# Technical Documentation - Multi-User Chat System

## 1. Introduction

This document details the technical architecture, design decisions, and implementation specifics of the Multi-User Chat System. The system supports chat over both TCP and UDP (with custom reliability mechanisms), features a custom JSON-based message protocol, and provides a graphical user interface (GUI) using Tkinter.

## 2. Project Architecture

The system follows a client-server architecture.

*   **Server:**
    *   Listens for incoming client connections (TCP or UDP on different ports).
    *   Manages client state (usernames, addresses, sequence numbers for UDP).
    *   Handles message routing and broadcasting.
    *   Implements reliability for UDP communication (acknowledgments, retransmissions).
*   **Client:**
    *   Connects to the server (TCP or UDP).
    *   Provides a GUI for user interaction (sending/receiving messages, viewing users).
    *   Implements reliability for UDP communication (sending ACKs, handling retransmissions from server, retransmitting its own messages).
*   **Common Protocol Module:**
    *   Defines message types, structures, and serialization/deserialization logic used by both client and server.

### 2.1. Directory Structure

```
chat_system/
├── client/
│   ├── __init__.py
│   ├── client.py           # TCP Client Logic
│   ├── client_udp.py       # UDP Client Logic
│   └── gui.py              # Tkinter GUI Implementation
├── server/
│   ├── server.py           # TCP Server Logic
│   └── server_udp.py       # UDP Server Logic
├── common/
│   ├── __init__.py
│   └── protocol.py         # Custom message protocol definitions
├── docs/
│   ├── TECHNICAL_DOCUMENTATION.md  # This file
│   └── USER_MANUAL.md              # User manual
└── README.md               # Project overview
```

## 3. Core Components and Design Decisions

### 3.1. Networking

*   **Transport Protocols:**
    *   **TCP (`server.py`, `client.py`):** Chosen for its inherent reliability, simplifying initial development. Handles ordered, guaranteed delivery of messages. Uses standard socket programming with threading on the server to manage multiple clients.
    *   **UDP (`server_udp.py`, `client_udp.py`):** Implemented to demonstrate understanding of connectionless protocols and to build custom reliability. Operates on a different port than the TCP server.
*   **Ports:**
    *   TCP Server: Default `65432`
    *   UDP Server: Default `65433`

### 3.2. Custom Message Protocol (`common/protocol.py`)

*   **Format:** JSON was chosen for its human-readability and ease of parsing in Python. Messages are UTF-8 encoded strings.
*   **Structure:** Each message is a JSON object with a mandatory `type` field and a `payload` field (which is also an object).
    ```json
    {
        "type": "MESSAGE_TYPE_CONSTANT",
        "payload": { ... specific data ... },
        "seq_num": 123, // Optional: For UDP reliability
        "ack_num": 123  // Optional: For UDP reliability
    }
    ```
*   **Key Message Types:**
    *   `MESSAGE`: Standard chat text.
    *   `AUTH_REQUEST`, `AUTH_RESPONSE`: For username authentication.
    *   `USER_JOINED`, `USER_LEFT`, `USER_LIST`: For managing and displaying the user list.
    *   `SYSTEM`: Server-to-client system messages.
    *   `ERROR`: For communicating errors.
    *   `UDP_DATA`: Wrapper for data sent over UDP that requires reliability, contains `seq_num` and the original message in its payload.
    *   `UDP_ACK`: Used to acknowledge received `UDP_DATA` packets, contains `ack_num`.
    *   `CLIENT_LEAVING`: Sent by UDP client before disconnecting.
*   **Serialization:** `json.dumps()` and `.encode('utf-8')`.
*   **Deserialization:** `.decode('utf-8')` and `json.loads()`.

### 3.3. Reliability Mechanisms over UDP

Implemented in `server_udp.py` and `client_udp.py`.

*   **Sequence Numbers (`seq_num`):**
    *   Each `UDP_DATA` message (and the initial `AUTH_REQUEST` from client, `CLIENT_LEAVING` from client) carries a sequence number.
    *   Senders increment their sequence number for each new reliable message.
    *   Receivers use this to detect lost or duplicate packets and to ensure ordered processing (though current implementation primarily focuses on detecting duplicates and handling expected sequence).
*   **Acknowledgments (`ack_num`):**
    *   When a receiver gets a `UDP_DATA` message with `seq_num X`, it sends back a `UDP_ACK` message with `ack_num X`.
*   **Retransmission:**
    *   **Sender-Side:**
        1.  When a reliable message is sent, it's stored in an `ack_pending` dictionary with a timestamp and retry count.
        2.  A separate thread (`check_retransmissions` on server, `check_client_retransmissions` on client) periodically checks this dictionary.
        3.  If an ACK for a message is not received within `RETRANSMISSION_TIMEOUT`, the message is resent.
        4.  Retries occur up to `MAX_RETRIES`. If still unacknowledged, the sender gives up on that specific message.
    *   **Receiver-Side:**
        1.  If a duplicate packet (same `seq_num` as an already processed one) is received, the receiver re-sends the ACK for that `seq_num` but does not re-process the data.
        2.  If an out-of-order packet is received (higher `seq_num` than expected), the current basic implementation ignores it. A more advanced system might buffer such packets.
*   **Client Disconnection:** UDP clients send a `CLIENT_LEAVING` message (reliably) before shutting down. The server ACKs this, removes the client, and notifies others.

### 3.4. GUI (`client/gui.py`)

*   **Framework:** Tkinter (Python's built-in GUI library) was chosen for simplicity and not requiring external dependencies.
*   **Structure:**
    *   Main window with a scrolled text area for messages, an input field, and a send button.
    *   A listbox displays online users.
*   **Threading:** GUI updates initiated by the network receiving thread (which runs separately) are scheduled onto Tkinter's main event loop using `root.after(0, ...)` to ensure thread safety.
*   **Key Features:**
    *   Displays incoming messages, system notifications, and errors with distinct styling.
    *   Allows users to type and send messages.
    *   Prompts for username on startup.
    *   Updates the user list dynamically.
    *   Handles window close events to trigger disconnection.

### 3.5. Server-Side Concurrency (TCP & UDP)

*   **TCP Server (`server.py`):** Uses `threading` to handle each connected TCP client in a separate thread. This allows the server to manage multiple clients simultaneously without blocking.
*   **UDP Server (`server_udp.py`):**
    *   The main loop uses `recvfrom()` which is blocking. Message handling (`handle_udp_message`) is currently done in the main server thread. For very high loads, this could be a bottleneck, and offloading to worker threads might be considered.
    *   A separate daemon thread (`check_retransmissions`) handles UDP retransmission logic concurrently.

### 3.6. Network Topology Discovery

*   Implemented as a server-mediated user list.
*   When a client connects (TCP or UDP), the server sends the current list of usernames.
*   As users join or leave, `USER_JOINED` and `USER_LEFT` messages are broadcast, allowing clients to update their local view of online users.
*   This provides clients with knowledge of other concurrently connected users (by username).

## 4. Algorithms and Data Structures

*   **Server `clients` Dictionary (TCP):** `socket: username` mapping.
*   **Server `clients` Dictionary (UDP):** `address (ip, port): client_info_dict`
    *   `client_info_dict`: `{"username": str, "last_ack_num": int, "next_expected_seq_num": int, "ack_pending": {seq: (timestamp, data, retries)}, "server_to_client_seq_num": int}`
*   **Client `ack_pending_on_server` Dictionary (UDP):** `{seq: (timestamp, data, retries)}` for messages client sent to server.
*   **Sequence Number Management:** Simple incrementing counters on both client and server for their respective reliable message streams.
*   **User List Management (Client):** `current_users_set` (TCP client) and `current_users_set_udp` (UDP client) are Python `set` objects for efficient addition/removal of usernames.

## 5. Potential Future Enhancements

*   **More Robust UDP Reliability:**
    *   Congestion control (e.g., AIMD, windowing).
    *   Flow control.
    *   Selective acknowledgments (SACK) for more efficient retransmission.
    *   Buffering and processing of out-of-order packets.
*   **Secure Authentication:** Implement proper password-based authentication, possibly with hashing and salting.
*   **Encryption:** Add TLS/SSL for TCP or DTLS for UDP to encrypt communication.
*   **Advanced Chat Features:** Private messages, channels/rooms, file sharing.
*   **Scalability Improvements for UDP Server:** Consider using asynchronous I/O (e.g., `asyncio`) or a thread pool for handling incoming UDP messages if the current single-threaded `recvfrom` loop becomes a bottleneck.
*   **Detailed Network Topology:** If required, allow clients to query for more details like IP/port of other users (with security/privacy considerations).
*   **NAT Traversal:** For direct P2P communication if that feature were added (e.g., STUN/TURN).

This document provides a snapshot of the system's technical design as of its current implementation.