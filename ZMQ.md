# ZeroMQ-based PLC communication

This specification document describes a ZeroMQ-based PLC communication protocol to be used with MUJIN controllers.

## Overview

- This netowrk protocol is built on top of ZeroMQ REQ-REP sockets.

## Sockets

Communication on REQ-REP sockets are bi-directional. MUJIN controller will create a `ZMQ_REQ` socket to connect to client PLC. Client PLC should listen on a `ZMQ_REP` socket, typically on TCP port 5555.

The format of the ZeroMQ message has to be JSON, and the root element has to be a JSON dictionary.

## Read

Read operation is for MUJIN controller to read signal values on user PLC.

### Read request

A typical read request sent from MUJIN controller to user PLC will contain:

| Field | Type | Description |
| - | - | - |
| `command` | string | (required) must be set to "read" |
| `keys` | list of strings | (required) List of signals to read from user PLC |

For example,

```json
{
    "command": "read",
    "keys": ["signal1", "signal2"]
}
```

### Read reply

A typical reply for read request sent from user PLC to MUJIN controller will contain:

| Field | Type | Description |
| - | - | - |
| `keyvalues` | dictionary with string keys | (optional) Mapping of signals and corresponding values as requested in `keys` field of read request. When requested signal does not exist, it should be omitted |

For example,

```json
{
    "keyvalues": {
        "signal2": "value2"
    }
}
```

## Write

Write operation is for MUJIN controller to write signal values on user PLC.

### Write request

A typical write request sent from MUJIN controller to user PLC will contain:

| Field | Type | Description |
| - | - | - |
| `command` | string | (required) must be set to "write" |
| `keyvalues` | dictionary with string keys | (required) Mapping of signals and corresponding values to be written to user PLC |

For example,

```json
{
    "command": "write",
    "writevalues": {
        "signal3": "value3",
        "signal4": "value4"
    }
}
```

### Write reply

A typical reply for write request sent from user PLC to MUJIN controller will contain no field. For example,

```json
{
}
```
