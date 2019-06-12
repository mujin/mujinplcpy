# ZeroMQ-based PLC communication

This specification document describes a ZeroMQ-based PLC communication protocol to be used with MUJIN controllers. See [plczmqserver.py](python/mujinplc/plczmqserver.py) for reference implementation.

## Overview

- This netowrk protocol is built on top of ZeroMQ REQ-REP sockets.
- MUJIN controller will send a request, and user PLC will reply to the request.
- Two types of requests are used, `read` and `write`, for reading signal values from user PLC and writing signal values to user PLC.

## Socket

Communication on REQ-REP socket is bi-directional. MUJIN controller will create a `ZMQ_REQ` socket to connect to client PLC. Client PLC should listen on a `ZMQ_REP` socket, typically on TCP port `5555`.

The format of the ZeroMQ message has to be JSON, and the root element has to be a JSON dictionary.

## `read`

`read` operation is for MUJIN controller to read signal values on user PLC.

### `read` request

A typical `read` request sent from MUJIN controller to user PLC will contain:

| Field | Type | Description |
| - | - | - |
| `command` | string | (required) must be set to `"read"` |
| `keys` | list of strings | (required) List of signals to read from user PLC |

For example,

```json
{
    "command": "read",
    "keys": ["signal1", "signal2"]
}
```

### `read` reply

A typical reply for `read` request sent from user PLC to MUJIN controller will contain:

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

## `write`

`write` operation is for MUJIN controller to write signal values on user PLC.

### `write` request

A typical `write` request sent from MUJIN controller to user PLC will contain:

| Field | Type | Description |
| - | - | - |
| `command` | string | (required) must be set to `"write"` |
| `keyvalues` | dictionary with string keys | (required) Mapping of signals and corresponding values to be written to user PLC |

For example,

```json
{
    "command": "write",
    "keyvalues": {
        "signal3": "value3",
        "signal4": "value4"
    }
}
```

### `write` reply

A typical reply for `write` request sent from user PLC to MUJIN controller will contain no field. For example,

```json
{
}
```
