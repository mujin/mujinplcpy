# -*- coding: utf-8 -*-

import asyncio
import typing
from . import plcmemory, plclogic

import logging
log = logging.getLogger(__name__)

class PLCMaterialHandler:
    """
    To be subclassed and implemented by customer.
    """

    async def MoveLocationAsync(self, locationIndex: int, containerId: str, containerType: str, orderUniqueId: str) -> typing.Tuple[str, str]:
        """
        when location needs moving called by mujin
        send request to agv to move, can return immediately even if agv has not started moving yet
        function should return a pair of actual containerId and containerType
        """
        return containerId, containerType

    async def FinishOrderAsync(self, orderUniqueId: str, orderFinishCode: plclogic.PLCOrderCycleFinishCode) -> None:
        """
        when order status changed called by mujin
        """
        return

class PLCQueueOrderParameters:
    """
    Struct describing order data
    """

    partType = '' # type of the product to be picked, for example: "cola"
    orderNumber = 0 # number of items to be picked, for example: 1
    robotId = 0 # set to 1

    pickLocationIndex = 0 # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # barcode of the source container, for example: "010023"
    pickContainerType = '' # type of the source container, if all the same, set to ""

    placeLocationIndex = 0 # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # barcode of the dest contianer, for example: "pallet1"
    placeContainerType = '' # type of the source container, if all the same, set to ""

    packInputPartIndex = 0 # when using packFormation, index of the part in the pack
    packFormationComputationName = '' # when using packFormation, name of the formation

class PLCProductionCycle:
    """
    Interface to communicate with production cycle
    """

    _memory = None # an instance of PLCMemory

    def __init__(self, memory: plcmemory.PLCMemory, materialHandler: PLCMaterialHandler):
        self._memory = memory

    def QueueOrder(self, orderUniqueId: str, queueOrderParameters: PLCQueueOrderParameters) -> None:
        pass
