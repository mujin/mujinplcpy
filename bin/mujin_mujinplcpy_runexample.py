#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import typing

from mujinplc import plcmemory, plcserver, plccontroller, plclogic, plcproductioncycle

import logging
log = logging.getLogger(__name__)


class Example(plcproductioncycle.PLCMaterialHandler):

    def __init__(self, plcMemory: plcmemory.PLCMemory):
        self._productionCycle = plcproductioncycle.PLCProductionCycle(plcMemory, self)
        self._controller = plccontroller.PLCController(memory, maxHeartbeatInterval=0.1)

    async def MoveLocationAsync(self, locationIndex: int, containerId: str, containerType: str, orderUniqueId: str) -> typing.Tuple[str, str]:
        """
        when location needs moving called by mujin
        send request to agv to move, can return immediately even if agv has not started moving yet
        function should return a pair of actual containerId and containerType
        """
        return containerId, containerType

    async def FinishOrderAsync(self, orderUniqueId: str, orderFinishCode: plclogic.PLCOrderCycleFinishCode, numPutInDest: int) -> None:
        """
        when order status changed called by mujin
        """
        return

    def WaitUntilConnected(self) -> None:
        self._controller.WaitUntilConnected()

    def QueueOrders(self) -> None:
        self._productionCycle.QueueOrder('a', plcproductioncycle.PLCQueueOrderParameters(
            partType = 'cola',
            orderNumber = 1,
            pickLocationIndex = 1,
            pickContainerId = '0001',
            placeLocationIndex = 2,
            placeContainerId = 'pallet1',
        ))

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)s [%(levelname)s] [%(filename)s:%(lineno)s %(funcName)s] %(message)s', level=logging.DEBUG)

    memory = plcmemory.PLCMemory()
    server = plcserver.PLCServer(memory, 'tcp://*:5555')
    server.Start()
    log.info('server started.')

    example = Example(memory)
    example.WaitUntilConnected()
    log.info('connected.')

    example.QueueOrders()

    # pause until we want to stop
    # in a real program, should handle SIGTERM instead
    input('Press ENTER to stop.\n')

    server.Stop()
    log.info('server stopped.')
