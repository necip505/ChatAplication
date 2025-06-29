# User Manual - Multi-User Chat System

## 1. Introduction

Welcome to the Multi-User Chat System! This application allows multiple users to connect to a central server and exchange text messages in real-time. It supports communication over both TCP (reliable by default) and UDP (with custom reliability mechanisms). Users interact with the chat through a graphical user interface (GUI).

## 2. System Requirements

*   Python 3.7 or higher.
*   Tkinter library (usually included with standard Python installations).
*   A network connection (for connecting to the server, can be localhost for local testing).

## 3. Installation

No complex installation is required beyond having Python set up.

1.  **Download or Clone the Project:**
    Obtain the project files and place them in a directory on your computer (e.g., `chat_system`).
    The expected directory structure is:
    ```
    chat_system/
    ├── client/
    │   ├── client.py       # TCP Client
    │   └── client_udp.py   # UDP Client
    │   └── gui.py
    ├── server/
    │   ├── server.py       # TCP Server
    │   └── server_udp.py   # UDP Server
    ├── common/
    │   └── protocol.py
    ├── docs/
    └── README.md
    ```

2.  **No External Libraries (Beyond Standard Python):**
    The project primarily uses Python's built-in libraries (`socket`, `threading`, `json`, `tkinter`, `os`, `sys`, `time`).

## 4. Running the Chat System

You need to run one server instance and then one or more client instances.

### 4.1. Starting the Server

You can choose to run either the TCP server or the UDP server. They operate on different ports and cannot run on the same port simultaneously.

*   **To Start the TCP Server:**
    Open a terminal or command prompt, navigate to the project's root directory (`chat_system`), and run:
    ```bash
    python server/server.py
    ```
    You should see a message like: `Server listening on 0.0.0.0:65432`

*   **To Start the UDP Server:**
    Open a terminal or command prompt, navigate to the project's root directory (`chat_system`), and run:
    ```bash
    python server/server_udp.py
    ```
    You should see a message like: `UDP Server listening on 0.0.0.0:65433`

The server will continue running, waiting for clients to connect. To stop the server, press `Ctrl+C` in its terminal window.

### 4.2. Starting the Client

You can run multiple client instances to simulate a multi-user chat. Each client will open its own GUI window.

*   **To Start the TCP Client:**
    Ensure the TCP server is running. Open a new terminal, navigate to the project directory, and run:
    ```bash
    python client/client.py [server_host] [server_port]
    ```
    *   `[server_host]` (optional): The IP address or hostname of the server. Defaults to `127.0.0.1` (localhost).
    *   `[server_port]` (optional): The port number of the TCP server. Defaults to `65432`.
    Example for local server: `python client/client.py`

*   **To Start the UDP Client:**
    Ensure the UDP server is running. Open a new terminal, navigate to the project directory, and run:
    ```bash
    python client/client_udp.py [server_host] [server_port]
    ```
    *   `[server_host]` (optional): The IP address or hostname of the server. Defaults to `127.0.0.1` (localhost).
    *   `[server_port]` (optional): The port number of the UDP server. Defaults to `65433`.
    Example for local server: `python client/client_udp.py`

### 4.3. Using the Chat Client GUI

1.  **Username:** Upon launching, the client GUI will prompt you to enter a username. This name will be visible to other users. Choose a unique username if others are already connected.
2.  **Main Window:**
    *   **Message Area:** The large central area displays chat messages, system notifications (users joining/leaving), and error messages. Your own messages are typically highlighted differently.
    *   **User List:** A panel (usually on the right) shows the list of currently online users.
    *   **Input Field:** At the bottom, type your messages here.
    *   **Send Button:** Click this (or press Enter in the input field) to send your message.
3.  **Sending Messages:** Type your message in the input field and click "Send" or press Enter.
4.  **Receiving Messages:** Messages from other users and system notifications will appear automatically in the message area.
5.  **Disconnecting/Quitting:**
    *   Type `/quit` or `/disconnect` in the message input field and send it.
    *   Alternatively, click the close button (X) on the GUI window. You'll be asked to confirm if you want to quit.

## 5. Troubleshooting

*   **Cannot Connect to Server:**
    *   Ensure the server (TCP or UDP) is running before starting the corresponding client.
    *   Verify you are using the correct server IP address and port number for the client. If running on the same machine, `127.0.0.1` (localhost) is usually correct.
    *   Check firewall settings on the server machine; they might be blocking incoming connections on the chat ports (65432 for TCP, 65433 for UDP).
*   **`ModuleNotFoundError` (e.g., `client.gui`):**
    *   This can happen if Python doesn't recognize the subdirectories as packages. Ensure `__init__.py` files (can be empty) exist in the `client/` and `common/` directories.
    *   Ensure you are running the client/server scripts from the project's root directory.
*   **UDP Issues (Messages not appearing, frequent disconnects):**
    *   UDP is inherently less reliable than TCP. While this project implements custom reliability, packet loss can still occur, especially on unstable networks.
    *   The server and client consoles print debug information about UDP sequence numbers, ACKs, and retransmissions, which can be helpful for diagnosing issues.
*   **GUI Freezes or Behaves Oddly:**
    *   This could be due to various reasons. If it persists, note down the steps to reproduce it and any error messages in the client's console.

## 6. Contact

For issues or questions regarding this chat system, please refer to the project's source or maintainer.