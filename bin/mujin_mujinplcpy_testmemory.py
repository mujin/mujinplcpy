#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import typing # noqa: F401 # used in type check
import asyncio

from mujinplc import plcmemory, plczmqserver, plccontroller, plclogic, plcproductionrunner, plcproductioncycle, plcpickworkersimulator

import logging
log = logging.getLogger(__name__)


def ConfigureLogging(logLevel=logging.DEBUG, outputStream=sys.stderr):
    handler = logging.StreamHandler(outputStream)
    try:
        import logutils.colorize
        handler = logutils.colorize.ColorizingStreamHandler(outputStream)
        handler.level_map[logging.DEBUG] = (None, 'green', False)
        handler.level_map[logging.INFO] = (None, None, False)
        handler.level_map[logging.WARNING] = (None, 'yellow', False)
        handler.level_map[logging.ERROR] = (None, 'red', False)
        handler.level_map[logging.CRITICAL] = ('white', 'magenta', True)
    except ImportError:
        pass
    handler.setFormatter(logging.Formatter('%(asctime)s %(name)s [%(levelname)s] [%(filename)s:%(lineno)s %(funcName)s] %(message)s'))
    handler.setLevel(logLevel)

    root = logging.getLogger()
    root.setLevel(logLevel)
    root.handlers = []
    root.addHandler(handler)

if __name__ == '__main__':
    ConfigureLogging(logging.INFO)

    # have one plc memory per MUJIN controller
    memory = plcmemory.PLCMemory()
    logger = plcmemory.PLCMemoryLogger(memory)

    # start a network server instance for MUJIN controllers to connect to
    server = plczmqserver.PLCZMQServer(memory, 'tcp://*:5555')
    server.Start()
    log.warn('server started.')

    from IPython.terminal import embed; ipshell=embed.InteractiveShellEmbed(config=embed.load_default_config())(local_ns=locals())
