# -*- coding: utf-8 -*-

import threading
import typing
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
    _preparedOrder = None # type: typing.Optional[PLCPickWorkerOrder]

    def __init__(self, memory: plcmemory.PLCMemory):
        self._memory = memory

    async def RunOrderCycleAsync(self, order: PLCPickWorkerOrder) -> PLCOrderCycleStatus:
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

        log.warn('running order cycle: %r, isPrepared = %r', order, isPrepared)
        while True:
            await asyncio.sleep(0.2)
            controller.Sync()
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
        log.info('containers in position for order cycle')
        if not isPrepared:
            await asyncio.sleep(5)
        controller.Set('isRobotMoving', True)
        for numPutInDestination in range(1, order.orderNumber + 1):
            await asyncio.sleep(5)
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
        controller = plccontroller.PLCController(self._memory)

        self._preparedOrder = None

        log.warn('running preparation: %r', order)
        while True:
            await asyncio.sleep(0.2)
            controller.Sync()
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
        log.info('containers in position for preparation')

        await asyncio.sleep(4)
        self._preparedOrder = order
        return PLCPreparationCycleStatus(
            preparationFinishCode = PLCPreparationFinishCode.PreparationFinishedSuccess,
        )

    async def ResetError(self) -> None:
        log.debug('')

class PLCPickWorkerSimulator:

    _memory = None # type: plcmemory.PLCMemory
    _backend = None # type: PLCPickWorkerBackend

    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _threads = None # type: typing.Dict[str, typing.Optional[threading.Thread]]

    def __init__(self, memory: plcmemory.PLCMemory, backend: typing.Optional[PLCPickWorkerBackend] = None):
        self._memory = memory
        self._backend = backend or PLCPickWorkerBackend(memory)
        self._threads = {
            'resetError': None,
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
            'isSystemReady':  True,
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
                'startOrderCycle': self._RunOrderCycleThread,
                'startPreparation': self._RunPreparationCycleThread,
            }
            for triggerSignal, target in triggerMapping.items():
                if triggerSignal in triggerSignals and controller.GetBoolean(triggerSignal):
                    log.debug('starting a thread to handle: %s', triggerSignal)
                    thread = threading.Thread(target=target, name=triggerSignal)
                    thread.start()
                    self._threads[triggerSignal] = thread

        controller.SetMultiple({
            'isModeAuto': False,
            'isSystemReady':  False,
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
            log.exception('resetError thread error: %s', e)

        finally:
            log.debug('resetError thread stopping')
            controller.SetMultiple({
                'isError': False,
                'errorcode': 0,
                'detailcode': '',
            })
            self._threads['resetError'] = None
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
                pickLocationIndex = controller.GetInteger('orderPickLocationIndex'),
                pickContainerId = controller.GetString('orderPickContainerId'),
                pickContainerType = controller.GetString('orderPickContainerType'),
                placeLocationIndex = controller.GetInteger('orderPlaceLocationIndex'),
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

            controller.WaitUntil('startOrderCycle', False)

        except PLCError as e:
            log.exception('orderCycle plc error: %s', e)
            status.orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedGenericFailure
            controller.SetMultiple({
                'isError': True,
                'errorcode': int(e.GetErrorCode()),
                'detailcode': e.GetErrorDetail(),
                'isRunningOrderCycle': False,
            })

        except Exception as e:
            log.exception('orderCycle thread error: %s', e)
            status.orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedGenericFailure

        finally:
            log.debug('orderCycle thread stopping')
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
                pickLocationIndex = controller.GetInteger('preparationPickLocationIndex'),
                pickContainerId = controller.GetString('preparationPickContainerId'),
                pickContainerType = controller.GetString('preparationPickContainerType'),
                placeLocationIndex = controller.GetInteger('preparationPlaceLocationIndex'),
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

            controller.WaitUntil('startOrderCycle', False)

        except PLCError as e:
            log.exception('preparationCycle plc error: %s', e)
            status.preparationFinishCode = PLCPreparationFinishCode.PreparationFinishedGenericError
            controller.SetMultiple({
                'isError': True,
                'errorcode': int(e.GetErrorCode()),
                'detailcode': e.GetErrorDetail(),
                'isRunningPreparation': False,
            })

        except Exception as e:
            log.exception('preparationCycle thread error: %s', e)
            status.preparationFinishCode = PLCPreparationFinishCode.PreparationFinishedGenericError

        finally:
            log.debug('preparationCycle thread stopping')
            controller.SetMultiple({
                'orderCycleFinishCode': int(status.preparationFinishCode),
                'isRunningPreparation': False,
            })
            self._threads['startPreparation'] = None
            loop.close()
