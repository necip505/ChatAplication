"""
TCP Chat Server for the Multi-User Chat System.

This server listens for incoming TCP connections, handles client authentication (username),
broadcasts messages to connected clients, and manages user join/leave notifications.
Each client connection is managed in a separate thread.
"""

import socket
import threading
import sys
import os

# Adjust the path to import from the common directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from common.protocol import create_message, parse_message, MAX_MSG_SIZE
from common.protocol import MSG_TYPE_MESSAGE, MSG_TYPE_AUTH_REQUEST, MSG_TYPE_AUTH_RESPONSE
from common.protocol import MSG_TYPE_USER_JOINED, MSG_TYPE_USER_LEFT, MSG_TYPE_SYSTEM, MSG_TYPE_ERROR, MSG_TYPE_USER_LIST
from common.protocol import MSG_TYPE_PRIVATE_MESSAGE, MSG_TYPE_PRIVATE_MESSAGE_FAILED

HOST = '0.0.0.0'  # Listen on all available network interfaces
PORT = 65432        # Port to listen on (non-privileged ports are > 1023)

# Global dictionary to store active client connections.
# Key: client socket object, Value: username (str)
clients = {}

# List to keep track of active client handler threads. Used for potential graceful shutdown.
client_threads = []

def broadcast_message(message: bytes, sender_socket: socket.socket = None):
    """
    Sends a given message (bytes) to all connected and authenticated clients.
    Optionally excludes the original sender of the message.

    If sending to a client fails, that client is assumed to have disconnected
    and is removed.

    Args:
        message (bytes): The message to broadcast, already encoded.
        sender_socket (socket.socket, optional): The socket of the client who sent
                                                 the original message. If provided,
                                                 this client will not receive the broadcast.
    """
    # Log the broadcast action (decode for readability if it's bytes)
    # print(f"Broadcasting: {message.decode('utf-8', errors='ignore') if isinstance(message, bytes) else message}")
    
    # Iterate over a copy of the client socket keys to allow modification (removal) during iteration.
    for client_sock in list(clients.keys()):
        if client_sock != sender_socket:
            try:
                client_sock.sendall(message)
            except socket.error as e:
                # If broadcast fails, assume the client has disconnected.
                print(f"Error broadcasting to client {clients.get(client_sock, 'Unknown')}: {e}. Removing client.")
                remove_client(client_sock) # Attempt to gracefully remove the problematic client.

def remove_client(client_socket: socket.socket):
    """
    Removes a client from the active list, closes their socket,
    and broadcasts a 'user left' message to other clients.

    Args:
        client_socket (socket.socket): The socket object of the client to remove.
    """
    username = clients.get(client_socket) # Get username before trying to delete
    if username:
        print(f"Client {username} disconnected.")
        del clients[client_socket]
        try:
            client_socket.close()
        except socket.error:
            pass # Ignore errors if socket already closed
        
        # Notify other clients
        leave_msg_payload = {"username": username, "message": f"{username} has left the chat."}
        leave_msg = create_message(MSG_TYPE_USER_LEFT, leave_msg_payload)
        broadcast_message(leave_msg)
    elif client_socket in clients: # Handle cases where username might not be set yet
        print(f"Client (unknown username) disconnected.")
        del clients[client_socket]
        try:
            client_socket.close()
        except socket.error:
            pass


def handle_client(client_socket: socket.socket, addr):
    """
    Handles all communication with a single connected client.
    This function is intended to be run in a separate thread per client.
    It manages the authentication process and the main message receiving loop.

    Args:
        client_socket (socket.socket): The socket object for the connected client.
        addr (tuple): The address (IP, port) of the connected client.
    """
    print(f"Accepted TCP connection from {addr}")
    username = None

    try:
        # --- Authentication Phase ---
        # 1. Server requests username from the client.
        auth_request_payload = {"message": "Welcome! Please send your username to join the chat."}
        auth_request_msg = create_message(MSG_TYPE_AUTH_REQUEST, auth_request_payload)
        client_socket.sendall(auth_request_msg)

        # 2. Server waits for the client's username response.
        auth_response_data = client_socket.recv(MAX_MSG_SIZE)
        if not auth_response_data: # Client disconnected before sending username
            print(f"Client {addr} disconnected before completing authentication.")
            return # Thread will exit, finally block will attempt cleanup if socket was partially registered

        # 3. Parse client's response.
        auth_response = parse_message(auth_response_data)
        if auth_response and auth_response.get("type") == MSG_TYPE_AUTH_RESPONSE:
            username_attempt = auth_response.get("payload", {}).get("username")

            # 4. Validate username (must exist, must not be a duplicate).
            # Note: Accessing `clients.values()` should be relatively safe here as writes to `clients`
            # (adding new users) happen after this validation block for other threads.
            # For very high connection rates, a lock could be considered for `clients` dictionary.
            if not username_attempt or username_attempt in clients.values():
                error_detail = "Username cannot be empty." if not username_attempt else "Username is already taken."
                error_msg_payload = {"error": error_detail}
                error_msg = create_message(MSG_TYPE_ERROR, error_msg_payload)
                client_socket.sendall(error_msg)
                print(f"Invalid username attempt ('{username_attempt}') from {addr}. Reason: {error_detail}. Disconnecting.")
                return # Client will be disconnected by the finally block.
            
            username = username_attempt # Username is valid
            clients[client_socket] = username # Register the client
            print(f"User '{username}' authenticated and connected from {addr}.")

            # --- Post-Authentication ---
            # 5. Notify all other clients that a new user has joined.
            join_msg_payload = {"username": username, "message": f"'{username}' has joined the chat!"}
            join_msg = create_message(MSG_TYPE_USER_JOINED, join_msg_payload)
            broadcast_message(join_msg, client_socket) # Exclude the new user from this broadcast.

            # 6. Send a welcome message to the newly connected user.
            welcome_payload = {"message": f"Welcome to the chat, {username}!"}
            welcome_msg = create_message(MSG_TYPE_SYSTEM, welcome_payload)
            client_socket.sendall(welcome_msg)

            # 7. Send the current list of all online users to the newly connected client.
            # Iterating over `clients.values()` here is generally safe as new additions are serialized
            # by the server's main accept loop and thread creation.
            current_users = list(clients.values())
            user_list_payload = {"users": current_users}
            user_list_msg = create_message(MSG_TYPE_USER_LIST, user_list_payload)
            try:
                client_socket.sendall(user_list_msg)
            except socket.error as e:
                print(f"Error sending user list to {username}: {e}")
                # Not critical enough to disconnect, but log it.

        else:
            print(f"Failed to authenticate client {addr}. Disconnecting.")
            error_msg = create_message(MSG_TYPE_ERROR, {"error": "Authentication failed."})
            client_socket.sendall(error_msg)
            return # Disconnect client

        # --- Main Message Handling Loop ---
        while True:
            # Wait to receive data from the client.
            data = client_socket.recv(MAX_MSG_SIZE)
            if not data: # Empty data usually means client closed the connection.
                print(f"Client '{username}' from {addr} sent empty data, assuming disconnection.")
                break # Exit loop, client will be removed in finally block.
            
            message = parse_message(data)
            if message:
                # print(f"Received from '{username}': {message}") # Verbose logging
                if message.get("type") == MSG_TYPE_MESSAGE:
                    text_payload = message.get("payload", {}).get("text", "")
                    if text_payload: # Only process if there's text
                        # Check for private message command
                        if text_payload.startswith("/msg ") or text_payload.startswith("/w "):
                            parts = text_payload.split(" ", 2)
                            if len(parts) < 3:
                                error_payload = {"error": "Invalid private message format. Use /msg <recipient> <message> or /w <recipient> <message>"}
                                error_msg = create_message(MSG_TYPE_ERROR, error_payload)
                                client_socket.sendall(error_msg)
                            else:
                                recipient_username = parts[1]
                                private_text = parts[2]
                                
                                recipient_socket = None
                                # Find recipient's socket. Iterate over a copy in case clients dict changes.
                                for sock, uname in list(clients.items()):
                                    if uname == recipient_username:
                                        recipient_socket = sock
                                        break
                                
                                if recipient_socket and recipient_socket != client_socket:
                                    pm_payload = {
                                        "sender": username, # Sender's username
                                        "recipient": recipient_username,
                                        "text": private_text,
                                        "message_id": message.get("message_id"), # Pass through
                                        "send_timestamp": message.get("send_timestamp") # Pass through
                                    }
                                    # Filter out None values for id/timestamp if they weren't present
                                    pm_payload = {k: v for k, v in pm_payload.items() if v is not None}

                                    pm_message_bytes = create_message(MSG_TYPE_PRIVATE_MESSAGE, pm_payload)
                                    try:
                                        recipient_socket.sendall(pm_message_bytes)
                                    except socket.error as e:
                                        print(f"Error sending private message to {recipient_username}: {e}")
                                        fail_payload = {
                                            "recipient": recipient_username,
                                            "reason": f"Could not deliver message to {recipient_username} (network error)."
                                        }
                                        fail_msg = create_message(MSG_TYPE_PRIVATE_MESSAGE_FAILED, fail_payload)
                                        client_socket.sendall(fail_msg)
                                elif recipient_socket == client_socket:
                                    fail_payload = {
                                        "recipient": recipient_username,
                                        "reason": "You cannot send a private message to yourself."
                                    }
                                    fail_msg = create_message(MSG_TYPE_PRIVATE_MESSAGE_FAILED, fail_payload)
                                    client_socket.sendall(fail_msg)
                                else: # Recipient not found or offline
                                    fail_payload = {
                                        "recipient": recipient_username,
                                        "reason": f"User '{recipient_username}' not found or is offline."
                                    }
                                    fail_msg = create_message(MSG_TYPE_PRIVATE_MESSAGE_FAILED, fail_payload)
                                    client_socket.sendall(fail_msg)
                        else: # Regular broadcast message
                            broadcast_payload = {
                                "sender": username,
                                "text": text_payload
                            }
                            original_msg_id = message.get("message_id")
                            original_send_timestamp = message.get("send_timestamp")

                            broadcast_msg_bytes = create_message(
                                MSG_TYPE_MESSAGE,
                                broadcast_payload,
                                message_id=original_msg_id,
                                send_timestamp=original_send_timestamp
                            )
                            broadcast_message(broadcast_msg_bytes, client_socket)
                # TODO: Implement handling for MSG_TYPE_COMMAND if client-side commands are added.
                # e.g., if message.get("type") == MSG_TYPE_COMMAND:
                #           handle_client_command(username, message.get("payload"))
            else:
                # Received data that could not be parsed as a valid message.
                print(f"Received malformed data from '{username}'. Ignoring.")
                # Optionally send an error back to the client
                # error_payload = {"error": "Malformed message received."}
                # error_msg = create_message(MSG_TYPE_ERROR, error_payload)
                # client_socket.sendall(error_msg)


    except socket.error as e: # Catch socket-related errors during client communication.
        # This can happen if client disconnects abruptly or network issues.
        user_display_name = f"'{username}'" if username else f"client at {addr}"
        print(f"Socket error with {user_display_name}: {e}")
    except Exception as e: # Catch any other unexpected errors.
        user_display_name = f"'{username}'" if username else f"client at {addr}"
        print(f"Unexpected error in handle_client for {user_display_name}: {e}")
    finally:
        # --- Cleanup Phase (always executed) ---
        # This ensures the client is removed from the active list and their socket is closed,
        # regardless of how the try block was exited (normal disconnect, error, etc.).
        print(f"Cleaning up connection for {username if username else addr}...")
        remove_client(client_socket)


def start_server():
    """
    Initializes and starts the TCP chat server.
    Listens for incoming connections and spawns a new thread for each client.
    """
    global server_socket # Allow modification in finally block if needed, though it's usually local
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # Set SO_REUSEADDR to allow the server to restart quickly on the same address.
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
        server_socket.listen(5) # Start listening with a backlog of 5 connections.
        print(f"TCP Server listening on {HOST}:{PORT}")

        # Main loop to accept new client connections.
        while True: # Loop indefinitely until KeyboardInterrupt or other critical error.
            try:
                client_socket, addr = server_socket.accept() # Blocking call, waits for a new connection.
                
                # Create and start a new daemon thread to handle the client.
                # Daemon threads automatically exit when the main program (server) exits.
                thread = threading.Thread(target=handle_client, args=(client_socket, addr), daemon=True)
                thread.start()
                client_threads.append(thread) # Keep track of thread (optional, for graceful shutdown).
            except KeyboardInterrupt: # Handle Ctrl+C to shut down the server gracefully.
                print("\nServer shutting down due to KeyboardInterrupt...")
                break # Exit the accept loop.
            except socket.error as e: # Handle errors during accept (e.g., if server socket is closed).
                print(f"Error accepting new connection: {e}")
                # Depending on the error, might need to break or just log and continue.
                # If it's a critical error with the server_socket itself, the outer try/except will catch it.
                # For now, continue trying to accept.
                if not server_socket._closed: # Check if socket is still open
                    continue
                else:
                    print("Server socket closed, cannot accept new connections.")
                    break
            except Exception as e: # Catch any other unexpected errors during accept.
                print(f"Unexpected error in server accept loop: {e}")
                continue

    except socket.error as e: # Errors during server_socket.bind() or .listen().
        print(f"Fatal socket error on server startup: {e}")
    except Exception as e: # Other startup errors.
        print(f"Fatal server startup error: {e}")
    finally:
        # --- Server Shutdown Phase ---
        print("Server is shutting down. Closing all active client connections...")
        # Close all connected client sockets.
        for sock in list(clients.keys()): # Iterate over a copy
            # remove_client also closes the socket and notifies others.
            remove_client(sock)
        
        # Optionally, wait for all client threads to complete their execution.
        # This might be useful if threads perform critical cleanup.
        # Since they are daemon threads, they will be terminated if main thread exits.
        # print("Waiting for client threads to finish...")
        # for t in client_threads:
        #     if t.is_alive():
        #         t.join(timeout=1.0) # Wait for 1 second per thread.
        # print("All client threads processed.")

        if server_socket:
            print("Closing server socket.")
            server_socket.close()
        print("TCP Server has been shut down.")

if __name__ == "__main__":
    start_server()