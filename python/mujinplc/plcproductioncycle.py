# -*- coding: utf-8 -*-

import threading
import typing
import time
import enum

from . import plcmemory, plccontroller, plclogic
from .plcproductionrunner import PLCQueueOrderFinishCode
from . import PLCDataObject

import logging
log = logging.getLogger(__name__)

class PLCProductionCycleOrder(PLCDataObject):
    """
    Struct describing order data. This PLCOrder class is used internally.
    """
    uniqueId = '' # type: str

    partType = '' # type: str # type of the product to be picked, for example: 'cola'
    partSizeX = 0 # type: int
    partSizeY = 0 # type: int
    partSizeZ = 0 # type: int

    orderNumber = 0 # type: int # number of items to be picked, for example: 1

    robotId = 0 # type: int # set to 1

    pickLocationIndex = 0 # type: int # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # type: str # barcode of the source container, for example: '010023'
    pickContainerType = '' # type: str # type of the source container, if all the same, set to ''

    placeLocationIndex = 0 # type: int # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # type: str # barcode of the dest contianer, for example: 'pallet1'
    placeContainerType = '' # type: str # type of the source container, if all the same, set to ''

    packInputPartIndex = 0 # type: int # when using packFormation, index of the part in the pack
    packFormationComputationName = '' # type: str # when using packFormation, name of the formation

class PLCProductionCycleState(enum.Enum):
    Starting = 'starting'
    Started = 'started'
    Cleanup = 'cleanup'
    Stopping = 'stopping'
    Stopped = 'stopped' # production cycle stopped. Waiting for startProductionCycle to be true.
    
    

    Idle = 'idle' # Production Cycle is started.  Queue is empty. System is in Idle.
    Start = 'start' # Queue has order, start to deal with new order.
    Running = 'running' # Order from start state meet the condition , start to run order.
    Finished = 'finished' # Order Finished. Publish orderFinishCode to high level system and wait for return to continue.

class PLCProductionCycle:
    
    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _locationIndices = None # type: typing.List[int]
    _locationsQueue = {} # type: typing.Dict[int, typing.List[PLCProductionCycleOrder]]
    _locationsQueueLock = {} # type: typing.Dict[int, threading.Lock]
    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _state = (PLCProductionCycleState.Stopped, 0) # type: typing.Tuple[PLCProductionCycleState, float] # current state and state transition timestamp

    def __init__(self, memory: plcmemory.PLCMemory, maxLocationIndex: int = 4):
        self._memory = memory
        self._locationIndices = list(range(1, maxLocationIndex + 1))
        for locationIndex in self._locationIndices:
            self._locationsQueue[locationIndex] = []
            self._locationsQueueLock[locationIndex] = threading.Lock()
        self._state = (PLCProductionCycleState.Stopped, time.monotonic())

    def _EnqueueOrder(self, order: PLCProductionCycleOrder) -> None:
        if order.orderNumber <= 0:
            raise ValueError('invalid orderNumber (%d)' % order.orderNumber)
        if order.pickLocationIndex not in self._locationIndices:
            raise ValueError('invalid pickLocationIndex (%d)' % order.pickLocationIndex)
        if order.placeLocationIndex not in self._locationIndices:
            raise ValueError('invalid placeLocationIndex (%d)' % order.placeLocationIndex)
        # TODO: check other values here

        locationIndex = order.pickLocationIndex
        with self._locationsQueueLock[locationIndex]:
            self._locationsQueue[locationIndex].append(order)
            log.debug('enqueued order %r, queue length is now %d', order, len(self._locationsQueue[locationIndex]))

    def _DequeueOrder(self, locationIndex: int) -> PLCProductionCycleOrder:
        """
        Deqeue first order from locationIndex queue
        """
        with self._locationsQueueLock[locationIndex]:
            order = self._locationsQueue[locationIndex].pop(0)
            log.debug('dequeued order %r, queue length is now %d', order, len(self._locationsQueue[locationIndex]))
            return order

    def __del__(self):
        self.Stop()

    def Start(self) -> None:
        self.Stop()

        # start the main monitoring thread
        self._isok = True
        self._thread = threading.Thread(target=self._RunThread, name='plcproductioncycle')
        self._thread.start()
        self._queueOrderThread = threading.Thread(target=self._RunQueueOrderThread, name='plcqueueorder')
        self._queueOrderThread.start()

    def Stop(self) -> None:
        self._isok = False
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _SetState(self, state: PLCProductionCycleState) -> None:
        if self._IsState(state):
            return
        timestamp = time.monotonic()
        log.debug('%s -> %s, previous state lasted %.03fs', self._state[0], state, timestamp - self._state[1])
        self._state = (state, timestamp)

    def _IsState(self, state: PLCProductionCycleState) -> bool:
        return self._state[0] == state

    def _RunThread(self) -> None:
        controller = plccontroller.PLCController(self._memory)
        controller.SetMultiple({
            'isRunningProductionCycle': False,
        })

        self._SetState(PLCProductionCycleState.Stopped)

        while self._isok:
            # signal changes to watch for
            controller.WaitForAny({
                'startProductionCycle': None,
                'stopProductionCycle': None,
                'isRunningOrderCycle': None,
                'isRunningPreparation': None,
            }, timeout=0.1)

            # we start out in the Stopped state
            # here we wait for startProductionCycle trigger
            if self._IsState(PLCProductionCycleState.Stopped):
                if controller.GetBoolean('startProductionCycle'):
                    self._SetState(PLCProductionCycleState.Starting)
            
            # once startProductionCycle triggered
            # we wait for the trigger to go down first
            # before actually running any processing
            if self._IsState(PLCProductionCycleState.Starting):
                controller.Set('isRunningProductionCycle', True)
                if not controller.GetBoolean('startProductionCycle'):
                    self._SetState(PLCProductionCycleState.Started)
            
            # this is the idle state, when the production cycle has started
            if self._IsState(PLCProductionCycleState.Started):
                if controller.GetBoolean('stopProductionCycle'):
                    self._SetState(PLCProductionCycleState.Cleanup)

            # when stop is requested, we first need to cleanup
            # when everything is stopped, we can then transition to stopping state
            if self._IsState(PLCProductionCycleState.Cleanup):
                controller.SetMultiple({
                    'stopImmediately': True,
                    'stopOrderCycle': True,
                    'stopPreparationCycle': True,
                })
                if not controller.GetBoolean('isRunningOrderCycle') and not controller.GetBoolean('isRunningPreparation'):
                    self._SetState(PLCProductionCycleState.Stopping)

            # when we receive stopProductionCycle, we need to wait for trigger to go down
            if self._IsState(PLCProductionCycleState.Stopping):
                controller.SetMultiple({
                    'stopImmediately': False,
                    'stopOrderCycle': False,
                    'stopPreparationCycle': False,
                    'isRunningProductionCycle': False,
                })
                if not controller.GetBoolean('stopProductionCycle'):
                    self._SetState(PLCProductionCycleState.Stopped)

        controller.SetMultiple({
            'isRunningProductionCycle': False,
        })

    def _RunQueueOrderThread(self):
        controller = plccontroller.PLCController(self._memory)
        controller.SetMultiple({
            'isRunningQueueOrder': False,
            'queueOrderOrderFinishCode': int(PLCQueueOrderFinishCode.NotAvailable),
        })

        while self._isok:
            if not controller.WaitUntil('startQueueOrder', True, timeout=0.1):
                continue

            finishCode = PLCQueueOrderFinishCode.NotAvailable
            order = PLCProductionCycleOrder(
                uniqueId = controller.GetString('queueOrderUniqueId'),

                partType = controller.GetString('queueOrderPartType'),
                partSizeX = controller.GetInteger('queueOrderPartSizeX'),
                partSizeY = controller.GetInteger('queueOrderPartSizeY'),
                partSizeZ = controller.GetInteger('queueOrderPartSizeZ'),

                orderNumber = controller.GetInteger('queueOrderNumber'),

                robotId = controller.GetInteger('queueOrderRobotId'),

                pickLocationIndex = controller.GetInteger('queueOrderPickLocationIndex'),
                pickContainerId = controller.GetString('queueOrderPickContainerId'),
                pickContainerType = controller.GetString('queueOrderPickContainerType'),

                placeLocationIndex = controller.GetInteger('queueOrderPlaceLocationIndex'),
                placeContainerId = controller.GetString('queueOrderPlaceContainerId'),
                placeContainerType = controller.GetString('queueOrderPlaceContainerIndex'),

                packInputPartIndex = controller.GetInteger('queueOrderPackInputPartIndex'),
                packFormationComputationName = controller.GetString('queueOrderPackFormationComputationName'),
            )
            controller.SetMultiple({
                'isRunningQueueOrder': False,
                'queueOrderOrderFinishCode': int(finishCode),
            })

            try:
                self._EnqueueOrder(order)
                finishCode = PLCQueueOrderFinishCode.Success
            except Exception as e:
                log.exception('QueueOrder %r error: %s', order, e)
                finishCode = PLCQueueOrderFinishCode.GenericError
            finally:
                controller.WaitUntil('startQueueOrder', False)
                controller.SetMultiple({
                    'isRunningQueueOrder': False,
                    'queueOrderFinishCode': int(finishCode),
                })
