print("DEBUG: client.py script execution started - TOP OF FILE") # DEBUG LINE
"""
TCP Chat Client for the Multi-User Chat System.

This client connects to the TCP server, provides a Tkinter-based GUI for user interaction,
handles message sending/receiving, and manages the display of online users.
Network communication (receiving messages) is handled in a separate thread to keep the
GUI responsive.
"""

import socket
print("DEBUG: import socket - done") # DEBUG
import threading
print("DEBUG: import threading - done") # DEBUG
import sys
print("DEBUG: import sys - done") # DEBUG
import os
print("DEBUG: import os - done") # DEBUG
import time # For safe GUI updates and timestamps
print("DEBUG: import time - done") # DEBUG
import uuid # For generating unique message IDs
print("DEBUG: import uuid - done") # DEBUG
import csv # For structured logging
print("DEBUG: import csv - done") # DEBUG
print("DEBUG: Standard library imports complete") # DEBUG

# Adjust the path to import from the common directory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
print("DEBUG: sys.path modified") # DEBUG
from common.protocol import create_message, parse_message, MAX_MSG_SIZE
from common.protocol import MSG_TYPE_MESSAGE, MSG_TYPE_AUTH_REQUEST, MSG_TYPE_AUTH_RESPONSE
from common.protocol import MSG_TYPE_USER_JOINED, MSG_TYPE_USER_LEFT, MSG_TYPE_SYSTEM, MSG_TYPE_ERROR, MSG_TYPE_USER_LIST
from common.protocol import MSG_TYPE_PRIVATE_MESSAGE, MSG_TYPE_PRIVATE_MESSAGE_FAILED
print("DEBUG: common.protocol imports complete") # DEBUG

from client.gui import ChatGUI # Import the GUI class
print("DEBUG: client.gui import complete") # DEBUG

SERVER_HOST = '127.0.0.1' # Connect to localhost by default
SERVER_PORT = 65432

# Event to signal all threads (e.g., receive_messages) to terminate.
stop_event = threading.Event()

# Global variable for the client's socket connection.
client_socket = None

# Global variable for the ChatGUI instance.
gui = None

# Global variable to store the authenticated username of this client.
username_global = "User"

# Global set to store usernames of currently online users, updated from server messages.
current_users_set = set()

# Global variable for latency log file
latency_log_file_tcp = None
latency_log_writer_tcp = None
latency_log_file_header_tcp = ['log_timestamp', 'message_id', 'sender_username', 'receiver_username', 'protocol', 'latency_ms']

def setup_latency_logger_tcp(username: str):
    """Initializes the CSV logger for TCP latency data."""
    global latency_log_file_tcp, latency_log_writer_tcp
    filename = f"latency_tcp_client_{username.replace(' ', '_')}.csv"
    # Check if file exists to write header only once
    file_exists = os.path.isfile(filename)
    try:
        # Use 'a+' to append if file exists, create if not, and allow reading (for checking if empty for header)
        latency_log_file_tcp = open(filename, 'a+', newline='')
        latency_log_writer_tcp = csv.writer(latency_log_file_tcp)
        if not file_exists or os.path.getsize(filename) == 0: # Write header if new file or empty
            latency_log_writer_tcp.writerow(latency_log_file_header_tcp)
            latency_log_file_tcp.flush() # Ensure header is written immediately
        print(f"TCP Latency log will be written to: {filename}")
    except IOError as e:
        print(f"Error opening TCP latency log file {filename}: {e}")
        latency_log_file_tcp = None # Ensure it's None if open fails
        latency_log_writer_tcp = None

def log_latency_tcp(msg_id: str, sender: str, receiver: str, latency: float):
    """Logs a single latency record to the CSV file for TCP."""
    if latency_log_writer_tcp and latency_log_file_tcp:
        try:
            log_ts = time.strftime('%Y-%m-%d %H:%M:%S') + f".{int(time.time()*1000)%1000:03d}"
            latency_log_writer_tcp.writerow([log_ts, msg_id, sender, receiver, "TCP", f"{latency:.2f}"])
            latency_log_file_tcp.flush() # Ensure data is written to disk
        except Exception as e:
            print(f"Error writing to TCP latency log: {e}")

def close_latency_logger_tcp():
    """Closes the TCP latency log file."""
    global latency_log_file_tcp
    if latency_log_file_tcp:
        try:
            latency_log_file_tcp.close()
            latency_log_file_tcp = None
            print("TCP Latency log file closed.")
        except Exception as e:
            print(f"Error closing TCP latency log: {e}")


def receive_messages():
    """
    Continuously listens for messages from the TCP server in a dedicated thread.
    Parses received messages and updates the GUI accordingly (e.g., displaying
    chat messages, system notifications, user list changes).

    This function is designed to run in a background thread to prevent blocking
    the main GUI thread. It terminates when `stop_event` is set.
    """
    global client_socket, gui, stop_event, current_users_set, username_global

    while not stop_event.is_set() and client_socket:
        try:
            # Attempt to receive data from the server. This is a blocking call.
            data = client_socket.recv(MAX_MSG_SIZE)
            if not data: # An empty data string usually indicates the server closed the connection.
                if not stop_event.is_set() and gui:
                    # Ensure GUI updates are thread-safe if not already handled by display_error_message
                    gui.root.after(0, lambda: gui.display_error_message("Disconnected from server (connection closed by server)."))
                stop_event.set() # Signal other parts of the client to stop.
                break # Exit the listening loop.

            message = parse_message(data)
            if message and gui: # Ensure message is valid and GUI is available.
                msg_type = message.get("type")
                payload = message.get("payload", {}) # Default to empty dict for safety

                # Schedule GUI updates on the main Tkinter thread using root.after
                # This is crucial for thread safety with Tkinter.
                if msg_type == MSG_TYPE_MESSAGE:
                    sender = payload.get("sender", "Unknown")
                    text = payload.get("text", "")
                    is_own = (sender == username_global) # This client sent the message

                    # Latency calculation for non-own messages
                    # Own messages are displayed optimistically and also echoed by server;
                    # we only care about latency for messages from others.
                    if not is_own:
                        print(f"DEBUG_TCP: Received message from other. Sender: {sender}, Full Message: {message}") # DEBUG LINE
                        original_send_timestamp = message.get("send_timestamp")
                        msg_id = message.get("message_id")
                        print(f"DEBUG_TCP: Extracted ts={original_send_timestamp}, id={msg_id}") # DEBUG LINE
                        if original_send_timestamp and msg_id:
                            receive_time = time.time()
                            latency = (receive_time - original_send_timestamp) * 1000 # milliseconds
                            log_latency_tcp(msg_id, sender, username_global, latency)
                        else: # DEBUG LINE
                            print(f"DEBUG_TCP: Missing timestamp or msg_id for latency calc. TS: {original_send_timestamp}, ID: {msg_id}") # DEBUG LINE
                    
                    gui.root.after(0, lambda s=sender, t=text, own=is_own: gui.display_message(s, t, is_own=own))
                elif msg_type == MSG_TYPE_SYSTEM:
                    sys_msg = payload.get('message', '')
                    gui.root.after(0, lambda m=sys_msg: gui.display_system_message(m))
                elif msg_type == MSG_TYPE_USER_LIST:
                    users = payload.get("users", [])
                    current_users_set.clear()
                    current_users_set.update(users)
                    gui.root.after(0, lambda u_list=list(current_users_set): gui.update_user_list(u_list))
                elif msg_type == MSG_TYPE_USER_JOINED:
                    joined_user = payload.get('username')
                    if joined_user:
                        current_users_set.add(joined_user)
                        gui.root.after(0, lambda ju=joined_user, u_list=list(current_users_set): (
                            gui.display_system_message(f"{ju} has joined the chat."),
                            gui.update_user_list(u_list)
                        ))
                elif msg_type == MSG_TYPE_USER_LEFT:
                    left_user = payload.get('username')
                    if left_user and left_user in current_users_set:
                        current_users_set.remove(left_user)
                        gui.root.after(0, lambda lu=left_user, u_list=list(current_users_set): (
                            gui.display_system_message(f"{lu} has left the chat."),
                            gui.update_user_list(u_list)
                        ))
                elif msg_type == MSG_TYPE_AUTH_REQUEST: # Server should not send this after initial auth.
                    auth_req_msg = payload.get('message', 'Authentication requested unexpectedly.')
                    gui.root.after(0, lambda m=auth_req_msg: gui.display_system_message(f"Server: {m}"))
                elif msg_type == MSG_TYPE_ERROR:
                    error_text = payload.get('error', 'Unknown server error.')
                    gui.root.after(0, lambda err=error_text: gui.display_error_message(err))
                    if "Authentication failed" in error_text or "Invalid or duplicate username" in error_text:
                        gui.root.after(0, lambda: gui.display_error_message("Critical authentication error. Disconnecting."))
                        stop_event.set()
                        break
                elif msg_type == MSG_TYPE_PRIVATE_MESSAGE:
                    sender = payload.get("sender", "Unknown")
                    text = payload.get("text", "")
                    # Display as: "[PM from Sender]: Text" or similar
                    # is_own is False because this client is the recipient, not the sender of this PM
                    gui.root.after(0, lambda s=sender, t=text: gui.display_private_message(s, t, is_own=False))
                elif msg_type == MSG_TYPE_PRIVATE_MESSAGE_FAILED:
                    recipient = payload.get("recipient", "Unknown")
                    reason = payload.get("reason", "Failed to send private message.")
                    # Display as a system/error message
                    gui.root.after(0, lambda rcp=recipient, rsn=reason: gui.display_error_message(f"PM to {rcp} failed: {rsn}"))
                else:
                    unhandled_msg_payload = payload # Capture payload for lambda
                    gui.root.after(0, lambda mt=msg_type, p=unhandled_msg_payload: gui.display_system_message(f"Received unhandled message type {mt}: {p}"))
            
            elif not message and not stop_event.is_set() and gui:
                gui.root.after(0, lambda: gui.display_error_message("Received malformed message from server."))

        except socket.timeout: # socket.timeout can occur if client_socket.settimeout() was used.
            if not stop_event.is_set(): # Only continue if not already stopping.
                continue
            else:
                break # If stopping, exit loop.
        except ConnectionResetError: # Server or network abruptly closed connection.
            if not stop_event.is_set() and gui:
                gui.root.after(0, lambda: gui.display_error_message("Connection reset by server."))
            stop_event.set()
            break
        except socket.error as e: # Other socket errors.
            if not stop_event.is_set() and gui:
                err_msg = f"Socket error: {e}"
                gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
            stop_event.set()
            break
        except Exception as e: # Catch-all for other unexpected errors in this thread.
            if not stop_event.is_set() and gui:
                err_msg = f"Receiving error: {e}"
                gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
            stop_event.set()
            break
    
    # Loop cleanup messages
    if gui:
        final_msg = "Disconnected. You can close the window." if stop_event.is_set() else "Receive thread stopped unexpectedly."
        if gui.root and gui.root.winfo_exists(): # Check if GUI window still exists
             gui.root.after(0, lambda m=final_msg: gui.display_system_message(m))
        # gui.close_gui() # This might be called too soon if main thread also calls it.


def gui_send_message(message_text: str):
    """
    Callback function invoked by the GUI when the user attempts to send a message
    or a command (like '/quit').

    Args:
        message_text (str): The text entered by the user in the GUI's input field.
    """
    global client_socket, stop_event, gui, username_global

    if stop_event.is_set() or not client_socket:
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda: gui.display_error_message("Not connected to server."))
        return

    normalized_message = message_text.strip().lower()
    if normalized_message == '/quit' or normalized_message == '/disconnect':
        if gui and gui.root.winfo_exists():
            # For TCP, simply setting stop_event is enough. Server detects disconnect.
            # No explicit "leaving" message is sent by TCP client in this version.
            gui.root.after(0, lambda: gui.display_system_message("Disconnecting..."))
        stop_event.set() # Signal other threads (receive_messages) to stop.
                         # The main thread (gui.start()) will exit when GUI closes or stop_event is handled.
        # The on_gui_close callback (if window is closed) or finally block will handle socket closure.
        return
    
    if message_text: # Ensure message is not empty.
        try:
            msg_payload = {"text": message_text} # Basic payload
            msg_id = str(uuid.uuid4())
            current_time = time.time()
            
            # Create message with ID and timestamp for latency measurement
            message_bytes = create_message(MSG_TYPE_MESSAGE, msg_payload,
                                           message_id=msg_id, send_timestamp=current_time)
            client_socket.sendall(message_bytes) # Send the message to the server.
            
            # Optimistically display the user's own message in their GUI immediately.
            if gui and gui.root.winfo_exists():
                 gui.root.after(0, lambda mt=message_text: gui.display_message(username_global, mt, is_own=True))

        except socket.error as e:
            if gui and gui.root.winfo_exists():
                err_msg = f"Socket error while sending: {e}"
                gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
            stop_event.set() # Critical error, signal shutdown.
        except Exception as e:
            if gui and gui.root.winfo_exists():
                err_msg = f"Error sending message: {e}"
                gui.root.after(0, lambda em=err_msg: gui.display_error_message(em))
            stop_event.set() # Critical error.

def on_gui_close():
    """
    Callback function invoked when the GUI window's close button (e.g., 'X') is clicked.
    This initiates the client shutdown sequence.
    """
    global stop_event
    if gui and gui.root.winfo_exists(): # Check if GUI still exists
        # This message might not be visible if the GUI closes too quickly.
        # gui.root.after(0, lambda: gui.display_system_message("Disconnecting on window close..."))
        pass
    stop_event.set() # Signal the receive_messages thread and main logic to stop.
    # The main client loop's `finally` block will handle actual socket closure.
    # The GUI's own destroy mechanism will also be called by ChatGUI._on_closing.

def get_current_username():
    """
    Callback for the GUI to retrieve the client's current authenticated username.
    
    Returns:
        str: The current username.
    """
    global username_global
    return username_global

def start_client():
    """
    Initializes and starts the TCP chat client.
    This involves setting up the GUI, connecting to the server, handling authentication,
    and starting the message receiving thread.
    """
    global client_socket, gui, stop_event, username_global
    print("DEBUG: Entered start_client()") # DEBUG

    # 1. Initialize the GUI. Callbacks for sending messages and closing are passed.
    print("DEBUG: About to initialize ChatGUI") # DEBUG
    gui = ChatGUI(send_message_callback=gui_send_message,
                  on_close_callback=on_gui_close,
                  get_username_callback=get_current_username)
    print("DEBUG: ChatGUI initialized") # DEBUG

    # 2. Prompt for connection details (username, host, port, protocol) via the GUI.
    #    The global SERVER_HOST and SERVER_PORT (potentially set by CLI args) are passed as defaults.
    print("DEBUG: About to prompt for connection details") # DEBUG
    # Default TCP port for the dialog if not specified by CLI for TCP.
    # UDP default port is different, GUI should handle its own default if protocol changes.
    default_gui_port = str(SERVER_PORT) if SERVER_PORT else "65432" # Ensure string for GUI
    connection_details = gui.prompt_connection_details(default_host=SERVER_HOST, default_port=default_gui_port)
    print(f"DEBUG: Connection details prompt returned: {connection_details}") # DEBUG

    if not connection_details: # User cancelled or closed the dialog.
        if gui and gui.root.winfo_exists():
             # The gui.prompt_connection_details already calls root.quit() on cancel.
             pass
        print("DEBUG: Login cancelled by user.")
        return
        
    username_global = connection_details['username']
    connect_host = connection_details['host']
    connect_port = connection_details['port']
    selected_protocol = connection_details['protocol'].lower()
    
    # Update GUI title (already done by prompt_connection_details, but good to be aware)
    # if gui and gui.root.winfo_exists():
    #     gui.root.title(f"Chat Client - {username_global} ({selected_protocol.upper()})")

    if selected_protocol == "tcp":
        setup_latency_logger_tcp(username_global) # Initialize TCP logger
    elif selected_protocol == "udp":
        # For now, inform user that UDP needs to be run separately.
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda: gui.display_error_message(f"UDP selected. Please run client_udp.py for UDP connections for now."))
            gui.root.after(2000, gui.close_gui) # Close GUI after message
        print("INFO: UDP protocol selected. This script (client.py) primarily handles TCP.")
        print("INFO: For UDP, please run client_udp.py directly.")
        return # Exit client.py if UDP is chosen

    # 3. Create the client socket (only for TCP at this point in this script)
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # No explicit timeout on client_socket here; recv in thread is blocking.

    try:
        # 4. Connect to the server using details from the GUI dialog (for TCP).
        if gui: gui.root.after(0, lambda h=connect_host, p=connect_port: gui.display_system_message(f"Attempting to connect to {h}:{p} (TCP)..."))
        print(f"DEBUG: About to connect to {connect_host}:{connect_port} (TCP)") # DEBUG
        client_socket.connect((connect_host, connect_port))
        if gui: gui.root.after(0, lambda: gui.display_system_message("Connected to TCP server."))

        # --- Authentication Flow with Server (TCP) ---
        # a. Wait for the server to send an AUTH_REQUEST.
        auth_prompt_data = client_socket.recv(MAX_MSG_SIZE)
        if not auth_prompt_data: raise ConnectionAbortedError("Server closed connection during auth request.")
        auth_prompt = parse_message(auth_prompt_data)

        if auth_prompt and auth_prompt.get("type") == MSG_TYPE_AUTH_REQUEST:
            if gui:
                auth_msg_from_server = auth_prompt.get('payload',{}).get('message', 'Authenticating...')
                gui.root.after(0, lambda m=auth_msg_from_server: gui.display_system_message(f"Server: {m}"))
            
            # b. Send username as AUTH_RESPONSE.
            auth_response_payload = {"username": username_global}
            auth_response_msg = create_message(MSG_TYPE_AUTH_RESPONSE, auth_response_payload)
            client_socket.sendall(auth_response_msg)
        else:
            raise ConnectionAbortedError("Did not receive expected authentication request from server.")

        # c. Wait for server's confirmation/welcome message (or error).
        # This also implicitly confirms username validity.
        initial_server_response_data = client_socket.recv(MAX_MSG_SIZE)
        if not initial_server_response_data: raise ConnectionAbortedError("Server closed connection after auth response.")
        initial_server_response = parse_message(initial_server_response_data)

        if initial_server_response and initial_server_response.get("type") == MSG_TYPE_ERROR:
            error_detail = initial_server_response.get('payload',{}).get('error', 'Authentication failed.')
            raise ValueError(f"Authentication failed: {error_detail}") # Raise error to be caught below.
        elif initial_server_response and initial_server_response.get("type") == MSG_TYPE_SYSTEM:
            welcome_msg = initial_server_response.get('payload',{}).get('message', 'Authenticated.')
            if gui: gui.root.after(0, lambda m=welcome_msg: gui.display_system_message(m))
        elif not initial_server_response: # Should be caught by "not initial_server_response_data"
             raise ConnectionAbortedError("No response from server after sending username.")
        # Any other message type here is unexpected but will be handled by receive_messages thread.

        # 5. Start the background thread for receiving messages.
        # This thread is a daemon, so it will exit when the main thread (GUI) exits.
        receive_thread = threading.Thread(target=receive_messages, daemon=True)
        receive_thread.start()

        # 6. Start the Tkinter GUI event loop. This is a blocking call.
        # The program will stay in this loop until the GUI window is closed or an unhandled
        # exception occurs in the main thread.
        if gui: gui.start()

    except (socket.timeout, ConnectionRefusedError, ConnectionAbortedError, socket.error) as e:
        # Handle various network-related errors during connection/authentication.
        err_msg_display = f"Connection Error: {e}. Please ensure server is running and accessible."
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda em=err_msg_display: gui.display_error_message(em))
            gui.root.after(0, lambda: gui.close_gui()) # Attempt to close GUI gracefully
        else:
            print(err_msg_display) # Fallback if GUI is not available
    except ValueError as e: # Specifically for auth failure after connection
        err_msg_display = str(e)
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda em=err_msg_display: gui.display_error_message(em))
            gui.root.after(0, lambda: gui.close_gui())
        else:
            print(err_msg_display)
    except Exception as e: # Catch any other unexpected exceptions during startup.
        err_msg_display = f"An unexpected error occurred during client startup: {e}"
        if gui and gui.root.winfo_exists():
            gui.root.after(0, lambda em=err_msg_display: gui.display_error_message(em))
            gui.root.after(0, lambda: gui.close_gui())
        else:
            print(err_msg_display)
    finally:
        # --- Client Shutdown Phase ---
        stop_event.set() # Signal all threads to stop.
        
        if client_socket:
            try:
                # client_socket.shutdown(socket.SHUT_RDWR) # Graceful shutdown (optional, can cause errors if already closed)
                client_socket.close() # Ensure socket is closed.
            except socket.error:
                pass # Ignore errors if socket is already closed.
            client_socket = None
            if gui and gui.root.winfo_exists(): # Check if GUI still exists
                 gui.root.after(0, lambda: gui.display_system_message("Socket closed."))
        
        # Wait for the receive_thread to finish, but with a short timeout.
        # As it's a daemon, it might already be terminated if main thread is exiting.
        if 'receive_thread' in locals() and receive_thread.is_alive():
            receive_thread.join(timeout=0.2)

        close_latency_logger_tcp() # Ensure log file is closed on exit
        print("TCP Client has shut down.")
        # If GUI was closed by user, gui.root.destroy() was called via ChatGUI._on_closing -> on_gui_close -> stop_event.set().
        # If an error occurred, gui.close_gui() might have been called.
        # The main thread exits after this finally block if gui.start() has returned.
        
    print("DEBUG: All imports and definitions complete, just before __main__ check") # DEBUG
if __name__ == "__main__":
    if len(sys.argv) == 3:
        SERVER_HOST = sys.argv[1]
        try:
            SERVER_PORT = int(sys.argv[2])
        except ValueError:
            print(f"Invalid port number: {sys.argv[2]}. Using default {SERVER_PORT}.")
    elif len(sys.argv) > 1:
        print("Usage: python client.py [server_host] [server_port]")
        sys.exit(1)
    
    print("DEBUG: In __main__, about to call start_client()") # DEBUG
    start_client()