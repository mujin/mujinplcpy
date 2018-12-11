#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import typing
import asyncio

from mujinplc import plcmemory, plcserver, plccontroller, plclogic, plcproductionrunner, plcproductioncycle

import logging
log = logging.getLogger(__name__)


class Example(plcproductionrunner.PLCMaterialHandler):

    def __init__(self, plcMemory: plcmemory.PLCMemory):
        self._productionRunner = plcproductionrunner.PLCProductionRunner(plcMemory, self)
        self._controller = plccontroller.PLCController(memory, maxHeartbeatInterval=0.1)

    async def MoveLocationAsync(self, locationIndex: int, containerId: str, containerType: str, orderUniqueId: str) -> typing.Tuple[str, str]:
        """
        when location needs moving called by mujin
        send request to agv to move, can return immediately even if agv has not started moving yet
        function should return a pair of actual containerId and containerType
        """
        log.info('containerId = %r', containerId)
        log.info('containerType = %r', containerType)
        log.info('orderUniqueId = %r', orderUniqueId)
        await asyncio.sleep(30) # for testing
        return containerId + containerId, containerType

    async def FinishOrderAsync(self, orderUniqueId: str, orderFinishCode: plclogic.PLCOrderCycleFinishCode, numPutInDest: int) -> None:
        """
        when order status changed called by mujin
        """
        log.info('orderUniqueId = %r', orderUniqueId)
        log.info('orderFinishCode = %r', orderFinishCode)
        log.info('numPutInDest = %r', numPutInDest)
        await asyncio.sleep(30) # for testing
        return

    def Start(self):
        self._productionRunner.Start()

    def Stop(self):
        self._productionRunner.Stop()

    def WaitUntilConnected(self) -> None:
        self._controller.WaitUntilConnected()

    def QueueOrders(self) -> None:
        self._productionRunner.QueueOrder('a', plcproductionrunner.PLCQueueOrderParameters(
            partType = 'cola',
            orderNumber = 1,
            pickLocationIndex = 1,
            pickContainerId = '0001',
            placeLocationIndex = 2,
            placeContainerId = 'pallet1',
        ))

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)s [%(levelname)s] [%(filename)s:%(lineno)s %(funcName)s] %(message)s', level=logging.DEBUG)

    # have one plc memory per MUJIN controller
    memory = plcmemory.PLCMemory()
    logger = plcmemory.PLCMemoryLogger(memory)

    # production cycle is a standalone server process monitoring the memory
    productionCycle = None
    if True:
        productionCycle = plcproductioncycle.PLCProductionCycle(memory)
        productionCycle.Start()

    # customer code
    example = Example(memory)
    example.Start()

    # start a network server instance for MUJIN controllers to connect to
    server = plcserver.PLCServer(memory, 'tcp://*:5555')
    server.Start()
    log.info('server started.')

    example.WaitUntilConnected()
    log.info('connected.')

    example.QueueOrders()

    # pause until we want to stop
    # in a real program, should handle SIGTERM instead
    input('Press ENTER to stop.\n')

    # stop everything
    log.info('stopping.')
    server.Stop()
    example.Stop()
    if productionCycle:
        productionCycle.Stop()
    log.info('stopped.')
