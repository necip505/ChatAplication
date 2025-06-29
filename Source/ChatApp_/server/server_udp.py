"""
UDP Chat Server for the Multi-User Chat System.

This server listens for incoming UDP datagrams, manages client "connections" (state
associated with client addresses), and implements a custom reliability layer
(sequence numbers, acknowledgments, retransmissions) for message exchange.
It handles client authentication (basic username registration), message broadcasting,
and user join/leave notifications over UDP.
"""
import socket
import threading
import sys
import os
import time
from collections import deque

# Adjust the path to import from the common directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import create_message, parse_message, MAX_MSG_SIZE
from common.protocol import (MSG_TYPE_UDP_DATA, MSG_TYPE_UDP_ACK,
                             MSG_TYPE_AUTH_REQUEST, MSG_TYPE_AUTH_RESPONSE, # For initial handshake
                             MSG_TYPE_MESSAGE, MSG_TYPE_SYSTEM, MSG_TYPE_ERROR,
                             MSG_TYPE_USER_JOINED, MSG_TYPE_USER_LEFT, MSG_TYPE_USER_LIST, MSG_TYPE_CLIENT_LEAVING,
                             MSG_TYPE_PRIVATE_MESSAGE, MSG_TYPE_PRIVATE_MESSAGE_FAILED)

HOST = '0.0.0.0'
PORT = 65433 # Different port for UDP server

# Global dictionary to store active client states.
# Key: client_address (tuple, (ip, port))
# Value: A dictionary containing client-specific information:
#   "username": (str) Authenticated username.
#   "last_ack_num": (int) The last sequence number acknowledged by this client (for messages server sent to it). Not fully used yet.
#   "next_expected_seq_num": (int) The next sequence number expected from this client for its data messages.
#   "ack_pending": (dict) Messages sent by the server to this client that are awaiting acknowledgment.
#                       Key: sequence_number (int) of the sent message.
#                       Value: (timestamp (float), data (bytes), retries (int))
#   "server_to_client_seq_num": (int) The next sequence number the server will use for messages it initiates to this client.
clients = {}

# Global variable for the server's UDP socket.
server_socket = None

# Event to signal all server threads to terminate gracefully.
stop_server_event = threading.Event()

# Reliability Parameters
RETRANSMISSION_TIMEOUT = 1.0  # Seconds to wait for an ACK before retransmitting.
MAX_RETRIES = 3               # Maximum number of retransmission attempts for a single message.

def send_reliable_message(sock: socket.socket, address: tuple, msg_type: str, payload: dict, seq_num: int):
    """
    Sends a message (typically MSG_TYPE_UDP_DATA) to a specific client address reliably.
    This means the message is assigned a sequence number, sent, and stored in the
    client's `ack_pending` queue for potential retransmission if not acknowledged.

    Args:
        sock (socket.socket): The server's UDP socket.
        address (tuple): The (IP, port) address of the target client.
        msg_type (str): The type of the message to be sent (e.g., MSG_TYPE_UDP_DATA).
        payload (dict): The payload of the message.
        seq_num (int): The sequence number to assign to this message.
    """
    client_info = clients.get(address) # Get state for the target client.
    if not client_info:
        print(f"Error: Client {address} not found for reliable send.")
        return

    message_bytes = create_message(msg_type, payload, seq_num=seq_num)
    
    # Store for retransmission
    client_info["ack_pending"][seq_num] = (time.time(), message_bytes, 0) # timestamp, data, retries
    
    try:
        print(f"Sending (seq:{seq_num}) to {address}: {payload.get('text', payload)}")
        sock.sendto(message_bytes, address)
    except socket.error as e:
        print(f"Socket error sending to {address}: {e}")


def check_retransmissions():
    """
    Periodically scans all connected clients for messages sent by the server
    that have not yet been acknowledged and may require retransmission.
    This function runs in a dedicated background thread.

    It iterates through each client's `ack_pending` queue. If a message's
    timestamp exceeds the `RETRANSMISSION_TIMEOUT`, it's resent, and its
    retry count is incremented. If `MAX_RETRIES` is reached, the server
    gives up on that message for that client.
    """
    global server_socket # Use the global server socket for sending.
    while not stop_server_event.is_set(): # Continue running until server shutdown.
        current_time = time.time()
        # Iterate over a copy of clients.items() to allow modification of `clients`
        # (e.g., removing a client if auth retransmission fails hard).
        for addr, client_info in list(clients.items()):
            # Iterate over a copy of ack_pending items for safe removal.
            for seq_num, (timestamp, data, retries) in list(client_info.get("ack_pending", {}).items()):
                if current_time - timestamp > RETRANSMISSION_TIMEOUT:
                    if retries < MAX_RETRIES:
                        # print(f"SERVER: Retransmitting (seq:{seq_num}, attempt:{retries+1}) to {addr}")
                        try:
                            if server_socket: server_socket.sendto(data, addr)
                            # Update timestamp and retry count for the pending ACK.
                            client_info["ack_pending"][seq_num] = (time.time(), data, retries + 1)
                        except socket.error as e:
                            print(f"SERVER: Socket error retransmitting to {addr}: {e}")
                            # Consider implications: if socket is broken, client might be gone.
                    else:
                        print(f"SERVER: Max retries ({MAX_RETRIES}) reached for seq:{seq_num} to {addr}. Giving up on this message.")
                        del client_info["ack_pending"][seq_num]
                        
                        # If an initial auth response from server fails repeatedly, remove the client entry.
                        # This assumes server_to_client_seq_num 0 is used for the first critical server response.
                        if client_info.get("username") is None and seq_num == client_info.get("server_to_client_seq_num", -1) -1 : # Check if it was the last attempted server_seq
                             print(f"SERVER: Critical auth-related message failed for {addr}. Removing unauthenticated client entry.")
                             if addr in clients: del clients[addr] # Remove the client entry.
        
        # Sleep for a fraction of the timeout to check periodically.
        time.sleep(RETRANSMISSION_TIMEOUT / 2.0)


def broadcast_to_clients(message_payload_content: dict, original_message_type: str, exclude_address: tuple = None):
    """
    Broadcasts a message to all authenticated UDP clients.
    The message is wrapped in MSG_TYPE_UDP_DATA and sent reliably, meaning
    the server will expect an ACK from each client for this broadcast.
    It uses a per-client sequence number (`server_to_client_seq_num`) for these broadcasts.

    Args:
        message_payload_content (dict): The actual content (payload) of the message to broadcast.
        original_message_type (str): The original type of the message being broadcast (e.g., MSG_TYPE_MESSAGE, MSG_TYPE_USER_JOINED).
        exclude_address (tuple, optional): The address (IP, port) of a client to exclude from this broadcast.
    """
    global server_socket
    # print(f"SERVER: Broadcasting UDP - Type: {original_message_type}, Content: {message_payload_content}")
    
    # This simple broadcast won't use individual sequence numbers per client yet.
    # For a true reliable broadcast, each client would need its own seq num management for this message.
    # For now, let's assume system messages like join/leave are sent unreliably or with a simpler mechanism.
    # Or, we can iterate and send reliably to each.
    
    # For now, let's make USER_JOINED and USER_LEFT reliable for demonstration
    # For messages like USER_JOINED, USER_LEFT, and relayed MESSAGEs, send reliably.
    # Other system messages might be sent unreliably if desired (not current implementation for broadcast).
    # For private messages, this broadcast function is not used; they are sent directly.
    if original_message_type in [MSG_TYPE_USER_JOINED, MSG_TYPE_USER_LEFT, MSG_TYPE_MESSAGE, MSG_TYPE_USER_LIST, MSG_TYPE_SYSTEM]:
        for client_addr, client_info_data in list(clients.items()):
            # Send only to authenticated clients and exclude the specified address (if any).
            if client_addr != exclude_address and client_info_data.get("username"):
                
                # Each client has its own sequence number for messages initiated by the server.
                if "server_to_client_seq_num" not in client_info_data: # Initialize if not present
                    client_info_data["server_to_client_seq_num"] = 0
                
                current_server_seq_for_client = client_info_data["server_to_client_seq_num"]
                
                # The payload for MSG_TYPE_UDP_DATA wraps the original message content and type.
                udp_data_payload = {
                    "message_content": message_payload_content,
                    "original_type": original_message_type
                }
                
                send_reliable_message(
                    server_socket,
                    client_addr,
                    MSG_TYPE_UDP_DATA, # All reliable data is wrapped in UDP_DATA
                    udp_data_payload,
                    current_server_seq_for_client
                )
                client_info_data["server_to_client_seq_num"] += 1 # Increment for the next server-initiated message to this client.
    else:
        # Fallback for any other message types: send unreliably (fire and forget).
        # This part is currently not expected to be hit by `broadcast_to_clients` calls.
        unreliable_msg_bytes = create_message(original_message_type, message_payload_content) # No seq_num
        for client_addr, client_info_data in list(clients.items()):
            if client_addr != exclude_address and client_info_data.get("username"):
                try:
                    if server_socket: server_socket.sendto(unreliable_msg_bytes, client_addr)
                except socket.error as e:
                    print(f"SERVER: Error broadcasting unreliably to {client_addr}: {e}")


def handle_udp_message(data: bytes, addr: tuple):
    """
    Processes a single incoming UDP datagram received from a client.
    This function is called by the main server loop for each received packet.
    It handles authentication, ACKs, data messages, and client disconnections.

    Args:
        data (bytes): The raw data received in the UDP packet.
        addr (tuple): The (IP, port) address of the client who sent the packet.
    """
    global server_socket # For sending responses/ACKs.
    message = parse_message(data) # Attempt to parse the incoming data.
    if not message:
        print(f"Received malformed UDP packet from {addr}. Ignoring.")
        return

    msg_type = message.get("type")
    payload = message.get("payload")
    seq_num = message.get("seq_num") # For data from client
    ack_num = message.get("ack_num") # For ACKs from client

    client_info = clients.get(addr)

    # --- Phase 1: Initial Authentication (Client Registration) ---
    if msg_type == MSG_TYPE_AUTH_REQUEST: # Client sends this with its desired username.
        username_attempt = payload.get("username")
        if not username_attempt:
            print(f"SERVER: Auth request from {addr} missing username. Ignoring.")
            # Ideally, send a non-reliable error, or client times out.
            return

        # Check for duplicate username.
        # This check iterates values, could be slow with many users; a set of usernames could optimize.
        is_duplicate = any(c.get("username") == username_attempt for c in clients.values())
        if is_duplicate:
            print(f"SERVER: Duplicate username '{username_attempt}' attempt from {addr}.")
            # Reliably send an AUTH_RESPONSE error.
            # Client's initial AUTH_REQUEST is expected to have seq_num (e.g., 0).
            if seq_num is not None: # ACK client's auth attempt first.
                 ack_auth_attempt = create_message(MSG_TYPE_UDP_ACK, {}, ack_num=seq_num)
                 if server_socket: server_socket.sendto(ack_auth_attempt, addr)
            
            # Prepare and send the error message reliably.
            auth_error_payload = {"error": "Username is already taken."}
            # Server uses its own sequence number for this response.
            # Initialize client state for sending this reliable error.
            if addr not in clients: # Should not happen if client sent AUTH_REQUEST
                 clients[addr] = {"username": None, "ack_pending": {}, "server_to_client_seq_num": 0, "next_expected_seq_num": (seq_num + 1) if seq_num is not None else 0}
            
            s_seq_auth_err = clients[addr]["server_to_client_seq_num"]
            send_reliable_message(server_socket, addr, MSG_TYPE_AUTH_RESPONSE, auth_error_payload, s_seq_auth_err)
            clients[addr]["server_to_client_seq_num"] += 1
            # Do not fully register client yet. They might retry or disconnect.
            # The ack_pending entry for the error will eventually time out if client doesn't ACK.
            return

        # Username is unique and valid. Register the client.
        print(f"SERVER: User '{username_attempt}' registered via UDP from {addr}.")
        clients[addr] = {
            "username": username_attempt,
            "last_ack_num": -1, # Tracks ACKs from client for server's messages.
            "next_expected_seq_num": (seq_num + 1) if seq_num is not None else 0, # Next data seq from this client.
            "ack_pending": {}, # Server's reliable messages to this client awaiting client's ACK.
            "server_to_client_seq_num": 0 # Server's sequence number for messages to this client.
        }
        
        # ACK the client's successful AUTH_REQUEST.
        if seq_num is not None:
            ack_payload = {"message": "Username registered successfully."}
            ack_msg = create_message(MSG_TYPE_UDP_ACK, ack_payload, ack_num=seq_num)
            if server_socket: server_socket.sendto(ack_msg, addr)

        # Send a reliable welcome message to the new client.
        welcome_content = {"text": f"Welcome {username_attempt}!"}
        s_seq_welcome = clients[addr]["server_to_client_seq_num"]
        send_reliable_message(server_socket, addr, MSG_TYPE_UDP_DATA,
                              {"message_content": welcome_content, "original_type": MSG_TYPE_SYSTEM},
                              s_seq_welcome)
        clients[addr]["server_to_client_seq_num"] += 1

        # Send the current user list to the new client (reliably).
        current_user_list_data = [c_info.get("username") for c_info in clients.values() if c_info.get("username")]
        user_list_content = {"users": current_user_list_data}
        s_seq_userlist = clients[addr]["server_to_client_seq_num"]
        send_reliable_message(server_socket, addr, MSG_TYPE_UDP_DATA,
                              {"message_content": user_list_content, "original_type": MSG_TYPE_USER_LIST},
                              s_seq_userlist)
        clients[addr]["server_to_client_seq_num"] += 1
        
        # Notify all other authenticated clients that a new user has joined.
        join_broadcast_content = {"username": username_attempt, "message": f"'{username_attempt}' has joined."}
        broadcast_to_clients(join_broadcast_content, MSG_TYPE_USER_JOINED, exclude_address=addr)
        return # End of AUTH_REQUEST processing.

    # --- Subsequent Message Handling (Client must be authenticated) ---
    if not client_info or not client_info.get("username"):
        # This client is not recognized or hasn't completed authentication.
        print(f"SERVER: Received message type '{msg_type}' from unauthenticated address {addr}. Ignoring.")
        # Consider sending an error or re-prompting for auth if this is frequent.
        return

    # --- Phase 2: Handling ACKs from Authenticated Clients ---
    # These are ACKs for messages the server sent reliably to this client.
    if msg_type == MSG_TYPE_UDP_ACK:
        if ack_num is not None and ack_num in client_info.get("ack_pending", {}):
            # print(f"SERVER: Received ACK (ack:{ack_num}) for server's seq from {client_info['username']}@{addr}")
            del client_info["ack_pending"][ack_num] # Message successfully acknowledged.
        else:
            # print(f"SERVER: Received unexpected/duplicate ACK (ack:{ack_num}) from {client_info['username']}@{addr}. Ignored.")
            pass # It's okay to receive duplicate ACKs; just ignore them if already processed.
        return # ACKs typically don't require further processing beyond clearing pending.

    # --- Phase 3: Handling Reliable Data (MSG_TYPE_UDP_DATA) from Authenticated Clients ---
    # These are messages from the client that require an ACK from the server.
    if msg_type == MSG_TYPE_UDP_DATA:
        if seq_num is None: # Reliable data must have a sequence number.
            print(f"SERVER: UDP_DATA from {client_info['username']}@{addr} missing sequence number. Ignoring.")
            return

        # Always send an ACK for any received UDP_DATA packet, even if duplicate or out of order.
        # This helps the client clear its retransmission buffer.
        ack_for_client_data = create_message(MSG_TYPE_UDP_ACK, {"status": "Server received your data"}, ack_num=seq_num)
        try:
            if server_socket: server_socket.sendto(ack_for_client_data, addr)
        except socket.error as e:
            print(f"SERVER: Error sending ACK for client_seq:{seq_num} to {addr}: {e}")

        # Process the data if it's the next expected sequence number.
        if seq_num == client_info.get("next_expected_seq_num", 0):
            # print(f"SERVER: Received in-order data (seq:{seq_num}) from {client_info['username']}@{addr}: {payload}")
            client_info["next_expected_seq_num"] += 1 # Update for the next expected packet.
            
            # Extract the actual message content and original type from the UDP_DATA wrapper.
            actual_message_content = payload.get("message_content", {})
            original_message_type_from_client = payload.get("original_type", MSG_TYPE_MESSAGE)

            if original_message_type_from_client == MSG_TYPE_MESSAGE:
                text_from_client = actual_message_content.get("text", "")
                if text_from_client:
                    current_sender_username = client_info["username"]
                    # Check for private message command
                    if text_from_client.startswith("/msg ") or text_from_client.startswith("/w "):
                        parts = text_from_client.split(" ", 2)
                        if len(parts) < 3:
                            error_payload_content = {"error": "Invalid private message format. Use /msg <recipient> <message> or /w <recipient> <message>"}
                            # Send error back to sender reliably
                            s_seq_err = client_info["server_to_client_seq_num"]
                            send_reliable_message(server_socket, addr, MSG_TYPE_UDP_DATA,
                                                  {"message_content": error_payload_content, "original_type": MSG_TYPE_ERROR},
                                                  s_seq_err)
                            client_info["server_to_client_seq_num"] += 1
                        else:
                            recipient_username = parts[1]
                            private_text = parts[2]
                            
                            recipient_addr = None
                            recipient_info = None
                            for r_addr, r_info in clients.items():
                                if r_info.get("username") == recipient_username:
                                    recipient_addr = r_addr
                                    recipient_info = r_info
                                    break
                            
                            if recipient_addr and recipient_info and recipient_addr != addr :
                                pm_payload_content = {
                                    "sender": current_sender_username,
                                    "recipient": recipient_username,
                                    "text": private_text,
                                    "message_id": actual_message_content.get("message_id"),
                                    "send_timestamp": actual_message_content.get("send_timestamp")
                                }
                                pm_payload_content = {k: v for k, v in pm_payload_content.items() if v is not None}
                                
                                # Send private message reliably to recipient
                                s_seq_pm = recipient_info["server_to_client_seq_num"]
                                send_reliable_message(server_socket, recipient_addr, MSG_TYPE_UDP_DATA,
                                                      {"message_content": pm_payload_content, "original_type": MSG_TYPE_PRIVATE_MESSAGE},
                                                      s_seq_pm)
                                recipient_info["server_to_client_seq_num"] += 1
                            elif recipient_addr == addr: # Sending to self
                                fail_payload_content = {
                                    "recipient": recipient_username,
                                    "reason": "You cannot send a private message to yourself."
                                }
                                s_seq_fail = client_info["server_to_client_seq_num"]
                                send_reliable_message(server_socket, addr, MSG_TYPE_UDP_DATA,
                                                      {"message_content": fail_payload_content, "original_type": MSG_TYPE_PRIVATE_MESSAGE_FAILED},
                                                      s_seq_fail)
                                client_info["server_to_client_seq_num"] += 1
                            else: # Recipient not found
                                fail_payload_content = {
                                    "recipient": recipient_username,
                                    "reason": f"User '{recipient_username}' not found or is offline."
                                }
                                s_seq_fail = client_info["server_to_client_seq_num"]
                                send_reliable_message(server_socket, addr, MSG_TYPE_UDP_DATA,
                                                      {"message_content": fail_payload_content, "original_type": MSG_TYPE_PRIVATE_MESSAGE_FAILED},
                                                      s_seq_fail)
                                client_info["server_to_client_seq_num"] += 1
                    else: # Regular broadcast message
                        message_to_broadcast = {
                            "sender": current_sender_username,
                            "text": text_from_client,
                            "message_id": actual_message_content.get("message_id"),
                            "send_timestamp": actual_message_content.get("send_timestamp")
                        }
                        message_to_broadcast = {k: v for k, v in message_to_broadcast.items() if v is not None}
                        broadcast_to_clients(message_to_broadcast, MSG_TYPE_MESSAGE, exclude_address=addr)
            # TODO: Handle other `original_message_type_from_client` if needed (e.g., client-side commands).
            elif original_message_type_from_client == MSG_TYPE_PRIVATE_MESSAGE:
                # This case should ideally not be initiated by client with original_type = PRIVATE_MESSAGE.
                # Server sets original_type to PRIVATE_MESSAGE when forwarding.
                # If client sends this directly, it's likely a protocol misuse or test.
                print(f"SERVER: Received UDP_DATA with original_type PRIVATE_MESSAGE from {client_info['username']}. This is unexpected.")
                # For now, just log. Could send an error.

        elif seq_num < client_info.get("next_expected_seq_num", 0):
            # Duplicate packet already processed. ACK was resent above.
            # print(f"SERVER: Received duplicate data (seq:{seq_num}) from {client_info['username']}@{addr}. Data ignored.")
            pass
        else: # seq_num > client_info["next_expected_seq_num"]
            # Out-of-order packet. Current simple implementation ignores it.
            # A more robust system might buffer out-of-order packets.
            print(f"SERVER: Received out-of-order data (seq:{seq_num}, expected:{client_info.get('next_expected_seq_num',0)}) from {client_info['username']}@{addr}. Ignoring.")
        return # End of MSG_TYPE_UDP_DATA handling.

    # --- Phase 4: Handling Direct CLIENT_LEAVING Message ---
    # This message is sent directly by the client, not wrapped in UDP_DATA.
    if msg_type == MSG_TYPE_CLIENT_LEAVING:
        # Client must be authenticated to send a valid LEAVING message.
        # (already checked by `if not client_info ...` above, but good to be explicit)
            
        leaving_username = payload.get("username", client_info.get("username")) # Prefer username from payload.
        print(f"SERVER: User {leaving_username}@{addr} is leaving. Reason: {payload.get('reason', 'N/A')}")

        # ACK the client's LEAVING message if it had a sequence number.
        if seq_num is not None:
            ack_leaving = create_message(MSG_TYPE_UDP_ACK, {"status": "Leaving message acknowledged"}, ack_num=seq_num)
            try:
                if server_socket: server_socket.sendto(ack_leaving, addr)
            except socket.error as e:
                print(f"SERVER: Error sending ACK for LEAVING to {addr}: {e}")
        
        # Remove the client from the active list.
        if addr in clients:
            del clients[addr]
        
        # Notify all other authenticated clients that this user has left.
        user_left_broadcast_content = {"username": leaving_username, "message": f"'{leaving_username}' has left the chat."}
        broadcast_to_clients(user_left_broadcast_content, MSG_TYPE_USER_LEFT, exclude_address=addr)
        return # End of CLIENT_LEAVING processing.

    # If message type is none of the above handled types for an authenticated client.
    print(f"SERVER: Received unhandled direct message type '{msg_type}' from {client_info.get('username', 'UNKNOWN_USER')}@{addr}")


def start_udp_server():
    """
    Initializes and starts the UDP chat server.
    Binds to the specified host and port, then enters a loop to receive and process datagrams.
    Also starts a background thread for managing message retransmissions.
    """
    global server_socket # Allow modification in the finally block.
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # Note: SO_REUSEADDR is less critical for UDP servers than TCP in many cases,
    # but can be useful if restarting quickly.
    # server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
        print(f"UDP Server listening on {HOST}:{PORT}")

        # Start retransmission checker thread
        retransmit_thread = threading.Thread(target=check_retransmissions, daemon=True)
        retransmit_thread.start()

        while not stop_server_event.is_set():
            try:
                data, addr = server_socket.recvfrom(MAX_MSG_SIZE)
                # Offload message handling to a new thread to keep recvfrom responsive?
                # For UDP, often handling is quick enough in the main loop unless processing is heavy.
                # Let's try direct handling first.
                handle_udp_message(data, addr)
            except socket.timeout: # server_socket.settimeout() would be needed
                continue
            except KeyboardInterrupt:
                print("\nUDP Server shutting down (KeyboardInterrupt)...")
                stop_server_event.set()
                break
            except Exception as e:
                print(f"Error in UDP server receive loop: {e}")
                # Log and continue, or break depending on severity
                # For now, continue.
                
    except socket.error as e:
        print(f"Socket error on UDP server startup: {e}")
    except Exception as e:
        print(f"UDP Server startup error: {e}")
    finally:
        stop_server_event.set()
        print("Closing UDP server socket...")
        if server_socket:
            server_socket.close()
        
        # Wait for retransmit_thread (optional, it's a daemon)
        if 'retransmit_thread' in locals() and retransmit_thread.is_alive():
            print("Waiting for retransmit thread to finish...")
            retransmit_thread.join(timeout=1.0)

        print("UDP Server shut down.")

if __name__ == "__main__":
    start_udp_server()