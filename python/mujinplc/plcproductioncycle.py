# -*- coding: utf-8 -*-

import threading
import time
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
    _locationIndices = None # type: typing.List[int]

    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _finishOrderThread = None # type: typing.Optional[threading.Thread]
    _moveLocationThreads = None # type: typing.Dict[int, typing.Optional[threading.Thread]]

    def __init__(self, memory: plcmemory.PLCMemory, materialHandler: PLCMaterialHandler, maxLocationIndex: int = 4):
        self._memory = memory
        self._materialHandler = materialHandler
        self._locationIndices = list(range(1, maxLocationIndex + 1))
        self._moveLocationThreads = {}

    def __del__(self):
        self.Stop()

    def Start(self) -> None:
        self.Stop()

        # start the main monitoring thread
        self._isok = True
        self._thread = threading.Thread(target=self._RunThread, name='plcproductioncycle')
        self._thread.start()

    def Stop(self) -> None:
        self._isok = False
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def QueueOrder(self, orderUniqueId: str, queueOrderParameters: PLCQueueOrderParameters) -> None:
        pass

    def _RunThread(self) -> None:
        # monitor startMoveLocationX and startFinishOrder, then spin threads to handle them
        controller = plccontroller.PLCController(self._memory)
        while self._isok:
            triggerSignals = {}
            for locationIndex in self._locationIndices:
                if not self._moveLocationThreads.get(locationIndex, None):
                    triggerSignals['startMoveLocation%d' % locationIndex] = True
            if not self._finishOrderThread:
                triggerSignals['startFinishOrder'] = True

            if not triggerSignals:
                # everything running, nothing new to trigger
                time.sleep(0.1)
                continue

            if not controller.WaitUntilAny(triggerSignals, timeout=0.1):
                # nothing need to be triggered
                continue

            for locationIndex in self._locationIndices:
                triggerSignal = 'startMoveLocation%d' % locationIndex
                if triggerSignal not in triggerSignals:
                    continue
                if not controller.GetBoolean(triggerSignal):
                    continue
                log.debug('starting a thread to handle %s', triggerSignal)
                thread = threading.Thread(target=self._RunMoveLocationThread, args=(locationIndex,), name='moveLocation%d' % locationIndex)
                thread.start()
                self._moveLocationThreads[locationIndex] = thread

            triggerSignal = 'startFinishOrder'
            if triggerSignal in triggerSignals and controller.GetBoolean(triggerSignal):
                log.debug('starting a thread to handle %s', triggerSignal)
                thread = threading.Thread(target=self._RunFinishOrderThread, name='finishOrder')
                thread.start()
                self._finishOrderThread = thread

    def _RunMoveLocationThread(self, locationIndex: int) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        finishCode = 0xffff
        actualContainerId = ''
        actualContainerType = ''
        try:
            if not controller.SyncAndGetBoolean('startMoveLocation%d' % locationIndex):
                # trigger no longer alive
                return

            # first garther parameters
            containerId = controller.GetString('moveLocation%dContainerId' % locationIndex)
            containerType = controller.GetString('moveLocation%dContainerType' % locationIndex)
            orderUniqueId = controller.GetString('moveLocation%dOrderUniqueId' % locationIndex)

            # set output signals first
            controller.SetMultiple({
                'moveLocation%dFinishCode' % locationIndex: 0,
                'isMoveLocation%dRunning' % locationIndex: True,
                'location%dContainerId' % locationIndex: '',
                'location%dContainerType' % locationIndex: '',
                'location%dProhibited' % locationIndex: True,
            })

            # run customer code
            actualContainerId, actualContainerType = loop.run_until_complete(self._materialHandler.MoveLocationAsync(locationIndex, containerId, containerType, orderUniqueId))

            controller.WaitUntil('startMoveLocation%d' % locationIndex, False)
        finally:
            log.debug('moveLocation%d thread stopping', locationIndex)
            controller.SetMultiple({
                'moveLocation%dFinishCode' % locationIndex: finishCode,
                'isMoveLocation%dRunning' % locationIndex: False,
                'location%dContainerId' % locationIndex: actualContainerId,
                'location%dContainerType' % locationIndex: actualContainerType,
                'location%dProhibited' % locationIndex: False,
            })
            self._moveLocationThreads[locationIndex] = None
            loop.close()

    def _RunFinishOrderThread(self) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        finishCode = 0xffff
        try:
            if not controller.SyncAndGetBoolean('startFinishOrder'):
                # trigger no longer alive
                return

            # first garther parameters
            orderUniqueId = controller.GetString('finishOrderOrderUniqueId')
            orderFinishCode = plclogic.PLCOrderCycleFinishCode(controller.GetInteger('finishOrderOrderFinishCode'))
            numPutInDest = controller.GetInteger('finishOrderNumPutInDest')

            # set output signals first
            controller.SetMultiple({
                'finishOrderFinishCode': 0,
                'isFinishOrderRunning': True,
            })

            # run customer code
            loop.run_until_complete(self._materialHandler.FinishOrderAsync(orderUniqueId, orderFinishCode, numPutInDest))

            controller.WaitUntil('startFinishOrder', False)
        finally:
            log.debug('finishOrder thread stopping')
            controller.SetMultiple({
                'finishOrderFinishCode': finishCode,
                'isFinishOrderRunning': False,
            })
            self._finishOrderThread = None
            loop.close()
