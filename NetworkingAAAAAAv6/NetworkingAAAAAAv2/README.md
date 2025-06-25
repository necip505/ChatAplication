# Multi-User Chat System

This project implements a multi-user chat system supporting communication via both TCP and UDP sockets. It features a custom JSON-based message protocol, custom reliability mechanisms (sequence numbers, acknowledgments, retransmissions) over UDP, server-mediated network topology discovery (user lists), and a Tkinter-based GUI for user interaction.

## Project Structure

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
│   ├── TECHNICAL_DOCUMENTATION.md
│   ├── USER_MANUAL.md
│   ├── PERFORMANCE_ANALYSIS.md  # Outline for performance report
│   └── TESTING_CHECKLIST.md
└── README.md                   # This file
```

## Features Implemented

*   **Multi-user chat functionality:** Supports multiple clients connecting simultaneously.
*   **Custom Message Protocol:** JSON-based protocol defined in `common/protocol.py`.
*   **Dual Protocol Support:**
    *   **TCP-based communication:** Reliable, ordered message delivery.
    *   **UDP-based communication:** With custom reliability layer (ACKs, sequence numbers, retransmissions, graceful disconnect).
*   **Network Topology Discovery:** Server-mediated user list displayed in client GUI, showing currently online users.
*   **GUI for User Interaction:** Tkinter-based graphical interface for sending/receiving messages and viewing users.
*   **Basic Authentication:** Username-based registration with the server.
*   **Dynamic User List Updates:** GUI reflects users joining and leaving in real-time.

## Setup and Usage

For detailed setup and usage instructions, please refer to the [User Manual](./docs/USER_MANUAL.md).

## Technical Documentation

Detailed information about the project architecture, design decisions, protocol specifications, and implementation details can be found in the [Technical Documentation](./docs/TECHNICAL_DOCUMENTATION.md).

## Performance Analysis Report

An outline for conducting performance analysis and structuring the report is available at [Performance Analysis Outline](./docs/PERFORMANCE_ANALYSIS.md). (Actual report to be completed by the user).

## Testing

A comprehensive checklist for functionality, error handling, and multi-platform testing is available at [Testing Checklist](./docs/TESTING_CHECKLIST.md).

## Demo Video

(Link to demo video - TBD by user)