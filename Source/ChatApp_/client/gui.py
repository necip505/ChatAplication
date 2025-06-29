"""
Provides the Graphical User Interface (GUI) for the chat client using Tkinter.

This module defines the `ChatGUI` class, which encapsulates all GUI elements
and their interactions. It communicates with the client's networking logic
through callbacks.
"""
import tkinter as tk
from tkinter import scrolledtext, simpledialog, messagebox, Listbox, END, DISABLED, NORMAL, ttk
# `threading` is not directly used in this file but client logic using this GUI is threaded.

class ChatGUI:
    """
    Manages the Tkinter-based GUI for the chat client.

    Attributes:
        root (tk.Tk): The main Tkinter window.
        message_area (scrolledtext.ScrolledText): Widget for displaying chat messages.
        user_listbox (Listbox): Widget for displaying the list of online users.
        input_field (tk.Entry): Widget for user message input.
        send_button (tk.Button): Button to send messages.
        username (str): The username of the client using this GUI.
        send_message_callback (callable): Function to call when user sends a message.
        on_close_callback (callable): Function to call when the GUI window is closed.
        get_username_callback (callable): Function to retrieve the current username.
    """
    def __init__(self, send_message_callback: callable, on_close_callback: callable, get_username_callback: callable):
        """
        Initializes the ChatGUI.

        Args:
            send_message_callback (callable): A function that takes a message string
                as input and handles sending it (e.g., to the server).
            on_close_callback (callable): A function to be called when the GUI window
                is requested to close (e.g., by clicking the 'X' button). This
                should trigger client disconnection logic.
            get_username_callback (callable): A function that returns the current
                client's username. Used for display purposes (e.g., window title).
        """
        self.send_message_callback = send_message_callback
        self.on_close_callback = on_close_callback
        self.get_username_callback = get_username_callback

        self.root = tk.Tk()
        self.root.title("Chat Client - Not Authenticated") # Initial title
        self.root.geometry("800x600") # Set a default window size
        self.root.configure(bg="#f0f0f0") # Light grey background for the root window
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing) # Handle OS window close button.

        self.username = "Not Set" # Will be updated after successful authentication via prompt_username.

        # Define a default font
        default_font = ("Segoe UI", 10)
        bold_font = ("Segoe UI", 10, "bold")

        # --- GUI Layout ---
        # Main frame to hold message area and user list side-by-side
        main_content_frame = tk.Frame(self.root, bg="#f0f0f0", padx=10, pady=10)
        main_content_frame.pack(fill=tk.BOTH, expand=True)
        
        # Message display area
        self.message_area = scrolledtext.ScrolledText(main_content_frame, wrap=tk.WORD, state=DISABLED, height=20, width=60, font=default_font, relief=tk.SUNKEN, borderwidth=1)
        self.message_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))
        
        # User list display area
        user_list_frame = tk.Frame(main_content_frame, width=180, bg="#e0e0e0", relief=tk.SUNKEN, borderwidth=1) # Slightly darker frame for user list
        user_list_label = tk.Label(user_list_frame, text="Users Online:", font=bold_font, bg="#e0e0e0", anchor='w')
        user_list_label.pack(side=tk.TOP, anchor='w', padx=5, pady=(5,2))
        self.user_listbox = Listbox(user_list_frame, height=15, width=25, font=default_font, relief=tk.FLAT, borderwidth=0, selectbackground="#c0c0c0")
        self.user_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=(0,5))
        user_list_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(0,0)) # No right padding for the frame itself
        
        # Input field and send button frame
        input_controls_frame = tk.Frame(self.root, bg="#f0f0f0", padx=10, pady=10)
        input_controls_frame.pack(fill=tk.X)
        
        self.input_field = tk.Entry(input_controls_frame, width=70, font=default_font, relief=tk.SUNKEN, borderwidth=1)
        self.input_field.bind("<Return>", self._send_message_event) # Allow sending with Enter key.
        self.input_field.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10), ipady=4) # ipady for internal padding

        self.send_button = tk.Button(input_controls_frame, text="Send", command=self._send_message_event, font=default_font, bg="#d0d0d0", relief=tk.RAISED, borderwidth=1, padx=10)
        self.send_button.pack(side=tk.RIGHT)

        # --- Text Area Styling Tags ---
        # These tags are used to color different types of messages.
        # Define base font for tags
        tag_font_family = "Segoe UI"
        tag_font_size = 10

        # User message: Sender bold, then message
        self.message_area.tag_config("user_sender", font=(tag_font_family, tag_font_size, "bold"), foreground="#000080") # Navy Blue
        self.message_area.tag_config("user_text", font=(tag_font_family, tag_font_size), foreground="#333333")

        # Own message: Sender bold (You), then message
        self.message_area.tag_config("own_sender", font=(tag_font_family, tag_font_size, "bold"), foreground="#800080") # Purple
        self.message_area.tag_config("own_text", font=(tag_font_family, tag_font_size), foreground="#500050") # Darker Purple

        # System message: Different color, italic
        self.message_area.tag_config("system_message", font=(tag_font_family, tag_font_size, "italic"), foreground="#006400") # Dark Green

        # Error message: Red, bold prefix
        self.message_area.tag_config("error_prefix", font=(tag_font_family, tag_font_size, "bold"), foreground="#CC0000") # Bright Red
        self.message_area.tag_config("error_text", font=(tag_font_family, tag_font_size), foreground="#CC0000")

        # Private message: Sender bold, distinct color, italic message
        self.message_area.tag_config("private_sender", font=(tag_font_family, tag_font_size, "bold"), foreground="#FF00FF") # Magenta
        self.message_area.tag_config("private_text", font=(tag_font_family, tag_font_size, "italic"), foreground="#DD00DD") # Darker Magenta


    def _send_message_event(self, event=None): # `event` arg allows binding to <Return> key.
        """
        Handles the event of sending a message (either by button click or Enter key).
        Retrieves text from the input field and calls the `send_message_callback`.
        """
        message = self.input_field.get().strip() # Get and strip whitespace.
        if message: # Only send if message is not empty.
            self.send_message_callback(message)
            self.input_field.delete(0, tk.END) # Clear the input field after sending.
            # Note: Own messages are typically displayed when echoed back by the server
            # or can be displayed optimistically by the client logic calling display_message.

    def _insert_text_with_tag(self, text_parts: list):
        """
        Helper method to insert text into message_area with multiple tags and auto-scroll.
        text_parts is a list of tuples, where each tuple is (text_segment, tag_name_or_list_of_tags).
        """
        if not self.root or not self.root.winfo_exists(): return # Avoid error if GUI is closing
        self.message_area.configure(state=NORMAL)
        for text_segment, tags in text_parts:
            self.message_area.insert(tk.END, text_segment, tags)
        self.message_area.insert(tk.END, "\n") # Add newline after the full message
        self.message_area.configure(state=DISABLED)
        self.message_area.yview(tk.END) # Auto-scroll to the latest message.

    def display_message(self, sender: str, message: str, is_own: bool = False):
        """
        Displays a standard chat message in the message area.
        Own messages can be styled differently.

        Args:
            sender (str): The username of the message sender.
            message (str): The content of the message.
            is_own (bool): True if the message is from the current client, False otherwise.
        """
        sender_tag = "own_sender" if is_own else "user_sender"
        text_tag = "own_text" if is_own else "user_text"
        
        sender_display = f"[{sender}{' (You)' if is_own else ''}]"
        
        text_parts = [
            (f"{sender_display}: ", sender_tag),
            (message, text_tag)
        ]
        self._insert_text_with_tag(text_parts)

    def display_system_message(self, message: str):
        """
        Displays a system message (e.g., user join/leave, server notices) in the message area.

        Args:
            message (str): The system message content.
        """
        text_parts = [
            ("[SYSTEM]: ", "system_message"), # Assuming system_message tag handles prefix style
            (message, "system_message")
        ]
        self._insert_text_with_tag(text_parts)

    def display_error_message(self, message: str):
        """
        Displays an error message in the message area.

        Args:
            message (str): The error message content.
        """
        text_parts = [
            ("[ERROR]: ", "error_prefix"),
            (message, "error_text")
        ]
        self._insert_text_with_tag(text_parts)
        # For critical errors, a modal dialog might also be useful:
        # messagebox.showerror("Chat Error", message, parent=self.root)

    def display_private_message(self, sender_or_recipient: str, message: str, is_own: bool):
        """
        Displays a private message in the message area.
        If is_own is True, it implies this client sent the message (sender_or_recipient would be the recipient).
        If is_own is False, it implies this client received the message (sender_or_recipient is the sender).
        Note: Current client logic calls this with is_own=False for received PMs.
        """
        sender_display_text = ""
        if is_own:
            # This client sent the PM. sender_or_recipient is the recipient.
            sender_display_text = f"[PM to {sender_or_recipient}]"
        else:
            # This client received the PM. sender_or_recipient is the sender.
            sender_display_text = f"[PM from {sender_or_recipient}]"

        text_parts = [
            (f"{sender_display_text}: ", "private_sender"),
            (message, "private_text")
        ]
        self._insert_text_with_tag(text_parts)

    def update_user_list(self, users: list):
        """
        Updates the list of online users displayed in the user listbox.

        Args:
            users (list): A list of usernames (str) of currently online users.
        """
        if not self.root or not self.root.winfo_exists(): return

        self.user_listbox.delete(0, END) # Clear the current list.
        sorted_users = sorted(list(set(users))) # Ensure unique names and sort alphabetically.
        
        # Populate the listbox.
        for user in sorted_users:
            display_user = user
            # Optionally, highlight the current client's username.
            # if user == self.username:
            #     display_user = f"{user} (You)"
            #     self.user_listbox.insert(END, display_user)
            #     self.user_listbox.itemconfig(END, {'fg': 'purple', 'font': ('TkDefaultFont', 9, 'bold')})
            # else:
            self.user_listbox.insert(END, display_user)
        
        # Optionally, update a status or system message about user count.
        # self.display_system_message(f"Users online: {len(sorted_users)}")

    def prompt_connection_details(self, default_host="127.0.0.1", default_port="65432") -> dict | None:
        """
        Prompts the user for username, server IP, and server port using a custom dialog.
        Updates the window title with the username upon successful entry.

        Args:
            default_host (str): Default host IP to pre-fill.
            default_port (str): Default port to pre-fill.

        Returns:
            dict | None: A dictionary {'username': str, 'host': str, 'port': int}
                         if valid details are entered, or None if cancelled.
        """
        dialog = tk.Toplevel(self.root)
        dialog.title("Login Details")
        dialog.transient(self.root) # Make it modal with respect to the root window
        dialog.grab_set() # Capture all events
        dialog.resizable(False, False)

        details = {} # To store the result

        # Center the dialog
        self.root.update_idletasks()
        dialog_width = 300
        dialog_height = 210 # Increased height for protocol field
        screen_width = dialog.winfo_screenwidth()
        screen_height = dialog.winfo_screenheight()
        x_coordinate = int((screen_width / 2) - (dialog_width / 2))
        y_coordinate = int((screen_height / 2) - (dialog_height / 2))
        dialog.geometry(f"{dialog_width}x{dialog_height}+{x_coordinate}+{y_coordinate}")


        main_frame = tk.Frame(dialog, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(main_frame, text="Username:").grid(row=0, column=0, sticky=tk.W, pady=2)
        username_entry = tk.Entry(main_frame, width=30)
        username_entry.grid(row=0, column=1, pady=2)
        username_entry.focus_set() # Set focus to username field

        tk.Label(main_frame, text="Server IP:").grid(row=1, column=0, sticky=tk.W, pady=2)
        host_entry = tk.Entry(main_frame, width=30)
        host_entry.insert(0, default_host)
        host_entry.grid(row=1, column=1, pady=2)

        tk.Label(main_frame, text="Server Port:").grid(row=2, column=0, sticky=tk.W, pady=2)
        port_entry = tk.Entry(main_frame, width=30)
        port_entry.insert(0, str(default_port))
        port_entry.grid(row=2, column=1, pady=2)

        tk.Label(main_frame, text="Protocol:").grid(row=3, column=0, sticky=tk.W, pady=2)
        protocol_var = tk.StringVar(value="tcp") # Default to TCP
        protocol_combo = ttk.Combobox(main_frame, textvariable=protocol_var, values=["tcp", "udp"], state="readonly", width=27)
        protocol_combo.grid(row=3, column=1, pady=2)


        def on_connect():
            entered_username = username_entry.get().strip()
            entered_host = host_entry.get().strip()
            entered_port_str = port_entry.get().strip()
            selected_protocol = protocol_var.get()

            if not entered_username:
                messagebox.showerror("Validation Error", "Username cannot be empty.", parent=dialog)
                return
            if not entered_host:
                messagebox.showerror("Validation Error", "Server IP cannot be empty.", parent=dialog)
                return
            if not entered_port_str:
                messagebox.showerror("Validation Error", "Server Port cannot be empty.", parent=dialog)
                return
            
            try:
                port_num = int(entered_port_str)
                if not (0 < port_num < 65536):
                    raise ValueError("Port number out of range.")
            except ValueError:
                messagebox.showerror("Validation Error", "Invalid port number. Must be an integer between 1 and 65535.", parent=dialog)
                return

            details['username'] = entered_username
            details['host'] = entered_host
            details['port'] = port_num
            details['protocol'] = selected_protocol
            
            self.username = entered_username # Update GUI's internal username
            if self.root.winfo_exists():
                self.root.title(f"Chat Client - {self.username} ({selected_protocol.upper()})")

            dialog.destroy()

        def on_cancel():
            details.clear() # Ensure no details are returned
            dialog.destroy()
            # If cancelled at login, the main application should probably exit.
            # This is handled by checking the return value of prompt_connection_details in client.py
            # If the main root window is the only one, quitting it might be an option here,
            # but it's better handled by the caller.
            # For now, just ensure the main GUI knows it was cancelled.
            if self.root.winfo_exists():
                 self.root.quit() # Signal Tkinter main loop to terminate if login is cancelled.


        button_frame = tk.Frame(main_frame)
        connect_button = tk.Button(button_frame, text="Connect", command=on_connect, width=10)
        connect_button.pack(side=tk.LEFT, padx=5)
        cancel_button = tk.Button(button_frame, text="Cancel", command=on_cancel, width=10)
        cancel_button.pack(side=tk.RIGHT, padx=5)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10) # Adjusted row
        
        dialog.protocol("WM_DELETE_WINDOW", on_cancel) # Handle dialog close button

        # Make the dialog modal and wait for it to be destroyed
        self.root.wait_window(dialog)
        
        return details if details else None

    def _on_closing(self):
        """
        Handles the event when the user tries to close the main GUI window (e.g., clicks 'X').
        Prompts for confirmation and then calls the `on_close_callback`.
        """
        if messagebox.askokcancel("Quit", "Do you want to quit the chat application?", parent=self.root):
            self.on_close_callback() # Notify the client logic (e.g., to disconnect).
            if self.root.winfo_exists(): self.root.destroy() # Close the Tkinter window.

    def start(self):
        """
        Starts the Tkinter main event loop.
        This method should be called after the GUI is fully initialized and the client
        is ready to interact. It's a blocking call.
        """
        if self.root and self.root.winfo_exists():
            self.root.mainloop()

    def close_gui(self):
        """
        Attempts to safely close the GUI. Typically called when the client is
        disconnected by the server or due to a critical error.
        Disables input fields and schedules the window to destroy itself.
        """
        if not self.root or not self.root.winfo_exists(): return

        self.display_error_message("Disconnected or error. Closing GUI in 3 seconds.")
        if self.input_field: self.input_field.config(state=DISABLED)
        if self.send_button: self.send_button.config(state=DISABLED)
        
        # Schedule the window destruction to allow the user to see the message.
        self.root.after(3000, lambda: self.root.destroy() if self.root and self.root.winfo_exists() else None)


if __name__ == '__main__':
    # This block is for standalone testing or demonstration of the GUI components.
    # In the actual application, client.py or client_udp.py would instantiate and run ChatGUI.
    
    print("client/gui.py - This is the GUI module.")
    print("Run client.py or client_udp.py to start the chat application with this GUI.")

    # Example of how to run it standalone for quick visual checks:
    def dummy_send_message(message_text: str):
        """Dummy callback for sending messages during standalone GUI testing."""
        print(f"DUMMY SEND: '{message_text}'")
        # If `test_gui` is defined and available, you could call its display methods here.
        # For example, if test_gui is accessible:
        # if 'test_gui' in locals() and test_gui:
        #    test_gui.display_message("Me (Dummy)", message_text, is_own=True)

    def dummy_on_close():
        """Dummy callback for GUI close event during standalone testing."""
        print("DUMMY CLOSE: Window closing action triggered.")
        # If running a Tkinter loop for testing, you might call root.quit() or root.destroy() here.

    def dummy_get_username() -> str:
        """Dummy callback to provide a username during standalone GUI testing."""
        return "TestUserStandalone"

    # Instantiate the GUI for testing.
    test_gui = ChatGUI(
        send_message_callback=dummy_send_message,
        on_close_callback=dummy_on_close,
        get_username_callback=dummy_get_username
    )

    # Simulate the username prompt and display some test messages.
    # Note: prompt_username() might try to quit the root if cancelled.
    # For robust standalone testing, you might need to manage the Tkinter loop carefully.
    
    # print("Attempting to prompt for username for standalone GUI test...")
    # test_username_result = test_gui.prompt_username()
    #
    # if test_username_result:
    #     print(f"Standalone GUI Test: Username entered: {test_username_result}")
    #     test_gui.display_message("Alice", "Hello there, this is a test message!")
    #     test_gui.display_system_message("Bob has joined the chat.")
    #     test_gui.update_user_list(["Alice", "Bob", test_username_result])
    #     test_gui.display_error_message("This is a test error notification.")
    #     print("Starting standalone GUI test mainloop...")
    #     test_gui.start() # This will block until the GUI is closed.
    #     print("Standalone GUI test mainloop finished.")
    # else:
    #     print("Username prompt cancelled or failed. Exiting GUI test.")
    #     # If prompt_username calls root.quit(), the script might just end here.
    #     # If the root window still exists, explicitly destroy it.
    #     if test_gui.root and test_gui.root.winfo_exists():
    #         test_gui.root.destroy()
    # if not test_username:
    #     print("No username entered, exiting test.")
    # else:
    #     gui.display_system_message(f"Welcome {test_username}!")
    #     gui.display_message("Alice", "Hello there!")
    #     gui.display_system_message("Bob joined.")
    #     gui.display_error_message("This is a test error.")
    #     gui.start()
    print("client/gui.py - Run client.py to use the GUI with the chat system.")