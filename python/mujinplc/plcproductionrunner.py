# -*- coding: utf-8 -*-

import threading
import time
import asyncio
import typing # noqa: F401 # used in type check
import enum

from . import plcmemory, plclogic, plccontroller
from . import PLCDataObject

import logging
log = logging.getLogger(__name__)

class PLCMaterialHandler:
    """
    To be subclassed and implemented by customer.
    """
    _moveLocation = None
    _finishOrder = None

    def __init__(self, moveLocation=None, finishOrder=None):
        self._moveLocation = moveLocation
        self._finishOrder = finishOrder

    async def MoveLocationAsync(self, locationIndex: int, expectedContainerId: str, expectedContainerType: str, orderUniqueId: str) -> typing.Tuple[str, str]:
        """
        when location needs moving called by mujin
        send request to agv to move, can return immediately even if agv has not started moving yet
        function should return a pair of actual containerId and containerType
        """
        if self._moveLocation:
            return self._moveLocation(locationIndex, expectedContainerId, expectedContainerType, orderUniqueId)
        return expectedContainerId, expectedContainerType

    async def FinishOrderAsync(self, orderUniqueId: str, orderCycleFinishCode: plclogic.PLCOrderCycleFinishCode, numPutInDestination: int) -> None:
        """
        when order status changed called by mujin
        """
        if self._finishOrder:
            self._finishOrder(orderUniqueId, orderCycleFinishCode, numPutInDestination)


class PLCQueueOrderParameters(PLCDataObject):
    """
    Struct describing order data
    """

    partType = '' # type: str # type of the product to be picked, for example: "cola"
    partSizeX = 0 # type: int
    partSizeY = 0 # type: int
    partSizeZ = 0 # type: int
    partWeight = 0 # type: int
    partPackingId = 0 # type: int

    orderNumber = 0 # type: int # number of items to be picked, for example: 1

    robotName = '' # type: str

    pickLocationIndex = 0 # type: int # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # type: str # barcode of the source container, for example: "010023"
    pickContainerType = '' # type: str # type of the source container, if all the same, set to ""

    placeLocationIndex = 0 # type: int # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # type: str # barcode of the dest contianer, for example: "pallet1"
    placeContainerType = '' # type: str # type of the source container, if all the same, set to ""

    inputPartIndex = 0 # type: int # when using packFormation, index of the part in the pack
    packFormationComputationName = '' # type: str # when using packFormation, name of the formation

    ignoreFinishPosition = False # type: bool

class PLCProductionCycleFinishCode(enum.IntEnum):
    """
    Finish code for the whole production cycle.
    """
    NotAvailable = 0x0000
    Success = 0x0001
    GenericError = 0xffff

class PLCQueueOrderFinishCode(enum.IntEnum):
    """
    Finish code for queueOrder signal.
    """
    NotAvailable = 0x0000
    Success = 0x0001
    GenericError = 0xffff

class PLCMoveLocationFinishCode(enum.IntEnum):
    """
    Finish code for moveLocationX signal.
    """
    NotAvailable = 0x0000
    Success = 0x0001
    GenericError = 0xffff

class PLCFinishOrderFinishCode(enum.IntEnum):
    """
    Finish code for finishOrder signal.
    """
    NotAvailable = 0x0000
    Success = 0x0001
    GenericError = 0xffff

class PLCProductionRunner:
    """
    Interface to communicate with production cycle
    """

    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _materialHandler = None # type: PLCMaterialHandler # an instance of PLCMaterialHandler, supplied by customer
    _locationIndices = None # type: typing.List[int]
    _logPrefix = '' # type: str

    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _finishOrderThread = None # type: typing.Optional[threading.Thread]
    _moveLocationThreads = None # type: typing.Dict[int, typing.Optional[threading.Thread]]

    def __init__(self, memory: plcmemory.PLCMemory, materialHandler: PLCMaterialHandler, maxLocationIndex: int = 4, logPrefix: str = ''):
        self._memory = memory
        self._materialHandler = materialHandler
        assert(maxLocationIndex > 0)
        self._locationIndices = list(range(1, maxLocationIndex + 1))
        self._logPrefix = logPrefix
        self._moveLocationThreads = {}

    def __del__(self):
        self.Stop()

    def Start(self) -> None:
        self.Stop()

        # start the main monitoring thread
        self._isok = True
        self._thread = threading.Thread(target=self._RunThread, name='plcproductionrunner')
        self._thread.start()

    def SetStop(self) -> None:
        self._isok = False

    def Stop(self) -> None:
        self.SetStop()

        if self._thread is not None:
            self._thread.join()
            self._thread = None

        if self._finishOrderThread is not None:
            self._finishOrderThread.join()
            self._finishOrderThread = None

        for thread in self._moveLocationThreads.values():
            if thread is not None:
                thread.join()
        self._moveLocationThreads = {}

    def QueueOrder(self, orderUniqueId: str, queueOrderParameters: PLCQueueOrderParameters) -> None:
        controller = plccontroller.PLCController(self._memory)
        if not controller.WaitUntil('isRunningQueueOrder', False, timeout=1.0):
            raise Exception('QueueOrder is already running on server side')
        controller.SetMultiple({
            'queueOrderUniqueId': orderUniqueId,
            'queueOrderPartType': queueOrderParameters.partType,
            'queueOrderPartSizeX': queueOrderParameters.partSizeX,
            'queueOrderPartSizeY': queueOrderParameters.partSizeY,
            'queueOrderPartSizeZ': queueOrderParameters.partSizeZ,
            'queueOrderPartWeight': queueOrderParameters.partWeight,
            'queueOrderPartPackingId': queueOrderParameters.partPackingId,
            'queueOrderNumber': queueOrderParameters.orderNumber,
            'queueOrderRobotName': queueOrderParameters.robotName,
            'queueOrderPickLocationIndex': queueOrderParameters.pickLocationIndex,
            'queueOrderPickContainerId': queueOrderParameters.pickContainerId,
            'queueOrderPickContainerType': queueOrderParameters.pickContainerType,
            'queueOrderPlaceLocationIndex': queueOrderParameters.placeLocationIndex,
            'queueOrderPlaceContainerId': queueOrderParameters.placeContainerId,
            'queueOrderPlaceContainerType': queueOrderParameters.placeContainerType,
            'queueOrderInputPartIndex': queueOrderParameters.inputPartIndex,
            'queueOrderPackFormationComputationName': queueOrderParameters.packFormationComputationName,
            'queueOrderIgnoreFinishPosition': queueOrderParameters.ignoreFinishPosition,
            'startQueueOrder': True,
        })
        try:
            # TODO: later, we need timeout handling
            controller.WaitUntil('isRunningQueueOrder', True)
            controller.Set('startQueueOrder', False)
            controller.WaitUntil('isRunningQueueOrder', False)
            finishCode = PLCQueueOrderFinishCode(controller.GetInteger('queueOrderFinishCode'))
            if finishCode != PLCQueueOrderFinishCode.Success:
                raise Exception('QueueOrder failed with finish code: %r' % finishCode)
            log.warn('%ssuccessfully queued order: %s: %r', self._logPrefix, orderUniqueId, queueOrderParameters)
        finally:
            controller.Set('startQueueOrder', False)

    def _RunThread(self) -> None:
        productionCycleStarted = False

        # monitor startMoveLocationX and startFinishOrder, then spin threads to handle them
        controller = plccontroller.PLCController(self._memory)

        # clear signals
        signalsToClear = {
            'startProductionCycle': False,
            'stopProductionCycle': False,
            'finishOrderFinishCode': int(PLCFinishOrderFinishCode.NotAvailable),
            'isRunningFinishOrder': False,
        }
        for locationIndex in self._locationIndices:
            signalsToClear['isRunningMoveLocation%d' % locationIndex] = False
            signalsToClear['moveLocation%dFinishCode' % locationIndex] = int(PLCMoveLocationFinishCode.NotAvailable)
        controller.SetMultiple(signalsToClear)

        try:
            while True:
                if not self._isok:
                    controller.Set('stopProductionCycle', True)

                # always start production cycle
                if controller.SyncAndGetBoolean('isRunningProductionCycle'):
                    controller.Set('startProductionCycle', False)
                    productionCycleStarted = True
                else:
                    if productionCycleStarted:
                        log.error('%sproduction cycle stopped', self._logPrefix)
                        break
                    if not self._isok:
                        break
                    controller.SetMultiple({
                        'productionCycleMaxLocationIndex': max(self._locationIndices),
                        'startProductionCycle': True,
                    })

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
                    log.debug('%sstarting a thread to handle %s', self._logPrefix, triggerSignal)
                    thread = threading.Thread(target=self._RunMoveLocationThread, args=(locationIndex,), name='moveLocation%d' % locationIndex)
                    thread.start()
                    self._moveLocationThreads[locationIndex] = thread

                triggerSignal = 'startFinishOrder'
                if triggerSignal in triggerSignals and controller.GetBoolean(triggerSignal):
                    log.debug('%sstarting a thread to handle %s', self._logPrefix, triggerSignal)
                    thread = threading.Thread(target=self._RunFinishOrderThread, name='finishOrder')
                    thread.start()
                    self._finishOrderThread = thread
        except Exception as e:
            log.exception('%scaught exception while running the monitor thread for production runner: %s', self._logPrefix, e)
        finally:
            controller.Set('stopProductionCycle', False)

    def _RunMoveLocationThread(self, locationIndex: int) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        finishCode = PLCMoveLocationFinishCode.GenericError
        actualContainerId = '?' # use ? to indicate location without container, because empty means feature disabled
        actualContainerType = '?' # use ? to indicate location without container, because empty means feature disabled
        try:
            if not controller.SyncAndGetBoolean('startMoveLocation%d' % locationIndex):
                # trigger no longer alive
                return

            # first garther parameters
            expectedContainerId = controller.GetString('moveLocation%dExpectedContainerId' % locationIndex)
            expectedContainerType = controller.GetString('moveLocation%dExpectedContainerType' % locationIndex)
            orderUniqueId = controller.GetString('moveLocation%dOrderUniqueId' % locationIndex)

            # set output signals first
            controller.SetMultiple({
                'moveLocation%dFinishCode' % locationIndex: 0,
                'isRunningMoveLocation%d' % locationIndex: True,
                'location%dContainerId' % locationIndex: '?', # use ? to indicate location without container, because empty means feature disabled
                'location%dContainerType' % locationIndex: '?', # use ? to indicate location without container, because empty means feature disabled
                'location%dProhibited' % locationIndex: True,
            })

            # run customer code
            actualContainerId, actualContainerType = loop.run_until_complete(self._materialHandler.MoveLocationAsync(locationIndex, expectedContainerId, expectedContainerType, orderUniqueId))
            finishCode = PLCMoveLocationFinishCode.Success

        except Exception as e:
            log.exception('%smoveLocation%d thread error: %s', self._logPrefix, locationIndex, e)
            finishCode = PLCMoveLocationFinishCode.GenericError

        finally:
            log.debug('%smoveLocation%d thread stopping', self._logPrefix, locationIndex)
            controller.WaitUntil('startMoveLocation%d' % locationIndex, False)
            controller.SetMultiple({
                'moveLocation%dFinishCode' % locationIndex: int(finishCode),
                'isRunningMoveLocation%d' % locationIndex: False,
                'location%dContainerId' % locationIndex: actualContainerId,
                'location%dContainerType' % locationIndex: actualContainerType,
                'location%dProhibited' % locationIndex: False,
            })
            self._moveLocationThreads[locationIndex] = None
            loop.close()

    def _RunFinishOrderThread(self) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        finishCode = PLCFinishOrderFinishCode.GenericError
        try:
            if not controller.SyncAndGetBoolean('startFinishOrder'):
                # trigger no longer alive
                return

            # first garther parameters
            orderUniqueId = controller.GetString('finishOrderOrderUniqueId')
            orderCycleFinishCode = plclogic.PLCOrderCycleFinishCode(controller.GetInteger('finishOrderOrderCycleFinishCode'))
            numPutInDestination = controller.GetInteger('finishOrderNumPutInDestination')

            # set output signals first
            controller.SetMultiple({
                'finishOrderFinishCode': PLCFinishOrderFinishCode.NotAvailable,
                'isRunningFinishOrder': True,
            })

            # run customer code
            loop.run_until_complete(self._materialHandler.FinishOrderAsync(orderUniqueId, orderCycleFinishCode, numPutInDestination))
            finishCode = PLCFinishOrderFinishCode.Success

        except Exception as e:
            log.exception('%sfinishOrder thread error: %s', self._logPrefix, e)
            finishCode = PLCFinishOrderFinishCode.GenericError

        finally:
            log.debug('%sfinishOrder thread stopping', self._logPrefix)
            controller.WaitUntil('startFinishOrder', False)
            controller.SetMultiple({
                'finishOrderFinishCode': int(finishCode),
                'isRunningFinishOrder': False,
            })
            self._finishOrderThread = None
            loop.close()
