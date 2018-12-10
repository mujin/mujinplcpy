# -*- coding: utf-8 -*-

import threading
import time
from enum import Enum
import typing
from . import plcmemory, plclogic, plccontroller
from . import PLCDataObject

import logging
log = logging.getLogger(__name__)

class PLCMaterialHandler:
    """
    To be subclassed and implemented by customer.
    """

    def MoveLocationAsync(self, locationIndex: int, containerId: str, containerType: str, orderUniqueId: str) -> typing.Tuple[str, str]:
        """ function is called when location needs moving called by mujin
        it should send request to agv to move.
        this function should wait until location(agv/container) is ready and return a pair of actual containerId and containerType
        """
        return containerId, containerType

    def FinishOrderAsync(self, orderUniqueId: str, orderFinishCode: plclogic.PLCOrderCycleFinishCode, numPutInDest: int) -> None:
        """ function is invoked when order status changed called by mujin
        This function should wait until customer system confirm current order and return to Mujin. Mujin won't continue to work unless this function returned without raising any exception.
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

    class MoveLocationFinishCode(Enum):
        NotAvailable = 0x0000
        Success = 0x0001
        Error = 0xffff

    class FinishOrderFinishCode(Enum):
        NotAvailable = 0x0000
        Success = 0x0001
        Error = 0xffff

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
        # TODO: this is too simplified
        controller = plccontroller.PLCController(self._memory)
        controller.WaitUntil('isQueueOrderRunning', False)
        controller.SetMultiple({
            'queueOrderPartType': queueOrderParameters.partType,
            'queueOrderNumber': queueOrderParameters.orderNumber,
            'queueOrderRobotId': queueOrderParameters.robotId,
            'queueOrderPickLocationIndex': queueOrderParameters.pickLocationIndex,
            'queueOrderPickContainerId': queueOrderParameters.pickContainerId,
            'queueOrderPickContainerType': queueOrderParameters.pickContainerType,
            'queueOrderPlaceLocationIndex': queueOrderParameters.placeLocationIndex,
            'queueOrderPlaceContainerId': queueOrderParameters.placeContainerId,
            'queueOrderPlaceContainerType': queueOrderParameters.placeContainerType,
            'startQueueOrder': True,
        })
        try:
            controller.WaitUntil('isQueueOrderRunning', True)
            controller.Set('startQueueOrder', False)
            controller.WaitUntil('isQueueOrderRunning', False)
            finishCode = controller.GetInteger('queueOrderFinishCode')
            if finishCode != 1:
                raise Exception('QueueOrder failed with finish code: %d' % finishCode)
        finally:
            controller.Set('startQueueOrder', False)

    def _RunThread(self) -> None:
        # monitor startMoveLocationX and startFinishOrder, then spin threads to handle them
        controller = plccontroller.PLCController(self._memory)

        # clear signals
        signalsToClear = {
            'finishOrderFinishCode': 0,
            'isFinishOrderRunning': False,
        }
        for locationIndex in self._locationIndices:
            signalsToClear['isMoveLocation%dRunning' % locationIndex] = False
            signalsToClear['moveLocation%dFinishCode' % locationIndex] = 0
        controller.SetMultiple(signalsToClear)

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

        # TODO: handle exceptions of this thread and clear signal in the end

    def _RunMoveLocationThread(self, locationIndex: int) -> None:
        controller = plccontroller.PLCController(self._memory)
        finishCode = MoveLocationFinishCode.NotAvailable
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
            try:
                actualContainerId, actualContainerType = self._materialHandler.MoveLocationAsync(locationIndex, containerId, containerType, orderUniqueId)
            except Exception as e:
                # material handler raise exception
                log.error("MoveLocation%dThread error = %s" % (locationIndex, e))
                finishCode = MoveLocationFinishCode.Error
            else:
                log.info("MoveLocation%dThread success" % locationIndex)
                finishCode = MoveLocationFinishCode.Success
            # MoveLocationAsync return successfully. Location is Readly.
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

    def _RunFinishOrderThread(self) -> None:
        """ Start new thread to handle finishOrder requset
        """
        controller = plccontroller.PLCController(self._memory)
        finishCode = FinishOrderFinishCode.NotAvailable
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
            try:
                # run customer code
                self._materialHandler.FinishOrderAsync(orderUniqueId, orderFinishCode, numPutInDest)
            except Exception as e:
                # FinishOrder raise error;
                finishCode = FinishOrderFinishCode.Error
            else:
                # material handler return successfully. set finishCode to Success
                finishCode = FinishOrderFinishCode.Success
            controller.WaitUntil('startFinishOrder', False)
        finally:
            log.debug('finishOrder thread stopping')
            controller.SetMultiple({
                'finishOrderFinishCode': finishCode,
                'isFinishOrderRunning': False,
            })
            self._finishOrderThread = None
