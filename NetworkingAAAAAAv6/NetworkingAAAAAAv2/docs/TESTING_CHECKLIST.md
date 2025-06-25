# Testing Checklist - Multi-User Chat System

This checklist is designed to verify the functionality, error handling, and multi-platform compatibility of the Multi-User Chat System.

## I. Core Functionality Testing

**Test Environment Setup:**
*   [ ] Server and at least two client instances ready.
*   [ ] Test both TCP and UDP modes separately.

---
**A. Connection & Authentication (TCP & UDP)**
*   [ ] **A.1 (Server):** Server starts successfully and listens on the correct port (TCP: 65432, UDP: 65433).
*   [ ] **A.2 (Client):** Client GUI launches.
*   [ ] **A.3 (Client):** Username prompt appears.
    *   [ ] **A.3.1:** Entering a valid, unique username allows connection. (Check server log for registration).
    *   [ ] **A.3.2:** Entering an empty username shows a warning, prompts again.
    *   [ ] **A.3.3 (TCP & UDP):** Attempting to connect with a username already in use on the server results in an error message from the server, and the client is denied connection/authentication.
    *   [ ] **A.3.4:** Cancelling username prompt gracefully exits the client.
*   [ ] **A.4 (Client):** After successful authentication, a welcome message is displayed.
*   [ ] **A.5 (Client):** After successful authentication, the initial user list is displayed (showing at least the current user).

---
**B. Messaging (TCP & UDP)**
*   [ ] **B.1 (Client A -> Client B):** Client A sends a message.
    *   [ ] **B.1.1:** Message appears in Client A's GUI (as "own message").
    *   [ ] **B.1.2:** Message appears in Client B's GUI (from Client A).
    *   [ ] **B.1.3 (Server):** Server logs receipt and broadcast of the message.
*   [ ] **B.2 (Multiple Clients):** Messages sent by one client are received by all other connected clients.
*   [ ] **B.3 (Message Integrity):** Messages received are identical to messages sent (no corruption).
*   [ ] **B.4 (Empty Messages):** Client prevents sending of empty messages (or server ignores them).
*   [ ] **B.5 (Long Messages):** Test sending messages near `MAX_MSG_SIZE` (e.g., ~4000 characters). (Note: GUI input field might have practical limits before this).
*   [ ] **B.6 (Special Characters):** Messages with special characters (e.g., `!@#$%^&*()`, non-ASCII if intended) are handled correctly.

---
**C. User List and Notifications (TCP & UDP)**
*   [ ] **C.1 (Join):** When a new client (Client C) joins:
    *   [ ] **C.1.1:** Client C's user list shows all currently connected users (including itself).
    *   [ ] **C.1.2:** Existing clients (A, B) receive a "user joined" system message for Client C.
    *   [ ] **C.1.3:** Existing clients' (A, B) user lists update to include Client C.
*   [ ] **C.2 (Leave - /quit command):** Client A types `/quit` or `/disconnect`.
    *   [ ] **C.2.1 (Client A):** Client A sends appropriate leaving message (UDP: `CLIENT_LEAVING`) and GUI closes/client terminates.
    *   [ ] **C.2.2 (Server):** Server logs client departure, removes client from active list.
    *   [ ] **C.2.3 (Other Clients):** Other clients (B, C) receive a "user left" system message for Client A.
    *   [ ] **C.2.4 (Other Clients):** Other clients' (B, C) user lists update to remove Client A.
*   [ ] **C.3 (Leave - Window Close):** Client A closes GUI window.
    *   [ ] **C.3.1 (Client A):** Confirmation dialog appears. Confirming triggers disconnect.
    *   [ ] **C.3.2 (Server, Other Clients):** Same behavior as C.2.2 - C.2.4.

---
**D. UDP Specific Reliability**
*   [ ] **D.1 (ACKs - Client to Server):**
    *   [ ] **D.1.1 (Server Log):** Server logs receiving ACKs from clients for messages it sent (e.g., welcome, user list, broadcasted messages).
*   [ ] **D.2 (ACKs - Server to Client):**
    *   [ ] **D.2.1 (Client Log/GUI):** Client logs/indicates (if applicable) receipt of ACKs from server for messages it sent (e.g., auth request, chat messages, client leaving).
*   [ ] **D.3 (Retransmission - Client to Server):** (Requires simulating packet loss from client to server)
    *   [ ] **D.3.1 (Client Log):** Client logs retransmission attempts if server ACK is not received.
    *   [ ] **D.3.2 (Server Log):** Server eventually receives message (if retransmissions succeed).
    *   [ ] **D.3.3 (Client Log):** Client logs "max retries reached" if all retransmissions fail for a critical message (e.g., initial auth).
*   [ ] **D.4 (Retransmission - Server to Client):** (Requires simulating packet loss from server to client)
    *   [ ] **D.4.1 (Server Log):** Server logs retransmission attempts if client ACK is not received.
    *   [ ] **D.4.2 (Client GUI/Log):** Client eventually receives message.
    *   [ ] **D.4.3 (Server Log):** Server logs "max retries reached" if all retransmissions fail. (Verify server handles this gracefully, e.g., stops trying for that client for that message, or eventually times out the client).
*   [ ] **D.5 (Duplicate Packet Handling):**
    *   [ ] **D.5.1 (Server):** If server receives duplicate client message (same seq_num), it ACKs but doesn't re-process/re-broadcast.
    *   [ ] **D.5.2 (Client):** If client receives duplicate server message, it ACKs but doesn't re-display/re-process.

---
## II. Error Handling and Robustness

*   [ ] **E.1 (Server Down - Client Startup):** Client attempts to connect when the server is not running.
    *   [ ] **E.1.1:** Client GUI displays an appropriate error message (e.g., "Connection refused", "Host unreachable").
    *   [ ] **E.1.2:** Client exits gracefully or allows retry.
*   [ ] **E.2 (Server Crash/Stop - Mid-Session):** Server is stopped while clients are connected.
    *   [ ] **E.2.1 (Clients):** Clients detect disconnection (e.g., socket error, timeout on send/recv).
    *   [ ] **E.2.2 (Clients):** Client GUIs display an error message about disconnection.
    *   [ ] **E.2.3 (Clients):** Input fields are disabled; clients can be closed.
*   [ ] **E.3 (Client Crash/Abrupt Disconnect - Mid-Session):** One client process is killed abruptly.
    *   [ ] **E.3.1 (Server - TCP):** Server detects disconnection (e.g., `recv` returns empty, `send` fails), calls `remove_client`.
    *   [ ] **E.3.2 (Server - UDP):** Server eventually stops receiving messages/ACKs. Retransmissions to this client will fail. (Verify server eventually times out/cleans up this client if no `CLIENT_LEAVING` is received - this might require more advanced timeout logic not yet fully implemented).
    *   [ ] **E.3.3 (Other Clients):** Other clients are notified that the user has left (for TCP immediately, for UDP might be delayed or depend on server timeout logic for crashed clients).
*   [ ] **E.4 (Malformed Data):** (Harder to test without custom tools)
    *   [ ] **E.4.1 (Server/Client):** If malformed JSON or non-JSON data is received, it's logged and ignored, system remains stable.
*   [ ] **E.5 (Network Interruption - Temporary):** (Requires network emulation)
    *   [ ] **E.5.1 (TCP):** TCP handles retransmissions; connection ideally recovers.
    *   [ ] **E.5.2 (UDP):** Custom reliability handles retransmissions; connection ideally recovers. Messages might be delayed.

---
## III. Multi-Platform Testing

*   **Goal:** Verify the application runs and core features work on at least two different operating systems.
*   **Recommended OS Combinations:**
    *   Windows and Linux (e.g., Ubuntu)
    *   Windows and macOS
    *   Linux and macOS

*   **Test Procedure:**
    1.  [ ] **Setup:** Install Python 3.x on the target OS.
    2.  [ ] **Transfer Project:** Copy the project files to the target OS.
    3.  [ ] **Run Server:** Start the server (TCP then UDP) on one OS.
    4.  [ ] **Run Client(s):** Start client(s) (TCP then UDP) on the same OS and/or different OS.
    5.  [ ] **Execute Key Scenarios:** Perform a subset of tests from Section I (Core Functionality), focusing on:
        *   [ ] Connection and authentication.
        *   [ ] Sending and receiving messages between clients (cross-platform if possible).
        *   [ ] User list updates (join/leave).
        *   [ ] GUI responsiveness and basic interaction.
        *   [ ] Graceful disconnect using `/quit` and window close.
    6.  [ ] **Note any OS-specific issues:** (e.g., GUI rendering differences if significant, path issues, different error messages for network conditions).

---
**Notes:**
*   Mark each item as Pass (P), Fail (F), or Not Applicable (N/A).
*   For Failures, provide details on the issue observed and steps to reproduce.
*   UDP reliability tests (D.3, D.4, E.5.2) might require tools to simulate packet loss/latency (e.g., `tc` on Linux, Clumsy on Windows, or manual network cable pulls for extreme tests).