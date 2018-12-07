# -*- coding: utf-8 -*-

import threading
import asyncio
import typing
from . import plcmemory, plclogic, plccontroller
from . import PLCDataObject

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

    async def FinishOrderAsync(self, orderUniqueId: str, orderFinishCode: plclogic.PLCOrderCycleFinishCode, numPutInDest: int) -> None:
        """
        when order status changed called by mujin
        """
        return

class PLCQueueOrderParameters(PLCDataObject):
    """
    Struct describing order data
    """

    partType = '' # type: str # type of the product to be picked, for example: "cola"
    partSizeX = 0 # type: int
    partSizeY = 0 # type: int
    partSizeZ = 0 # type: int

    orderNumber = 0 # type: int # number of items to be picked, for example: 1

    robotId = 0 # type: int # set to 1

    pickLocationIndex = 0 # type: int # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # type: str # barcode of the source container, for example: "010023"
    pickContainerType = '' # type: str # type of the source container, if all the same, set to ""

    placeLocationIndex = 0 # type: int # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # type: str # barcode of the dest contianer, for example: "pallet1"
    placeContainerType = '' # type: str # type of the source container, if all the same, set to ""

    packInputPartIndex = 0 # type: int # when using packFormation, index of the part in the pack
    packFormationComputationName = '' # type: str # when using packFormation, name of the formation

class PLCProductionCycle:
    """
    Interface to communicate with production cycle
    """

    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _materialHandler = None # type: PLCMaterialHandler # an instance of PLCMaterialHandler, supplied by customer

    def __init__(self, memory: plcmemory.PLCMemory, materialHandler: PLCMaterialHandler):
        self._memory = memory
        self._materialHandler = materialHandler

        self._thread = threading.Thread(target=self._RunThread, name='plcproductioncycle')

    def QueueOrder(self, orderUniqueId: str, queueOrderParameters: PLCQueueOrderParameters) -> None:
        pass


    def _RunThread(self) -> None:
        # monitor startMoveLocationX and startFinishOrder, then spin threads to handle them
        pass

    def _RunMoveLocationThread(self, locationIndex: int) -> None:
        controller = plccontroller.PLCController(self._memory)
        if not controller.GetBoolean('startMoveLocation%d' % locationIndex):
            return

    def _RunFinishOrderThread(self) -> None:
        controller = plccontroller.PLCController(self._memory)
        if not controller.GetBoolean('startFinishOrder'):
            return
