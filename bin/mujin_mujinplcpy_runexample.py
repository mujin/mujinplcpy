#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import typing
import asyncio

from mujinplc import plcmemory, plcserver, plccontroller, plclogic, plcproductionrunner, plcproductioncycle, plcpickworkersimulator

import logging
log = logging.getLogger(__name__)


class Example(plcproductionrunner.PLCMaterialHandler):

    def __init__(self, plcMemory: plcmemory.PLCMemory):
        self._productionRunner = plcproductionrunner.PLCProductionRunner(plcMemory, self)
        self._controller = plccontroller.PLCController(memory, maxHeartbeatInterval=0.1)

    async def MoveLocationAsync(self, locationIndex: int, expectedContainerId: str, expectedContainerType: str, orderUniqueId: str) -> typing.Tuple[str, str]:
        """
        when location needs moving called by mujin
        send request to agv to move, can return immediately even if agv has not started moving yet
        function should return a pair of actual containerId and containerType
        """
        log.warn('moving location %d: expectedContainerId = %r, expectedContainerType = %r, orderUniqueId = %r', locationIndex, expectedContainerId, expectedContainerType, orderUniqueId)
        await asyncio.sleep(1) # for testing
        return expectedContainerId, expectedContainerType

    async def FinishOrderAsync(self, orderUniqueId: str, orderCycleFinishCode: plclogic.PLCOrderCycleFinishCode, numPutInDestination: int) -> None:
        """
        when order status changed called by mujin
        """
        log.warn('finish order: orderUniqueId = %r, orderCycleFinishCode = %r, numPutInDestination = %r', orderUniqueId, orderCycleFinishCode, numPutInDestination)
        await asyncio.sleep(1) # for testing

    def Start(self):
        self._productionRunner.Start()

    def Stop(self):
        self._productionRunner.Stop()

    def WaitUntilConnected(self) -> None:
        self._controller.WaitUntilConnected()

    def QueueOrders(self) -> None:
        self._productionRunner.QueueOrder('ORDER #1', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'cola',
            orderNumber = 1,
            pickLocationIndex = 1,
            pickContainerId = '0001',
            placeLocationIndex = 3,
            placeContainerId = 'pallet1',
        ))

        self._productionRunner.QueueOrder('ORDER #2', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'pepsi',
            orderNumber = 1,
            pickLocationIndex = 2,
            pickContainerId = '0002',
            placeLocationIndex = 3,
            placeContainerId = 'pallet1',
        ))

        self._productionRunner.QueueOrder('ORDER #3', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'milk',
            orderNumber = 1,
            pickLocationIndex = 1,
            pickContainerId = '0003',
            placeLocationIndex = 3,
            placeContainerId = 'pallet1',
        ))

        self._productionRunner.QueueOrder('ORDER #4', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'juice',
            orderNumber = 1,
            pickLocationIndex = 2,
            pickContainerId = '0004',
            placeLocationIndex = 3,
            placeContainerId = 'pallet2',
        ))

        self._productionRunner.QueueOrder('ORDER #5', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'sprite',
            orderNumber = 1,
            pickLocationIndex = 1,
            pickContainerId = '0005',
            placeLocationIndex = 3,
            placeContainerId = 'pallet1',
        ))

        self._productionRunner.QueueOrder('ORDER #6', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'water',
            orderNumber = 1,
            pickLocationIndex = 2,
            pickContainerId = '0006',
            placeLocationIndex = 3,
            placeContainerId = 'pallet2',
        ))

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

    # production cycle is a standalone server process monitoring the memory
    productionCycle = None
    if True:
        productionCycle = plcproductioncycle.PLCProductionCycle(memory)
        productionCycle.Start()

    # pick worker simulator
    pickWorkerSimulator = None
    if True:
        pickWorkerSimulator = plcpickworkersimulator.PLCPickWorkerSimulator(memory)
        pickWorkerSimulator.Start()

    # customer code
    example = Example(memory)
    example.Start()

    # start a network server instance for MUJIN controllers to connect to
    server = plcserver.PLCServer(memory, 'tcp://*:5555')
    server.Start()
    log.warn('server started.')

    example.WaitUntilConnected()
    log.warn('connected.')

    example.QueueOrders()

    # pause until we want to stop
    # in a real program, should handle SIGTERM instead
    input('Press ENTER to stop.\n')

    # stop everything
    log.warn('stopping.')
    server.Stop()
    example.Stop()
    if productionCycle:
        productionCycle.Stop()
    if pickWorkerSimulator:
        pickWorkerSimulator.Stop()
    log.warn('stopped.')
