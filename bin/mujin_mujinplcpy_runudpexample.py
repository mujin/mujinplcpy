#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys

from mujinplc import plcmemory, plcudpserver

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
    ConfigureLogging()

    # have one plc memory per MUJIN controller
    memory = plcmemory.PLCMemory()
    logger = plcmemory.PLCMemoryLogger(memory)

    # start a network server instance for MUJIN controllers to connect to
    server = plcudpserver.PLCUDPServer(memory, 5555)
    server.Start()
    log.warn('server started.')

    # pause until we want to stop
    # in a real program, should handle SIGTERM instead
    input('Press ENTER to stop.\n')

    # stop everything
    log.warn('stopping.')
    server.Stop()
    log.warn('stopped.')
