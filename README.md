# MUJIN PLC Library

This is an open-source library that provides simulated PLC server for MUJIN Controllers.

[![Build Status](https://travis-ci.org/mujin/mujinplcpy.svg?branch=master)](https://travis-ci.org/mujin/mujinplcpy)

## Dependencies

```
pyzmq==17.1.2
```

Optional log coloring:

```
logutils==0.3.5
```


## Development dependencies

```
flake8==3.6.0
mypy==0.650
pytest==4.0.1
```

Run syntax checking:

```
flake8 --show-source --ignore=E251,E261,E301,E302,E303,E305,E501 python/ bin/
```

Run type checking:

```
mypy --config-file=.mypy.ini python/ bin/
```

Run tests:

```
pytest
```

