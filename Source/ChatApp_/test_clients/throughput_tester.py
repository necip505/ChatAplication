"""
Client-side Throughput Tester for the Multi-User Chat System.

This script simulates a client connecting to the chat server (TCP or UDP)
and sending messages at a specified rate for a defined duration to help
measure system throughput and server performance under load.
"""
import socket
import threading
import time
import argparse
import uuid
import sys
import os

# Adjust path to import common.protocol
# This assumes the script is run from the project root or test_clients/
# If run from project root:
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
# If run from test_clients/ directory (which is where it will be created):
# sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from common.protocol import create_message, parse_message, MAX_MSG_SIZE
from common.protocol import (
    MSG_TYPE_MESSAGE, MSG_TYPE_AUTH_REQUEST, MSG_TYPE_AUTH_RESPONSE,
    MSG_TYPE_UDP_DATA, MSG_TYPE_UDP_ACK, MSG_TYPE_CLIENT_LEAVING,
    MSG_TYPE_ERROR, MSG_TYPE_SYSTEM
    # Add other types if needed by the tester's logic, e.g., for server responses
)

# Global stop event for this tester instance
stop_event_tester = threading.Event()

# --- Counters ---
# These should ideally be managed per client instance if the script handles multiple.
# For now, assuming one script run = one client.
sent_messages_count = 0
received_messages_count = 0 # Messages received from *other* users
ack_received_count = 0 # For UDP, ACKs received from server for our messages
retransmissions_count = 0 # For UDP

# --- UDP Reliability State (if protocol is UDP) ---
client_seq_num_tester = 0
ack_pending_on_server_tester = {} # {seq: (timestamp, data, retries)}
next_expected_server_seq_num_tester = 0

# --- Reliability Parameters (for UDP) ---
RETRANSMISSION_TIMEOUT_TESTER = 1.0  # seconds
MAX_RETRIES_TESTER = 3


def log_event(client_id: str, event_type: str, message: str):
    """Simple logger for test events."""
    print(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [Client-{client_id}] [{event_type.upper()}] {message}")


# --- TCP Specific Functions ---
def connect_and_auth_tcp(sock: socket.socket, host: str, port: int, username: str) -> bool:
    log_event(username, "tcp", f"Attempting to connect to {host}:{port}")
    try:
        sock.connect((host, port))
        log_event(username, "tcp", "Connected.")

        # Auth flow
        auth_prompt_data = sock.recv(MAX_MSG_SIZE)
        if not auth_prompt_data:
            log_event(username, "tcp-auth", "No auth prompt from server.")
            return False
        auth_prompt = parse_message(auth_prompt_data)
        if not auth_prompt or auth_prompt.get("type") != MSG_TYPE_AUTH_REQUEST:
            log_event(username, "tcp-auth", f"Unexpected auth prompt: {auth_prompt}")
            return False
        
        log_event(username, "tcp-auth", f"Server auth prompt: {auth_prompt.get('payload',{}).get('message')}")
        auth_response_payload = {"username": username}
        auth_response_msg = create_message(MSG_TYPE_AUTH_RESPONSE, auth_response_payload)
        sock.sendall(auth_response_msg)

        server_confirmation = sock.recv(MAX_MSG_SIZE)
        if not server_confirmation:
            log_event(username, "tcp-auth", "No confirmation from server after sending username.")
            return False
        
        parsed_confirmation = parse_message(server_confirmation)
        if parsed_confirmation and parsed_confirmation.get("type") == MSG_TYPE_ERROR:
            log_event(username, "tcp-auth", f"Auth error: {parsed_confirmation.get('payload',{}).get('error')}")
            return False
        if parsed_confirmation and parsed_confirmation.get("type") == MSG_TYPE_SYSTEM: # Or whatever server sends on success
            log_event(username, "tcp-auth", f"Authenticated successfully: {parsed_confirmation.get('payload',{}).get('message')}")
            # Potentially receive user list here too if server sends it immediately
            return True
        log_event(username, "tcp-auth", f"Unexpected auth confirmation: {parsed_confirmation}")
        return False
    except Exception as e:
        log_event(username, "tcp-connect", f"Error: {e}")
        return False

def send_message_tcp(sock: socket.socket, text: str, client_id: str):
    global sent_messages_count
    try:
        msg_id = f"tcp_{client_id}_{uuid.uuid4()}"
        ts = time.time()
        payload = {"text": text} # Server adds sender for TCP
        message_bytes = create_message(MSG_TYPE_MESSAGE, payload, message_id=msg_id, send_timestamp=ts)
        sock.sendall(message_bytes)
        sent_messages_count += 1
        # log_event(client_id, "tcp-send", f"Sent: '{text}' (ID: {msg_id})")
    except Exception as e:
        log_event(client_id, "tcp-send", f"Error sending: {e}")
        stop_event_tester.set()


def receive_messages_tcp(sock: socket.socket, client_id: str, current_username: str):
    global received_messages_count, stop_event_tester
    while not stop_event_tester.is_set():
        try:
            data = sock.recv(MAX_MSG_SIZE)
            if not data:
                log_event(client_id, "tcp-recv", "Connection closed by server.")
                stop_event_tester.set()
                break
            
            message = parse_message(data)
            if message and message.get("type") == MSG_TYPE_MESSAGE:
                sender = message.get("payload", {}).get("sender")
                if sender != current_username: # Count messages from others
                    received_messages_count += 1
                    # Latency can be calculated here if message_id and send_timestamp are present
                    # original_ts = message.get("send_timestamp")
                    # msg_id = message.get("message_id")
                    # if original_ts and msg_id:
                    #     latency = (time.time() - original_ts) * 1000
                    #     log_event(client_id, "latency", f"ID={msg_id}, Sender={sender}, Latency={latency:.2f}ms")

        except socket.timeout:
            continue
        except Exception as e:
            if not stop_event_tester.is_set():
                log_event(client_id, "tcp-recv", f"Error receiving: {e}")
            stop_event_tester.set()
            break
    log_event(client_id, "tcp-recv", "Receive thread stopped.")


# --- UDP Specific Functions (Placeholders - need full reliability logic) ---
def connect_and_auth_udp(sock: socket.socket, server_addr_tuple: tuple, username: str) -> bool:
    global client_seq_num_tester, ack_pending_on_server_tester, next_expected_server_seq_num_tester
    log_event(username, "udp", f"Attempting auth with {server_addr_tuple}")
    
    auth_payload = {"username": username}
    # Client's initial auth message uses seq_num 0
    auth_msg_bytes = create_message(MSG_TYPE_AUTH_REQUEST, auth_payload, seq_num=client_seq_num_tester)
    ack_pending_on_server_tester[client_seq_num_tester] = (time.time(), auth_msg_bytes, 0)
    
    try:
        sock.sendto(auth_msg_bytes, server_addr_tuple)
        log_event(username, "udp-auth", f"Sent AUTH_REQUEST (seq:{client_seq_num_tester})")
        client_seq_num_tester += 1

        # Wait for ACK for seq 0 OR an AUTH_RESPONSE from server
        # This is a simplified wait; a real client would have a receive loop.
        # For a tester, we might need a short timeout here or rely on the retransmit thread.
        # For now, assume the receive_messages_udp will handle the response.
        # This part needs to be robust for the tester.
        # Let's assume for now that the main receive loop will catch the AUTH_RESPONSE.
        # We need to confirm that ack_pending_on_server_tester[0] is cleared.
        
        # A simple check loop for the ACK or AUTH_RESPONSE (could be part of receive loop)
        auth_confirmed_time = time.time()
        while 0 in ack_pending_on_server_tester and (time.time() - auth_confirmed_time < 5.0): # Wait up to 5s for auth ack
            time.sleep(0.1)
            if stop_event_tester.is_set(): return False # Auth failed due to other error

        if 0 in ack_pending_on_server_tester:
            log_event(username, "udp-auth", "Timeout waiting for ACK/Response for initial AUTH_REQUEST.")
            return False
        
        log_event(username, "udp-auth", "Initial AUTH_REQUEST likely ACKed or responded to.")
        # next_expected_server_seq_num_tester should be 0 at this point for server's first data.
        return True # Placeholder - real success depends on AUTH_RESPONSE content

    except Exception as e:
        log_event(username, "udp-auth", f"Error during UDP auth: {e}")
        return False


def send_message_udp(sock: socket.socket, server_addr_tuple: tuple, text: str, client_id: str):
    global sent_messages_count, client_seq_num_tester, ack_pending_on_server_tester
    try:
        msg_id = f"udp_{client_id}_{uuid.uuid4()}"
        ts = time.time()
        
        message_content_payload = {"text": text, "message_id": msg_id, "send_timestamp": ts}
        udp_data_payload = {"message_content": message_content_payload, "original_type": MSG_TYPE_MESSAGE}
        
        message_bytes = create_message(MSG_TYPE_UDP_DATA, udp_data_payload, seq_num=client_seq_num_tester)
        ack_pending_on_server_tester[client_seq_num_tester] = (time.time(), message_bytes, 0)
        
        sock.sendto(message_bytes, server_addr_tuple)
        sent_messages_count += 1
        # log_event(client_id, "udp-send", f"Sent (seq:{client_seq_num_tester}): '{text}' (ID: {msg_id})")
        client_seq_num_tester += 1
    except Exception as e:
        log_event(client_id, "udp-send", f"Error sending: {e}")
        stop_event_tester.set()

def receive_messages_udp(sock: socket.socket, server_addr_tuple: tuple, client_id: str, current_username: str):
    global received_messages_count, stop_event_tester, next_expected_server_seq_num_tester, ack_pending_on_server_tester, ack_received_count
    while not stop_event_tester.is_set():
        try:
            data, addr = sock.recvfrom(MAX_MSG_SIZE)
            if addr != server_addr_tuple:
                continue

            message = parse_message(data)
            if not message:
                continue

            msg_type = message.get("type")
            payload = message.get("payload", {})
            server_seq = message.get("seq_num")
            server_ack = message.get("ack_num")

            if msg_type == MSG_TYPE_UDP_ACK:
                if server_ack is not None and server_ack in ack_pending_on_server_tester:
                    # log_event(client_id, "udp-recv", f"Server ACKed our seq: {server_ack}")
                    del ack_pending_on_server_tester[server_ack]
                    ack_received_count += 1
                continue
            
            if msg_type == MSG_TYPE_AUTH_RESPONSE: # Handle server's response to our initial auth
                if payload.get("error"):
                    log_event(client_id, "udp-auth", f"Auth Error from Server: {payload.get('error')}")
                    stop_event_tester.set() # Failed auth
                else:
                    log_event(client_id, "udp-auth", f"Auth OK from Server: {payload.get('message', 'Authenticated')}")
                    # If our initial auth (seq 0) was pending, this response implies it was received.
                    if 0 in ack_pending_on_server_tester: # Assuming initial auth is seq 0
                         del ack_pending_on_server_tester[0] 
                         ack_received_count +=1 # Count this as an implicit ACK for auth
                # This message from server might also have a seq_num that we need to ACK
                if server_seq is not None:
                    ack_to_server_payload = {"status": "Client got AUTH_RESPONSE"}
                    ack_b = create_message(MSG_TYPE_UDP_ACK, ack_to_server_payload, ack_num=server_seq)
                    sock.sendto(ack_b, server_addr_tuple)
                    if server_seq == next_expected_server_seq_num_tester:
                        next_expected_server_seq_num_tester +=1
                continue


            if msg_type == MSG_TYPE_UDP_DATA:
                if server_seq is None:
                    continue

                ack_to_server_payload = {"status": "Client got server_seq"}
                ack_bytes = create_message(MSG_TYPE_UDP_ACK, ack_to_server_payload, ack_num=server_seq)
                sock.sendto(ack_bytes, server_addr_tuple)

                if server_seq == next_expected_server_seq_num_tester:
                    next_expected_server_seq_num_tester += 1
                    actual_content = payload.get("message_content", {})
                    original_type = payload.get("original_type")
                    if original_type == MSG_TYPE_MESSAGE:
                        sender = actual_content.get("sender")
                        if sender != current_username:
                            received_messages_count += 1
                            # Latency calculation
                            # original_ts_udp = actual_content.get("send_timestamp")
                            # msg_id_udp = actual_content.get("message_id")
                            # if original_ts_udp and msg_id_udp:
                            #     latency_udp = (time.time() - original_ts_udp) * 1000
                            #     log_event(client_id, "latency-udp", f"ID={msg_id_udp}, Sender={sender}, Latency={latency_udp:.2f}ms")
                # else: handle duplicate or out-of-order server messages if necessary
        except socket.timeout:
            continue
        except Exception as e:
            if not stop_event_tester.is_set():
                log_event(client_id, "udp-recv", f"Error receiving: {e}")
            stop_event_tester.set()
            break
    log_event(client_id, "udp-recv", "Receive thread stopped.")


def check_client_retransmissions_udp(sock: socket.socket, server_addr_tuple: tuple, client_id: str):
    global ack_pending_on_server_tester, stop_event_tester, retransmissions_count
    while not stop_event_tester.is_set():
        current_time = time.time()
        for seq, (ts, data, retries) in list(ack_pending_on_server_tester.items()):
            if current_time - ts > RETRANSMISSION_TIMEOUT_TESTER:
                if retries < MAX_RETRIES_TESTER:
                    log_event(client_id, "udp-retransmit", f"Retransmitting seq:{seq}, attempt:{retries+1}")
                    try:
                        sock.sendto(data, server_addr_tuple)
                        ack_pending_on_server_tester[seq] = (time.time(), data, retries + 1)
                        retransmissions_count +=1
                    except Exception as e:
                        log_event(client_id, "udp-retransmit", f"Error: {e}")
                else:
                    log_event(client_id, "udp-retransmit", f"Max retries for seq:{seq}. Giving up.")
                    del ack_pending_on_server_tester[seq]
                    if seq == 0 : # Failed initial auth
                        log_event(client_id, "udp-auth", "Critical: Failed to get ACK for initial auth after max retries.")
                        stop_event_tester.set()
        time.sleep(RETRANSMISSION_TIMEOUT_TESTER / 2.0)
    log_event(client_id, "udp-retransmit", "Retransmission thread stopped.")


# --- Main Test Execution ---
def run_test_client(args):
    global stop_event_tester, sent_messages_count, received_messages_count, client_seq_num_tester, ack_pending_on_server_tester, next_expected_server_seq_num_tester, ack_received_count, retransmissions_count

    # Reset global state for this client instance (important if this func is called multiple times in one script)
    stop_event_tester.clear()
    sent_messages_count = 0
    received_messages_count = 0
    ack_received_count = 0
    retransmissions_count = 0
    client_seq_num_tester = 0
    ack_pending_on_server_tester = {}
    next_expected_server_seq_num_tester = 0


    current_username = f"{args.username_prefix}{args.client_id}"
    log_event(current_username, "main", f"Starting test client. Protocol: {args.protocol}, Target: {args.host}:{args.port}, Duration: {args.duration}s, Rate: {args.rate}msg/s")

    sock = None
    recv_thread = None
    retransmit_thread_udp = None
    server_address_tuple = (args.host, args.port)

    try:
        # Setup socket and connect/authenticate
        if args.protocol == "tcp":
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if not connect_and_auth_tcp(sock, args.host, args.port, current_username):
                log_event(current_username, "main", "TCP Auth failed. Exiting.")
                return
            recv_thread = threading.Thread(target=receive_messages_tcp, args=(sock, current_username, current_username), daemon=True)
        elif args.protocol == "udp":
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Explicitly bind the UDP socket to an ephemeral port before starting receiver
            # This helps prevent "WinError 10022: Invalid argument" on Windows when recvfrom is called early.
            sock.bind(('', 0))
            log_event(current_username, "udp-setup", f"Socket bound to local address: {sock.getsockname()}")

            # For UDP, auth is more integrated with initial send & receive loop
            # The connect_and_auth_udp will send the first message.
            # The receive_messages_udp needs to start first to catch server's auth response / ACKs.
            retransmit_thread_udp = threading.Thread(target=check_client_retransmissions_udp, args=(sock, server_address_tuple, current_username), daemon=True)
            retransmit_thread_udp.start()
            recv_thread = threading.Thread(target=receive_messages_udp, args=(sock, server_address_tuple, current_username, current_username), daemon=True)
            recv_thread.start() # Start receiver before attempting auth for UDP to catch responses
            if not connect_and_auth_udp(sock, server_address_tuple, current_username):
                log_event(current_username, "main", "UDP Auth failed. Exiting.")
                stop_event_tester.set() # Ensure threads stop
                # Threads will be joined in finally
                return
        else:
            log_event(current_username, "main", f"Unsupported protocol: {args.protocol}")
            return

        if args.protocol == "tcp": # Start TCP receiver only after successful auth
            recv_thread.start()

        # Message sending loop
        start_time = time.time()
        messages_to_send_total = args.duration * args.rate
        
        log_event(current_username, "main", f"Starting to send {messages_to_send_total} messages over {args.duration}s.")

        for i in range(messages_to_send_total):
            if stop_event_tester.is_set():
                log_event(current_username, "main", "Stop event received during sending. Breaking loop.")
                break
            
            msg_text = f"M:{i} from {current_username} " + ("x" * (args.message_size - 20 - len(str(i)) - len(current_username)))
            msg_text = msg_text[:args.message_size] # Ensure exact size

            if args.protocol == "tcp":
                send_message_tcp(sock, msg_text, current_username)
            else: # udp
                send_message_udp(sock, server_address_tuple, msg_text, current_username)
            
            # Rate limiting: sleep to distribute messages over the second
            if args.rate > 0:
                time.sleep(1.0 / args.rate) 
            
            if time.time() - start_time > args.duration + 2 : # Safety break if duration exceeded significantly
                 log_event(current_username, "main", "Exceeded test duration significantly. Breaking send loop.")
                 break
        
        log_event(current_username, "main", f"Finished sending messages. Sent: {sent_messages_count}")

        # Wait for a short period to allow final messages/ACKs to be processed
        # or until duration is truly up if sending was faster.
        remaining_time = args.duration - (time.time() - start_time)
        if remaining_time > 0:
            time.sleep(remaining_time)
        
        log_event(current_username, "main", "Test duration complete.")

    except Exception as e:
        log_event(current_username, "main", f"Unhandled exception in run_test_client: {e}")
    finally:
        stop_event_tester.set()
        log_event(current_username, "main", "Initiating shutdown...")

        if args.protocol == "udp" and sock:
            # Send CLIENT_LEAVING for UDP
            log_event(current_username, "udp", "Sending CLIENT_LEAVING message.")
            leaving_payload = {"username": current_username, "reason": "Test client finished"}
            # This leaving message also needs a seq_num and might need retransmission handling
            # For simplicity in tester, send it once.
            leaving_msg_bytes = create_message(MSG_TYPE_CLIENT_LEAVING, leaving_payload, seq_num=client_seq_num_tester)
            try:
                sock.sendto(leaving_msg_bytes, server_address_tuple)
                client_seq_num_tester+=1
            except Exception as e:
                log_event(current_username, "udp", f"Error sending CLIENT_LEAVING: {e}")
        
        time.sleep(0.5) # Give a moment for threads to see stop_event

        if recv_thread and recv_thread.is_alive():
            log_event(current_username, "main", "Joining receive thread...")
            recv_thread.join(timeout=2.0)
        if args.protocol == "udp" and retransmit_thread_udp and retransmit_thread_udp.is_alive():
            log_event(current_username, "main", "Joining UDP retransmit thread...")
            retransmit_thread_udp.join(timeout=2.0)

        if sock:
            log_event(current_username, "main", "Closing socket.")
            sock.close()
        
        log_event(current_username, "main", f"Test finished. Sent: {sent_messages_count}, Received (from others): {received_messages_count}, ACKs Recv (UDP): {ack_received_count}, Retransmits (UDP): {retransmissions_count}")
        # Output parsable results
        print(f"RESULT_LINE:ClientID={args.client_id},Username={current_username},Protocol={args.protocol},Duration={args.duration},Rate={args.rate},Sent={sent_messages_count},Received={received_messages_count},AcksReceived={ack_received_count},Retransmissions={retransmissions_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat Client Throughput Tester")
    parser.add_argument("--protocol", choices=["tcp", "udp"], required=True, help="Protocol to use (tcp or udp)")
    parser.add_argument("--host", default="127.0.0.1", help="Server host IP address")
    parser.add_argument("--port", type=int, help="Server port number (TCP: 65432, UDP: 65433 default)")
    parser.add_argument("--username_prefix", default="testuser", help="Prefix for usernames (client ID will be appended)")
    parser.add_argument("--client_id", type=int, default=0, help="Unique ID for this client instance")
    parser.add_argument("--duration", type=int, default=10, help="Test duration in seconds")
    parser.add_argument("--rate", type=int, default=1, help="Messages per second to send")
    parser.add_argument("--message_size", type=int, default=50, help="Approximate size of messages to send in bytes")

    args = parser.parse_args()

    # Set default port if not specified
    if args.port is None:
        if args.protocol == "tcp":
            args.port = 65432
        elif args.protocol == "udp":
            args.port = 65433
    
    run_test_client(args)