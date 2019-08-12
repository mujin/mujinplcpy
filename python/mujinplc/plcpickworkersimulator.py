# -*- coding: utf-8 -*-

import threading
import typing # noqa: F401 # used in type check
import asyncio
import time

from . import plcmemory, plccontroller
from . import PLCDataObject
from .plclogic import PLCOrderCycleStatus, PLCOrderCycleFinishCode, PLCPreparationCycleStatus, PLCPreparationFinishCode, PLCError

import logging
log = logging.getLogger(__name__)

class PLCPickWorkerOrder(PLCDataObject):
    uniqueId = '' # type: str

    partType = '' # type: str # type of the product to be picked, for example: "cola"

    orderNumber = 0 # type: int # number of items to be picked, for example: 1

    robotName = '' # type: str

    pickLocationIndex = 0 # type: int # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # type: str # barcode of the source container, for example: "010023"
    pickContainerType = '' # type: str # type of the source container, if all the same, set to ""

    placeLocationIndex = 0 # type: int # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # type: str # barcode of the dest contianer, for example: "pallet1"
    placeContainerType = '' # type: str # type of the source container, if all the same, set to ""

class PLCPickWorkerBackend:

    _memory = None # type: plcmemory.PLCMemory
    _logPrefix = '' # type: str
    _preparedOrder = None # type: typing.Optional[PLCPickWorkerOrder]
    _clearStatePerformed = False # type: bool

    def __init__(self, memory: plcmemory.PLCMemory, logPrefix: str = ''):
        self._memory = memory
        self._logPrefix = logPrefix

    async def RunOrderCycleAsync(self, order: PLCPickWorkerOrder) -> PLCOrderCycleStatus:
        if not self._clearStatePerformed:
            log.error('%srunning order cycle without first clearing state', self._logPrefix)

        controller = plccontroller.PLCController(self._memory)

        isPrepared = False
        if self._preparedOrder is not None and \
           self._preparedOrder.uniqueId == order.uniqueId and \
           self._preparedOrder.partType == order.partType and \
           self._preparedOrder.orderNumber == order.orderNumber and \
           self._preparedOrder.robotName == order.robotName and \
           self._preparedOrder.pickLocationIndex == order.pickLocationIndex and \
           self._preparedOrder.pickContainerId == order.pickContainerId and \
           self._preparedOrder.pickContainerType == order.pickContainerType and \
           self._preparedOrder.placeLocationIndex == order.placeLocationIndex and \
           self._preparedOrder.placeContainerId == order.placeContainerId and \
           self._preparedOrder.placeContainerType == order.placeContainerType:
            isPrepared = True
            self._preparedOrder = None

        if isPrepared:
            log.warn('%srunning prepared order cycle: %r', self._logPrefix, order)
        else:
            log.error('%srunning unprepared order cycle: %r', self._logPrefix, order)

        while True:
            await asyncio.sleep(0.1)
            controller.Sync()
            if controller.GetBoolean('stopOrderCycle'):
                raise Exception('Interrupted')
            if controller.GetString('location%dProhibited' % order.pickLocationIndex):
                continue
            if controller.GetString('location%dProhibited' % order.placeLocationIndex):
                continue
            if controller.GetString('location%dContainerId' % order.pickLocationIndex) != order.pickContainerId:
                continue
            if controller.GetString('location%dContainerType' % order.pickLocationIndex) != order.pickContainerType:
                continue
            if controller.GetString('location%dContainerId' % order.placeLocationIndex) != order.placeContainerId:
                continue
            if controller.GetString('location%dContainerType' % order.placeLocationIndex) != order.placeContainerType:
                continue
            break
        log.info('%scontainers in position for order cycle', self._logPrefix)
        if not isPrepared:
            for timeout in range(5):
                if controller.SyncAndGetBoolean('stopOrderCycle'):
                    raise Exception('Interrupted')
            await asyncio.sleep(0.1)

        controller.Set('isRobotMoving', True)
        for numPutInDestination in range(1, order.orderNumber + 1):
            for timeout in range(5):
                if controller.SyncAndGetBoolean('stopOrderCycle'):
                    raise Exception('Interrupted')
                await asyncio.sleep(0.1)
            controller.SetMultiple({
                'numPutInDestination': numPutInDestination,
                'numLeftInOrder': order.orderNumber - numPutInDestination,
            })
        controller.Set('isRobotMoving', False)

        return PLCOrderCycleStatus(
            orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedOrderComplete,
            numPutInDestination = order.orderNumber,
            numLeftInOrder = 0,
        )

    async def RunPreparationCycleAsync(self, order: PLCPickWorkerOrder) -> PLCPreparationCycleStatus:
        if not self._clearStatePerformed:
            log.error('%srunning preparation without first clearing state', self._logPrefix)

        controller = plccontroller.PLCController(self._memory)

        self._preparedOrder = None

        log.warn('%srunning preparation: %r', self._logPrefix, order)
        while True:
            await asyncio.sleep(0.1)
            controller.Sync()
            if controller.GetBoolean('stopPreparation'):
                raise Exception('Interrupted')
            if controller.GetString('location%dProhibited' % order.pickLocationIndex):
                continue
            if controller.GetString('location%dProhibited' % order.placeLocationIndex):
                continue
            if controller.GetString('location%dContainerId' % order.pickLocationIndex) != order.pickContainerId:
                continue
            if controller.GetString('location%dContainerType' % order.pickLocationIndex) != order.pickContainerType:
                continue
            if controller.GetString('location%dContainerId' % order.placeLocationIndex) != order.placeContainerId:
                continue
            if controller.GetString('location%dContainerType' % order.placeLocationIndex) != order.placeContainerType:
                continue
            break
        log.info('%scontainers in position for preparation', self._logPrefix)

        for timeout in range(5):
            if controller.SyncAndGetBoolean('stopPreparation'):
                raise Exception('Interrupted')
            await asyncio.sleep(0.1)

        self._preparedOrder = order
        return PLCPreparationCycleStatus(
            preparationFinishCode = PLCPreparationFinishCode.PreparationFinishedSuccess,
        )

    async def ResetError(self) -> None:
        log.debug('%sreset error', self._logPrefix)

    async def ClearState(self) -> None:
        log.debug('%sclear state', self._logPrefix)
        self._clearStatePerformed = True

class PLCPickWorkerSimulator:

    _memory = None # type: plcmemory.PLCMemory
    _logPrefix = '' # type: str
    _backend = None # type: PLCPickWorkerBackend

    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _threads = None # type: typing.Dict[str, typing.Optional[threading.Thread]]

    def __init__(self, memory: plcmemory.PLCMemory, logPrefix: str = '', backend: typing.Optional[PLCPickWorkerBackend] = None):
        self._memory = memory
        self._logPrefix = logPrefix
        self._backend = backend or PLCPickWorkerBackend(memory, logPrefix=logPrefix)
        self._threads = {
            'resetError': None,
            'clearState': None,
            'startOrderCycle': None,
            'startPreparation': None,
        }

    def __del__(self):
        self.Stop()

    def Start(self) -> None:
        self.Stop()

        # start the main monitoring thread
        self._isok = True
        self._thread = threading.Thread(target=self._RunThread, name='plcpickworkersimulator')
        self._thread.start()

    def Stop(self) -> None:
        self._isok = False
        if self._thread is not None:
            self._thread.join()
            self._thread = None

        for trigger, thread in self._threads.items():
            if thread is not None:
                thread.join()
                self._threads[trigger] = None

    def _RunThread(self) -> None:
        controller = plccontroller.PLCController(self._memory)

        controller.SetMultiple({
            'isModeAuto': True,
            'isSystemReady': True,
            'isCycleReady': True,
        })

        while self._isok:
            controller.Wait(timeout=0.1)

            triggerSignals = {}
            for trigger, thread in self._threads.items():
                if thread is None:
                    triggerSignals[trigger] = True

            if not triggerSignals:
                # everything running, nothing new to trigger
                time.sleep(0.1)
                continue

            if not controller.WaitUntilAny(triggerSignals, timeout=0.1):
                # nothing need to be triggered
                continue

            triggerMapping = {
                'resetError': self._RunResetErrorThread,
                'clearState': self._RunClearStateThread,
                'startOrderCycle': self._RunOrderCycleThread,
                'startPreparation': self._RunPreparationCycleThread,
            }
            for triggerSignal, target in triggerMapping.items():
                if triggerSignal in triggerSignals and controller.GetBoolean(triggerSignal):
                    log.debug('%sstarting a thread to handle: %s', self._logPrefix, triggerSignal)
                    thread = threading.Thread(target=target, name=triggerSignal)
                    thread.start()
                    self._threads[triggerSignal] = thread

        controller.SetMultiple({
            'isModeAuto': False,
            'isSystemReady': False,
            'isCycleReady': False,
        })

    def _RunResetErrorThread(self) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        try:
            if not controller.SyncAndGetBoolean('resetError'):
                # trigger no longer alive
                return
            loop.run_until_complete(self._backend.ResetError())
        except Exception as e:
            log.exception('%sresetError thread error: %s', self._logPrefix, e)

        finally:
            log.debug('%sresetError thread stopping', self._logPrefix)
            controller.SetMultiple({
                'isError': False,
                'errorcode': 0,
                'detailcode': '',
            })
            controller.WaitUntil('resetError', False)
            controller.SetMultiple({
                'isError': False,
                'errorcode': 0,
                'detailcode': '',
            })
            self._threads['resetError'] = None
            loop.close()

    def _RunClearStateThread(self) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        try:
            if not controller.SyncAndGetBoolean('clearState'):
                # trigger no longer alive
                return
            loop.run_until_complete(self._backend.ClearState())
        except Exception as e:
            log.exception('%sclearState thread error: %s', self._logPrefix, e)

        finally:
            log.debug('%sclearState thread stopping', self._logPrefix)
            controller.SetMultiple({
                'clearStatePerformed': True,
            })
            controller.WaitUntil('clearState', False)
            controller.SetMultiple({
                'clearStatePerformed': False,
            })
            self._threads['clearState'] = None
            loop.close()

    def _RunOrderCycleThread(self) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        status = PLCOrderCycleStatus()
        try:
            if not controller.SyncAndGetBoolean('startOrderCycle'):
                # trigger no longer alive
                return

            # first garther parameters
            order = PLCPickWorkerOrder(
                uniqueId = controller.GetString('orderUniqueId'),
                partType = controller.GetString('orderPartType'),
                orderNumber = controller.GetInteger('orderNumber'),
                robotName = controller.GetString('orderRobotName'),
                pickLocationIndex = controller.GetInteger('orderPickLocation'),
                pickContainerId = controller.GetString('orderPickContainerId'),
                pickContainerType = controller.GetString('orderPickContainerType'),
                placeLocationIndex = controller.GetInteger('orderPlaceLocation'),
                placeContainerId = controller.GetString('orderPlaceContainerId'),
                placeContainerType = controller.GetString('orderPlaceContainerType'),
            )

            # set output signals first
            controller.SetMultiple({
                'numLeftInOrder': order.orderNumber,
                'numPutInDestination': 0,
                'orderCycleFinishCode': PLCOrderCycleFinishCode.FinishedNotAvailable,
                'isRunningOrderCycle': True,
            })

            # run backend code
            status = loop.run_until_complete(self._backend.RunOrderCycleAsync(order))

        except PLCError as e:
            log.exception('%sorderCycle plc error: %s', self._logPrefix, e)
            status.orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedGenericError
            controller.SetMultiple({
                'isError': True,
                'errorcode': int(e.GetErrorCode()),
                'detailcode': e.GetErrorDetail(),
                'isRunningOrderCycle': False,
            })

        except Exception as e:
            log.exception('%sorderCycle thread error: %s', self._logPrefix, e)
            status.orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedGenericError

        finally:
            log.debug('%sorderCycle thread stopping', self._logPrefix)
            controller.WaitUntil('startOrderCycle', False)
            controller.SetMultiple({
                'numLeftInOrder': status.numLeftInOrder,
                'numPutInDestination': status.numPutInDestination,
                'orderCycleFinishCode': int(status.orderCycleFinishCode),
                'isRunningOrderCycle': False,
            })
            self._threads['startOrderCycle'] = None
            loop.close()


    def _RunPreparationCycleThread(self) -> None:
        loop = asyncio.new_event_loop()
        controller = plccontroller.PLCController(self._memory)
        status = PLCPreparationCycleStatus()
        try:
            if not controller.SyncAndGetBoolean('startPreparation'):
                # trigger no longer alive
                return

            # first garther parameters
            order = PLCPickWorkerOrder(
                uniqueId = controller.GetString('preparationUniqueId'),
                partType = controller.GetString('preparationPartType'),
                orderNumber = controller.GetInteger('preparationOrderNumber'),
                robotName = controller.GetString('preparationRobotName'),
                pickLocationIndex = controller.GetInteger('preparationPickLocation'),
                pickContainerId = controller.GetString('preparationPickContainerId'),
                pickContainerType = controller.GetString('preparationPickContainerType'),
                placeLocationIndex = controller.GetInteger('preparationPlaceLocation'),
                placeContainerId = controller.GetString('preparationPlaceContainerId'),
                placeContainerType = controller.GetString('preparationPlaceContainerType'),
            )

            # set output signals first
            controller.SetMultiple({
                'preparationFinishCode': PLCPreparationFinishCode.PreparationNotAvailable,
                'isRunningPreparation': True,
            })

            # run backend code
            status = loop.run_until_complete(self._backend.RunPreparationCycleAsync(order))

        except PLCError as e:
            log.exception('%spreparationCycle plc error: %s', self._logPrefix, e)
            status.preparationFinishCode = PLCPreparationFinishCode.PreparationFinishedGenericError
            controller.SetMultiple({
                'isError': True,
                'errorcode': int(e.GetErrorCode()),
                'detailcode': e.GetErrorDetail(),
                'isRunningPreparation': False,
            })

        except Exception as e:
            log.exception('%spreparationCycle thread error: %s', self._logPrefix, e)
            status.preparationFinishCode = PLCPreparationFinishCode.PreparationFinishedGenericError

        finally:
            log.debug('%spreparationCycle thread stopping', self._logPrefix)
            controller.WaitUntil('startOrderCycle', False)
            controller.SetMultiple({
                'orderCycleFinishCode': int(status.preparationFinishCode),
                'isRunningPreparation': False,
            })
            self._threads['startPreparation'] = None
            loop.close()
