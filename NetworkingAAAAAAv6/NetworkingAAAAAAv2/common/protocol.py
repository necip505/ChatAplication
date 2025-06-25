"""
Defines the custom message protocol for the chat system.
"""

import json

# Message Type Constants
MSG_TYPE_MESSAGE = "MESSAGE"  # Standard text message from a user
MSG_TYPE_COMMAND = "COMMAND"  # A command from a user (e.g., /list, /quit)
MSG_TYPE_SYSTEM = "SYSTEM"    # A system message from the server (e.g., user join/leave notification)
MSG_TYPE_ERROR = "ERROR"      # An error message from the server
MSG_TYPE_AUTH_REQUEST = "AUTH_REQUEST" # Server requests authentication
MSG_TYPE_AUTH_RESPONSE = "AUTH_RESPONSE" # Client sends authentication (e.g., username)
MSG_TYPE_USER_JOINED = "USER_JOINED" # Notification that a user has joined
MSG_TYPE_USER_LEFT = "USER_LEFT"   # Notification that a user has left
MSG_TYPE_USER_LIST = "USER_LIST"   # Server sends a list of connected users

# UDP Specific Message Types
MSG_TYPE_UDP_DATA = "UDP_DATA"    # For data packets sent over UDP requiring reliability
MSG_TYPE_UDP_ACK = "UDP_ACK"      # For acknowledgment packets
MSG_TYPE_CLIENT_LEAVING = "CLIENT_LEAVING" # Client informs server it's disconnecting

MSG_TYPE_PRIVATE_MESSAGE = "PRIVATE_MESSAGE" # For sending a private message
MSG_TYPE_PRIVATE_MESSAGE_FAILED = "PRIVATE_MESSAGE_FAILED" # If private message delivery fails
# Maximum message size (example, can be adjusted for network conditions and typical message content)
MAX_MSG_SIZE = 4096 # bytes, chosen as a common buffer size, can be tuned.

def create_message(msg_type: str, payload: dict,
                   seq_num: int = None, ack_num: int = None,
                   message_id: str = None, send_timestamp: float = None) -> bytes:
    """
    Creates a message string (as bytes) to be sent over the network.
    Messages are structured as JSON objects before being UTF-8 encoded.

    Args:
        msg_type (str): The type of the message (e.g., MSG_TYPE_MESSAGE).
        payload (dict): A dictionary containing the message-specific data.
        seq_num (int, optional): Sequence number, primarily for reliable UDP messages.
        ack_num (int, optional): Acknowledgment number, primarily for UDP ACKs.
        message_id (str, optional): A unique identifier for the message, used for tracking (e.g., latency measurement).
        send_timestamp (float, optional): The timestamp (e.g., `time.time()`) when the message
                                          was created/sent, for latency measurement.
    
    Returns:
        bytes: The JSON message encoded as UTF-8 bytes.
               Returns an error message (as bytes) if serialization fails.

    Raises:
        TypeError: If msg_type is not a string, payload is not a dict,
                   or if seq_num/ack_num are not integers, or message_id is not str,
                   or send_timestamp is not float, when provided.
    """
    if not isinstance(msg_type, str):
        raise TypeError("msg_type must be a string")
    if not isinstance(payload, dict):
        raise TypeError("payload must be a dictionary")

    message = {
        "type": msg_type,
        "payload": payload
    }
    if seq_num is not None:
        if not isinstance(seq_num, int):
            raise TypeError("seq_num must be an integer")
        message["seq_num"] = seq_num
    if ack_num is not None:
        if not isinstance(ack_num, int):
            raise TypeError("ack_num must be an integer")
        message["ack_num"] = ack_num
    if message_id is not None:
        if not isinstance(message_id, str):
            raise TypeError("message_id must be a string")
        message["message_id"] = message_id
    if send_timestamp is not None:
        if not isinstance(send_timestamp, float):
            raise TypeError("send_timestamp must be a float")
        message["send_timestamp"] = send_timestamp
        
    try:
        return json.dumps(message).encode('utf-8')
    except (TypeError, ValueError) as e:
        print(f"Error encoding message: {e}")
        # Fallback or error handling for non-serializable payload
        error_payload = {"error": "Failed to serialize message payload"}
        error_message = {
            "type": MSG_TYPE_ERROR,
            "payload": error_payload
        }
        return json.dumps(error_message).encode('utf-8')


def parse_message(data: bytes) -> dict | None:
    """
    Parses a received byte string (expected to be a UTF-8 encoded JSON message)
    into a Python dictionary.

    Args:
        data (bytes): The raw byte string received from the network.

    Returns:
        dict | None: A dictionary representing the parsed message if successful.
                     The dictionary will include 'type', 'payload', and optionally
                     'seq_num', 'ack_num', 'message_id', and 'send_timestamp'
                     if they were present in the original message.
                     Returns None if parsing fails (e.g., invalid JSON, decoding error,
                     missing mandatory fields 'type' or 'payload').
    """
    if not data: # Handle empty data explicitly
        print("Error: Received empty data for parsing.")
        return None
    try:
        message_str = data.decode('utf-8')
        message = json.loads(message_str)
        # Basic validation: 'type' and 'payload' are mandatory for our core messages.
        # Other fields like seq_num, ack_num, message_id, send_timestamp are optional
        # and will be checked by the consuming logic if needed.
        if "type" in message and "payload" in message:
            return message
        else:
            print(f"Error: Parsed message missing mandatory 'type' or 'payload' field. Data: {message_str[:100]}")
            return None
    except json.JSONDecodeError:
        print("Error: Could not decode JSON message.")
        return None
    except UnicodeDecodeError:
        print("Error: Could not decode UTF-8 message.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred during message parsing: {e}")
        return None

if __name__ == '__main__':
    # Example Usage
    msg1 = create_message(MSG_TYPE_MESSAGE, {"sender": "Alice", "text": "Hello Bob!"})
    print(f"Encoded Standard Message 1: {msg1}")
    parsed_msg1 = parse_message(msg1)
    print(f"Parsed Standard Message 1: {parsed_msg1}")

    # Example with latency fields
    import time
    import uuid
    latency_msg_payload = {"sender": "Tester", "text": "Latency test!"}
    msg_id_example = str(uuid.uuid4())
    ts_example = time.time()
    latency_msg = create_message(MSG_TYPE_MESSAGE, latency_msg_payload, message_id=msg_id_example, send_timestamp=ts_example)
    print(f"Encoded Latency Message: {latency_msg}")
    parsed_latency_msg = parse_message(latency_msg)
    print(f"Parsed Latency Message: {parsed_latency_msg}")


    msg2 = create_message(MSG_TYPE_COMMAND, {"command": "list_users"})
    print(f"Encoded Command Message: {msg2}")
    parsed_msg2 = parse_message(msg2)
    print(f"Parsed Command Message: {parsed_msg2}")

    # UDP Examples
    udp_data_msg = create_message(MSG_TYPE_UDP_DATA, {"data_chunk": "chunk1"}, seq_num=1, message_id="udp-msg-1", send_timestamp=time.time())
    print(f"Encoded UDP Data Message: {udp_data_msg}")
    parsed_udp_data = parse_message(udp_data_msg)
    print(f"Parsed UDP Data Message: {parsed_udp_data}")

    udp_ack_msg = create_message(MSG_TYPE_UDP_ACK, {}, ack_num=1) # Payload can be empty for ACK
    print(f"Encoded UDP ACK Message: {udp_ack_msg}")
    parsed_udp_ack = parse_message(udp_ack_msg)
    print(f"Parsed UDP ACK Message: {parsed_udp_ack}")
    
    udp_data_with_ack_field = create_message(MSG_TYPE_UDP_DATA, {"data_chunk": "piggyback_data"}, seq_num=2, ack_num=0) # Example of piggybacking ACK
    print(f"Encoded UDP Data with ACK field: {udp_data_with_ack_field}")
    parsed_udp_data_with_ack_field = parse_message(udp_data_with_ack_field)
    print(f"Parsed UDP Data with ACK field: {parsed_udp_data_with_ack_field}")


    # Example of a message that might cause issues if not handled (e.g. non-dict payload)
    # msg_bad_payload = create_message(MSG_TYPE_MESSAGE, "just a string") # This will now raise TypeError

    # Example of a malformed JSON string
    malformed_data = b'{"type": "MESSAGE", "payload": {"text": "unterminated string}'
    parsed_malformed = parse_message(malformed_data)
    print(f"Parsed Malformed Message: {parsed_malformed}")

    empty_data = b''
    parsed_empty = parse_message(empty_data)
    print(f"Parsed Empty Message: {parsed_empty}")

    non_json_data = b'This is not JSON'
    parsed_non_json = parse_message(non_json_data)
    print(f"Parsed Non-JSON Message: {parsed_non_json}")

    # Test with a potentially problematic payload for serialization
    class NonSerializable:
        pass
    # This will be caught by the create_message error handling
    # msg_non_serializable = create_message(MSG_TYPE_MESSAGE, {"data": NonSerializable()})
    # print(f"Encoded Non-Serializable: {msg_non_serializable}")
    # parsed_non_serializable = parse_message(msg_non_serializable)
    # print(f"Parsed Non-Serializable: {parsed_non_serializable}")

    # Test message creation with a valid but complex payload
    complex_payload = {
        "sender": "System",
        "details": {
            "code": 101,
            "description": "User Alice has joined the chat.",
            "timestamp": "2023-10-27T10:30:00Z"
        },
        "priority": "high"
    }
    msg_complex = create_message(MSG_TYPE_SYSTEM, complex_payload)
    print(f"Encoded Complex Message: {msg_complex}")
    parsed_complex = parse_message(msg_complex)
    print(f"Parsed Complex Message: {parsed_complex}")