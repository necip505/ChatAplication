"""
UDP Chat Client for the Multi-User Chat System.

This client connects to the UDP server, provides a Tkinter-based GUI, and implements
a custom reliability layer (sequence numbers, acknowledgments, retransmissions)
for message exchange over UDP. It handles sending user messages, receiving broadcasts,
managing a local user list, and graceful disconnection.
"""
import socket
import threading
import sys
import os
import time # For timestamps and sleep
import uuid # For generating unique message IDs
import csv # For structured logging
from collections import deque

# Adjust the path to import from the common directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import create_message, parse_message, MAX_MSG_SIZE
from common.protocol import (MSG_TYPE_UDP_DATA, MSG_TYPE_UDP_ACK,
                             MSG_TYPE_AUTH_REQUEST, MSG_TYPE_AUTH_RESPONSE,
                             MSG_TYPE_MESSAGE, MSG_TYPE_SYSTEM, MSG_TYPE_ERROR,
                             MSG_TYPE_USER_JOINED, MSG_TYPE_USER_LEFT, MSG_TYPE_USER_LIST, MSG_TYPE_CLIENT_LEAVING,
                             MSG_TYPE_PRIVATE_MESSAGE, MSG_TYPE_PRIVATE_MESSAGE_FAILED)

from client.gui import ChatGUI # Re-use the same GUI

SERVER_HOST = '127.0.0.1'
SERVER_PORT = 65433 # UDP server port

# Global variable for the client's UDP socket.
client_socket = None
# Global variable for the ChatGUI instance.
gui = None
# Event to signal all client threads to terminate.
stop_event = threading.Event()
# Global variable to store the authenticated username of this client.
username_global = "UDPUser"

# --- Client-Side State for UDP Reliability ---
# Next sequence number to use for messages sent by this client.
client_seq_num = 0
# Next sequence number expected from the server for its data messages.
next_expected_server_seq_num = 0
# Dictionary to store messages sent by this client to the server that are awaiting acknowledgment.
# Key: sequence_number (int) of the sent message.
# Value: (timestamp (float), data (bytes), retries (int))
ack_pending_on_server = {}
# Set to store usernames of currently online users, updated from server messages.
current_users_set_udp = set()
# Tuple storing the (HOST, PORT) of the UDP server.
server_addr = (SERVER_HOST, SERVER_PORT)

# --- UDP Latency Logging Globals ---
latency_log_file_udp = None
latency_log_writer_udp = None
latency_log_file_header_udp = ['log_timestamp', 'message_id', 'sender_username', 'receiver_username', 'protocol', 'latency_ms']

def setup_latency_logger_udp(username: str):
    """Initializes the CSV logger for UDP latency data."""
    global latency_log_file_udp, latency_log_writer_udp
    filename = f"latency_udp_client_{username.replace(' ', '_')}.csv"
    file_exists = os.path.isfile(filename)
    try:
        latency_log_file_udp = open(filename, 'a+', newline='')
        latency_log_writer_udp = csv.writer(latency_log_file_udp)
        if not file_exists or os.path.getsize(filename) == 0:
            latency_log_writer_udp.writerow(latency_log_file_header_udp)
            latency_log_file_udp.flush()
        print(f"UDP Latency log will be written to: {filename}")
    except IOError as e:
        print(f"Error opening UDP latency log file {filename}: {e}")
        latency_log_file_udp = None
        latency_log_writer_udp = None

def log_latency_udp(msg_id: str, sender: str, receiver: str, latency: float):
    """Logs a single latency record to the CSV file for UDP."""
    if latency_log_writer_udp and latency_log_file_udp:
        try:
            log_ts = time.strftime('%Y-%m-%d %H:%M:%S') + f".{int(time.time()*1000)%1000:03d}"
            latency_log_writer_udp.writerow([log_ts, msg_id, sender, receiver, "UDP", f"{latency:.2f}"])
            latency_log_file_udp.flush()
        except Exception as e:
            print(f"Error writing to UDP latency log: {e}")

def close_latency_logger_udp():
    """Closes the UDP latency log file."""
    global latency_log_file_udp
    if latency_log_file_udp:
        try:
            latency_log_file_udp.close()
            latency_log_file_udp = None
            print("UDP Latency log file closed.")
        except Exception as e:
            print(f"Error closing UDP latency log: {e}")

# Reliability Parameters (should match or be compatible with server's)
RETRANSMISSION_TIMEOUT = 1.0  # Seconds to wait for an ACK before retransmitting.
MAX_RETRIES = 3               # Maximum number of retransmission attempts.

def send_reliable_udp_message(msg_type: str, payload: dict, seq_num_to_use: int):
    """
    Sends a message to the UDP server that requires an acknowledgment.
    The message is stored for potential retransmission if an ACK is not received.

    Args:
        msg_type (str): The type of the message (e.g., MSG_TYPE_UDP_DATA, MSG_TYPE_AUTH_REQUEST).
        payload (dict): The payload of the message.
        seq_num_to_use (int): The sequence number to assign to this message.
    """
    global client_socket, server_addr, ack_pending_on_server
    if stop_event.is_set() or not client_socket:
        if gui and gui.root.winfo_exists(): # Check if GUI is still valid
            gui.root.after(0, lambda: gui.display_error_message("Not connected or sending disabled."))
        return

    message_bytes = create_message(msg_type, payload, seq_num=seq_num_to_use)
    # Store message details for retransmission logic.
    ack_pending_on_server[seq_num_to_use] = (time.time(), message_bytes, 0)
    
    try:
        # print(f"CLIENT: Sending (seq:{seq_num_to_use}) to {server_addr}: {payload}") # Verbose log
        if client_socket: client_socket.sendto(message_bytes, server_addr)
    except socket.error as e:
        if gui and gui.root.winfo_exists():
            err_msg = f"Socket error sending UDP: {e}"
            gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
        # Consider if critical send failures should trigger stop_event.set()


def check_client_retransmissions():
    """
    Periodically checks for messages sent by this client to the server that have
    not yet been acknowledged and may require retransmission.
    This function runs in a dedicated background thread.
    """
    global client_socket, server_addr, ack_pending_on_server
    while not stop_event.is_set(): # Loop until client shutdown.
        current_time = time.time()
        # Iterate over a copy of items for safe removal from ack_pending_on_server.
        for seq_num, (timestamp, data, retries) in list(ack_pending_on_server.items()):
            if current_time - timestamp > RETRANSMISSION_TIMEOUT:
                if retries < MAX_RETRIES:
                    # print(f"CLIENT: Retransmitting (seq:{seq_num}, attempt:{retries+1}) to {server_addr}")
                    try:
                        if client_socket: client_socket.sendto(data, server_addr)
                        # Update timestamp and retry count.
                        ack_pending_on_server[seq_num] = (time.time(), data, retries + 1)
                    except socket.error as e:
                        if gui and gui.root.winfo_exists():
                            err_msg = f"Socket error retransmitting UDP: {e}"
                            gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
                else: # Max retries reached.
                    if gui and gui.root.winfo_exists():
                        err_msg = f"Max retries for seq:{seq_num} to server. Giving up on this message."
                        gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
                    del ack_pending_on_server[seq_num] # Stop trying to send this message.
                    
                    # If the failed message was the initial authentication (seq 0), it's a critical failure.
                    if seq_num == 0: # Assuming sequence number 0 is for the initial auth message.
                        if gui and gui.root.winfo_exists():
                            gui.root.after(0, lambda: gui.display_error_message("Failed to send initial auth message to server. Disconnecting."))
                        stop_event.set() # Signal client shutdown.
        time.sleep(RETRANSMISSION_TIMEOUT / 2.0) # Check periodically.


def receive_udp_messages():
    """
    Continuously listens for UDP messages from the server in a dedicated thread.
    Handles ACKs for messages sent by this client, processes reliable data messages
    from the server (sending ACKs back), and updates the GUI.
    GUI updates are scheduled on the main Tkinter thread using `gui.root.after`.
    """
    global client_socket, gui, stop_event, next_expected_server_seq_num, server_addr, client_seq_num, current_users_set_udp, ack_pending_on_server
    
    while not stop_event.is_set() and client_socket:
        try:
            data, addr = client_socket.recvfrom(MAX_MSG_SIZE) # Blocking call.
            if addr != server_addr: # Ensure message is from the expected server.
                # print(f"CLIENT: Received UDP from unexpected source {addr}. Ignoring.")
                continue

            message = parse_message(data)
            if not message: # Malformed message.
                if gui and gui.root.winfo_exists():
                    gui.root.after(0, lambda: gui.display_error_message("Malformed UDP from server."))
                continue
            
            if not gui or not gui.root.winfo_exists(): # GUI closed or not available.
                break # Stop processing if GUI is gone.

            msg_type = message.get("type")
            payload = message.get("payload", {})
            server_seq = message.get("seq_num") # Sequence number of a data message from server.
            server_ack = message.get("ack_num") # ACK number from server for one of our messages.

            # --- Part 1: Handle ACKs from Server ---
            # These ACKs are for messages this client sent reliably.
            if msg_type == MSG_TYPE_UDP_ACK:
                if server_ack is not None and server_ack in ack_pending_on_server:
                    # print(f"CLIENT: Server ACKed our seq: {server_ack}")
                    del ack_pending_on_server[server_ack] # Remove from pending list.
                # else:
                    # print(f"CLIENT: Server sent unexpected/duplicate ACK: {server_ack}")
                continue # ACKs usually don't carry further data to process in this client.

            # --- Part 2: Handle Reliable Data (MSG_TYPE_UDP_DATA) from Server ---
            # These are messages from the server that require an ACK from this client.
            if msg_type == MSG_TYPE_UDP_DATA:
                if server_seq is None: # Reliable data from server must have a sequence number.
                    gui.root.after(0, lambda: gui.display_error_message("Server UDP_DATA missing sequence number."))
                    continue

                # Send an ACK back to the server for this data packet.
                ack_to_server_payload = {"status": "Client received server_seq"}
                ack_msg_bytes = create_message(MSG_TYPE_UDP_ACK, ack_to_server_payload, ack_num=server_seq)
                try:
                    if client_socket: client_socket.sendto(ack_msg_bytes, server_addr)
                except socket.error as e:
                    err_msg = f"Error sending ACK for server_seq:{server_seq} to server: {e}"
                    gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))

                # Process the data if it's the next expected sequence number.
                if server_seq == next_expected_server_seq_num:
                    # print(f"CLIENT: Processing server seq: {server_seq}")
                    next_expected_server_seq_num += 1 # Update for the next expected packet.
                    
                    actual_content = payload.get("message_content", {})
                    original_type = payload.get("original_type")

                    # Schedule GUI updates based on the original message type.
                    if original_type == MSG_TYPE_MESSAGE:
                        s = actual_content.get("sender", "Unknown")
                        t = actual_content.get("text", "")
                        own = (s == username_global)

                        # Latency calculation for non-own messages
                        if not own:
                            print(f"DEBUG_UDP: Received message from other. Sender: {s}, Content: {actual_content}") # DEBUG LINE
                            original_send_timestamp = actual_content.get("send_timestamp")
                            msg_id = actual_content.get("message_id")
                            print(f"DEBUG_UDP: Extracted ts={original_send_timestamp}, id={msg_id}") # DEBUG LINE
                            if original_send_timestamp and msg_id:
                                receive_time = time.time()
                                latency = (receive_time - original_send_timestamp) * 1000 # milliseconds
                                log_latency_udp(msg_id, s, username_global, latency)
                            else: # DEBUG LINE
                                print(f"DEBUG_UDP: Missing timestamp or msg_id for latency calc. TS: {original_send_timestamp}, ID: {msg_id}") # DEBUG LINE

                        gui.root.after(0, lambda sender=s, text=t, is_own=own: gui.display_message(sender, text, is_own=is_own))
                    elif original_type == MSG_TYPE_SYSTEM:
                        sys_m = actual_content.get('text', '')
                        gui.root.after(0, lambda m=sys_m: gui.display_system_message(m))
                    elif original_type == MSG_TYPE_USER_JOINED:
                        ju = actual_content.get('username')
                        if ju:
                            current_users_set_udp.add(ju)
                            gui.root.after(0, lambda j_user=ju, u_list=list(current_users_set_udp): (
                                gui.display_system_message(f"{j_user} joined."), gui.update_user_list(u_list)
                            ))
                    elif original_type == MSG_TYPE_USER_LEFT:
                        lu = actual_content.get('username')
                        if lu and lu in current_users_set_udp:
                            current_users_set_udp.remove(lu)
                            gui.root.after(0, lambda l_user=lu, u_list=list(current_users_set_udp): (
                                gui.display_system_message(f"{l_user} left."), gui.update_user_list(u_list)
                            ))
                    elif original_type == MSG_TYPE_USER_LIST:
                         users_data = actual_content.get("users", [])
                         current_users_set_udp.clear()
                         current_users_set_udp.update(users_data)
                         gui.root.after(0, lambda u_list=list(current_users_set_udp): gui.update_user_list(u_list))
                    elif original_type == MSG_TYPE_PRIVATE_MESSAGE:
                        sender = actual_content.get("sender", "Unknown")
                        text = actual_content.get("text", "")
                        # is_own is False as this client is the recipient
                        gui.root.after(0, lambda s=sender, t=text: gui.display_private_message(s, t, is_own=False))
                    elif original_type == MSG_TYPE_PRIVATE_MESSAGE_FAILED:
                        recipient = actual_content.get("recipient", "Unknown")
                        reason = actual_content.get("reason", "Failed to send private message.")
                        gui.root.after(0, lambda rcp=recipient, rsn=reason: gui.display_error_message(f"PM to {rcp} failed: {rsn}"))
                    elif original_type == MSG_TYPE_ERROR: # Handle generic errors from server if wrapped in UDP_DATA
                        error_text = actual_content.get('error', 'Unknown server error via UDP_DATA.')
                        gui.root.after(0, lambda err=error_text: gui.display_error_message(err))
                    else: # Unhandled original type within UDP_DATA
                        unhandled_payload = actual_content
                        gui.root.after(0, lambda ot=original_type, p=unhandled_payload: gui.display_system_message(f"Server sent data with unhandled original_type {ot}: {p}"))
                
                elif server_seq < next_expected_server_seq_num: # Duplicate server packet.
                    # print(f"CLIENT: Duplicate server seq: {server_seq}. ACK resent. Data ignored.")
                    pass # ACK was already sent above.
                else: # Out-of-order server packet.
                    err_m = f"Out-of-order server seq: {server_seq}, expected: {next_expected_server_seq_num}. Ignored."
                    gui.root.after(0, lambda em=err_m: gui.display_error_message(em))
                continue # End of MSG_TYPE_UDP_DATA processing.

            # --- Part 3: Handle Direct Messages from Server (e.g., AUTH_RESPONSE) ---
            # These are not wrapped in UDP_DATA by the server in the current protocol for this type.
            if msg_type == MSG_TYPE_AUTH_RESPONSE:
                error_from_server = payload.get("error")
                if error_from_server:
                    gui.root.after(0, lambda err=error_from_server: gui.display_error_message(f"Server Auth Error: {err}"))
                    stop_event.set() # Authentication failed, signal shutdown.
                else: # Auth successful.
                    auth_ok_msg = payload.get('message', 'Authenticated successfully.')
                    gui.root.after(0, lambda m=auth_ok_msg: gui.display_system_message(f"Server Auth OK: {m}"))
                    
                    # If this AUTH_RESPONSE itself was sent reliably by server (has server_seq), ACK it.
                    if server_seq is not None:
                        ack_auth_response = create_message(MSG_TYPE_UDP_ACK, {}, ack_num=server_seq)
                        if client_socket: client_socket.sendto(ack_auth_response, server_addr)
                        if server_seq == next_expected_server_seq_num: # If it's in order
                             next_expected_server_seq_num +=1
                    
                    # Check if our initial auth message (client_seq_num 0) was implicitly ACKed
                    # by receiving a successful AUTH_RESPONSE.
                    if 0 in ack_pending_on_server and not error_from_server:
                        # print("CLIENT: Initial auth to server considered ACKed by successful AUTH_RESPONSE.")
                        del ack_pending_on_server[0]
                continue # End of MSG_TYPE_AUTH_RESPONSE processing.

            # --- Part 4: Unhandled Message Types ---
            unhandled_msg_type_val = msg_type # Capture for lambda
            unhandled_payload_val = payload   # Capture for lambda
            gui.root.after(0, lambda mt=unhandled_msg_type_val, p=unhandled_payload_val: (
                gui.display_system_message(f"CLIENT: Received unhandled direct message type '{mt}' from server: {p}")
            ))

        except socket.timeout: # Can occur if client_socket.settimeout() is used.
            if not stop_event.is_set(): continue
            else: break
        except ConnectionResetError: # Should be rare for UDP but handle defensively.
            if not stop_event.is_set() and gui and gui.root.winfo_exists():
                gui.root.after(0, lambda: gui.display_error_message("Connection error (UDP). Server might be down."))
            stop_event.set()
            break
        except socket.error as e: # Other socket errors.
            if not stop_event.is_set() and gui and gui.root.winfo_exists():
                err_msg = f"UDP Socket error in receive loop: {e}"
                gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
            stop_event.set()
            break
        except Exception as e: # Catch-all for other unexpected errors.
            if not stop_event.is_set() and gui and gui.root.winfo_exists():
                err_msg = f"Unexpected UDP Receiving error: {e}"
                gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
            stop_event.set()
            break
            
    # Loop exited, inform GUI if it still exists.
    if gui and gui.root.winfo_exists():
        final_status_msg = "UDP Receive thread stopped."
        gui.root.after(0, lambda m=final_status_msg: gui.display_system_message(m))


def gui_send_udp_message(message_text: str):
    """
    Callback function invoked by the GUI when the user attempts to send a message
    or a command (like '/quit' or '/disconnect') via UDP.

    Args:
        message_text (str): The text entered by the user.
    """
    global client_socket, stop_event, gui, client_seq_num, username_global

    if stop_event.is_set() or not client_socket:
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda: gui.display_error_message("Not connected."))
        return

    normalized_message = message_text.strip().lower()
    if normalized_message == '/quit' or normalized_message == '/disconnect':
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda: gui.display_system_message("Sending leaving notification..."))
        
        # Prepare and send a CLIENT_LEAVING message reliably.
        leaving_payload = {"username": username_global, "reason": "User initiated disconnect"}
        send_reliable_udp_message(MSG_TYPE_CLIENT_LEAVING, leaving_payload, client_seq_num)
        current_client_seq_num_for_leaving = client_seq_num # Capture for potential display
        client_seq_num += 1 # Increment sequence number.
        
        # Short delay to allow the OS to send the packet before shutting down.
        # This is a simple approach; a more robust way might involve waiting for ACK if critical.
        time.sleep(0.1)

        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda seq=current_client_seq_num_for_leaving: gui.display_system_message(f"Disconnecting... (leaving msg sent with seq {seq})"))
        stop_event.set() # Signal all threads and main logic to stop.
        return
    
    if message_text: # If it's a regular chat message.
        msg_id = str(uuid.uuid4())
        current_time = time.time()
        
        # Prepare the inner message content with text, ID, and timestamp
        message_content_payload = {
            "text": message_text,
            "message_id": msg_id,
            "send_timestamp": current_time
            # Sender will be added by server if needed, or known by context
        }
        
        # Wrap this content for reliable UDP transmission
        udp_data_payload = {
            "message_content": message_content_payload,
            "original_type": MSG_TYPE_MESSAGE
        }
        send_reliable_udp_message(MSG_TYPE_UDP_DATA, udp_data_payload, client_seq_num)
        
        # Optimistically display the user's own message in their GUI.
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda mt=message_text: gui.display_message(username_global, mt, is_own=True))
        client_seq_num += 1 # Increment sequence number for the next message.


def on_gui_close_udp():
    """
    Callback for when the UDP client's GUI window is closed by the user (e.g., 'X' button).
    Initiates the client shutdown sequence.
    """
    global stop_event
    # if gui and gui.root.winfo_exists():
        # gui.root.after(0, lambda: gui.display_system_message("Disconnecting on window close (UDP)..."))
    stop_event.set() # Signal threads to stop. Shutdown is handled in `start_udp_client` finally block.

def get_current_username_udp():
    """Callback for GUI to get the current UDP client's username."""
    global username_global
    return username_global

def start_udp_client():
    """
    Initializes and starts the UDP chat client.
    Sets up the GUI, "connects" to the server (sends initial auth), and starts
    threads for message receiving and retransmissions.
    """
    global client_socket, gui, stop_event, SERVER_HOST, SERVER_PORT, username_global, server_addr, client_seq_num, next_expected_server_seq_num

    # 1. Initialize GUI
    gui = ChatGUI(send_message_callback=gui_send_udp_message,
                  on_close_callback=on_gui_close_udp,
                  get_username_callback=get_current_username_udp)

    # 2. Prompt for connection details
    connection_details = gui.prompt_connection_details(default_host=SERVER_HOST, default_port=str(SERVER_PORT))
    if not connection_details:
        # User cancelled the dialog. prompt_connection_details's on_cancel
        # in gui.py already calls gui.root.quit(), so gui.start() (called later) will terminate.
        print("Connection setup cancelled by user. Exiting client_udp.")
        # We must return here to prevent the rest of start_udp_client from executing.
        return

    # Extract details from the dialog
    chosen_username = connection_details['username']
    NEW_SERVER_HOST = connection_details['host']
    NEW_SERVER_PORT = connection_details['port']
    selected_protocol = connection_details['protocol']

    # Update global variables for server connection and username
    # These globals (SERVER_HOST, SERVER_PORT, username_global) are declared
    # with the `global` keyword at the beginning of the start_udp_client function.
    SERVER_HOST = NEW_SERVER_HOST
    SERVER_PORT = NEW_SERVER_PORT
    username_global = chosen_username
    server_addr = (SERVER_HOST, SERVER_PORT) # Update server_addr with new details

    # Handle protocol selection for this UDP-specific client
    if selected_protocol.lower() != "udp":
        gui.display_system_message(
            f"Warning: Protocol '{selected_protocol.upper()}' was selected in the connection dialog, "
            f"but this is a UDP-only client. Connection will use UDP."
        )
        # Update the GUI title to reflect UDP, as prompt_connection_details might have set it based on selection.
        if gui.root and gui.root.winfo_exists():
            gui.root.title(f"Chat Client - {username_global} (UDP) - {SERVER_HOST}:{SERVER_PORT}")
    # If protocol was UDP, prompt_connection_details already set a similar title.
    # We could also consolidate title setting after this block, e.g.:
    # elif gui.root and gui.root.winfo_exists(): # Ensure title is set even if protocol was UDP
    #    gui.root.title(f"Chat Client - {username_global} (UDP) - {SERVER_HOST}:{SERVER_PORT}")
    # For now, only updating if there was a mismatch.
    setup_latency_logger_udp(username_global) # Initialize UDP logger

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # client_socket.settimeout(1.0) # Timeout for recvfrom if needed, or handle blocking in thread

    try:
        gui.display_system_message(f"UDP Client attempting to 'connect' to {SERVER_HOST}:{SERVER_PORT}")
        
        # Initial "authentication" message to server
        # Client sends its username, server ACKs, then server might send its own challenges or welcome.
        # Let's use MSG_TYPE_AUTH_REQUEST from client to server.
        auth_payload = {"username": username_global}
        # Use client_seq_num 0 for this initial message.
        send_reliable_udp_message(MSG_TYPE_AUTH_REQUEST, auth_payload, client_seq_num)
        client_seq_num += 1 # Increment for next data message

        # Start retransmission checker for client's messages
        client_retransmit_thread = threading.Thread(target=check_client_retransmissions, daemon=True)
        client_retransmit_thread.start()

        # Start receive thread
        receive_thread = threading.Thread(target=receive_udp_messages, daemon=True)
        receive_thread.start()

        gui.start() # Blocks until GUI is closed

    except socket.error as e:
        if gui: gui.display_error_message(f"UDP Socket error on startup: {e}")
    except Exception as e:
        if gui: gui.display_error_message(f"UDP Client startup error: {e}")
    finally:
        stop_event.set()
        if client_socket:
            client_socket.close()
            client_socket = None
            if gui: gui.display_system_message("UDP Socket closed.")

        if 'receive_thread' in locals() and receive_thread.is_alive():
            receive_thread.join(timeout=0.5)
        if 'client_retransmit_thread' in locals() and client_retransmit_thread.is_alive():
            client_retransmit_thread.join(timeout=0.5)
        
        close_latency_logger_udp() # Close the UDP log file
        print("UDP Client has shut down.")


if __name__ == "__main__":
    if len(sys.argv) == 3:
        SERVER_HOST = sys.argv[1]
        try:
            SERVER_PORT = int(sys.argv[2])
            server_addr = (SERVER_HOST, SERVER_PORT) # Update server_addr if provided
        except ValueError:
            print(f"Invalid port: {sys.argv[2]}. Using default {SERVER_PORT}.")
    elif len(sys.argv) > 1:
        print("Usage: python client_udp.py [server_host] [server_port]")
        sys.exit(1)
        
    start_udp_client()