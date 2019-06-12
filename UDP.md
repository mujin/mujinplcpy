# UDP-based PLC communication

This specification document describes a UDP-based PLC communication protocol to be used with MUJIN controllers.

## Overview

- PLC communcation with MUJIN controller has to be realtime, low-latency and fault-tolerant.
- This netowrk protocol is built on top of UDP.
- There are two UDP ports in use. First port is for request-reply communication. Second port is for notifications.

## Request-reply port

Communication for request-reply port is bi-directional. MUJIN controller will send request to PLC, and PLC will send response to MUJIN controller for each request.

UDP port number is 5555 by default for this port. UDP packet content has to be in JSON format, and the root element has to be a JSON dictionary.

### Request from MUJIN controller

A typical request UDP packet sent from MUJIN controller to user PLC will contain:

| Field | Type | Description |
| - | - | - |
| `seqid` | 64-bit unsigned integer | (required) Sequence number, monotonically incremented, needs to be matched when replying |
| `read` | list of strings | (optional) List of signals to read from user PLC |
| `writevalues` | dictionary with string keys | (optional) Mapping of signals and corresponding values to be written to user PLC |
| `timestamp` | 64-bit unsigned integer | (required) MUJIN controller timestamp of request, monotonically increasing |

For example,

```json
{
    "seqid": 1234,
    "read": ["signal1", "signal2"],
    "writevalues": {
        "signal3": "value3",
        "signal4": "value4"
    },
    "timestamp": 5678
}
```

### Reply to MUJIN controller

Reply to request need to be sent to the originating UDP port on the originating IP address. A typical reply UDP packet sent from user PLC to MUJIN controller will contain:

| Field | Type | Description |
| - | - | - |
| `seqid` | 64-bit unsigned integer | (required) Sequence number, needs to match the `seqid` in request |
| `readvalues` | dictionary with string keys | (optional) Mapping of signals and corresponding values as requested in `read` field of request. When requested signal does not exist, it should be omitted. `readvalues` field should be present if and only if `read` exists in request |
| `timestamp` | 64-bit unsigned integer | (required) PLC timestamp of reply, monotonically increasing |


For example,

```json
{
    "seqid": 1234,
    "readvalues": {
        "signal2": "value2"
    },
    "timestamp": 333
}
```

## Notification port

Notification port communication is uni-directional. Notifications are sent from user PLC to MUJIN controller. Notifications should be sent as soon as signals on user PLC changes.

UDP port number is request-reply UDP port number plus one, therefore 5556 by default. UDP packet content has to be in JSON format, and the root element has to be a JSON dictionary.

A typical notification UDP packet sent from user PLC to MUJIN controller will contain:

| Field | Type | Description |
| - | - | - |
| `changevalues` | dictionary with string keys | (required) Mapping of signals and corresponding values that changed |
| `timestamp` | 64-bit unsigned integer | (required) PLC timestamp of notification, monotonically increasing |

For example,

```json
{
    "changevalues": {
        "signal2": "value2-changed"
    },
    "timestamp": 444
}
```

## Error handling

- UDP checksum should be enabled
- UDP packet content should be limited to 10240 bytes
