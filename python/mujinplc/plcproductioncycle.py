# -*- coding: utf-8 -*-

import threading
import typing
import time
import enum

from . import plcmemory, plccontroller
from .plcproductionrunner import PLCQueueOrderFinishCode
from . import PLCDataObject

import logging
log = logging.getLogger(__name__)

class PLCOrder(PLCDataObject):
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
    Idle = 'idle'
    Starting = 'starting'
    Running = 'running'
    Stopping = 'stopping'
    Stopped = 'stopped'

class PLCOrderCycleState(enum.Enum):
    Idle = 'idle'
    Starting = 'starting'
    Running = 'running'
    Error = 'error'
    Stopping = 'stopping'
    Stopped = 'stopped'

class PLCPreparationCycleState(enum.Enum):
    Idle = 'idle'
    Starting = 'starting'
    Running = 'running'
    Error = 'error'
    Stopping = 'stopping'
    Stopped = 'stopped'

class PLCQueueOrderState(enum.Enum):
    Idle = 'idle'
    Running = 'running'
    Finished = 'finished'

class PLCMoveLocationState(enum.Enum):
    Idle = 'idle'

class PLCProductionCycle:
    
    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _locationIndices = None # type: typing.List[int]
    _locationsQueue = {} # type: typing.Dict[int, typing.List[PLCOrder]]
    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _state = None # type: typing.Tuple[PLCProductionCycleState, float] # current state and state transition timestamp
    _orderCycleState = None # type: typing.Tuple[PLCOrderCycleState, float, typing.Optional[PLCOrder]] # current state and state transition timestamp and current order
    _preparationCycleState = None # type: typing.Tuple[PLCPreparationCycleState, float, typing.Optional[PLCOrder]] # current state and state transition timestamp and current order
    _queueOrderState = None # type: typing.Tuple[PLCQueueOrderState, float]
    _moveLocationStates = None # type: typing.Dict[int, typing.Tuple[PLCMoveLocationState, float, typing.Optional[PLCOrder]]]

    def __init__(self, memory: plcmemory.PLCMemory, maxLocationIndex: int = 4):
        self._memory = memory
        self._locationIndices = list(range(1, maxLocationIndex + 1))
        for locationIndex in self._locationIndices:
            self._locationsQueue[locationIndex] = []

        timestamp = time.monotonic()
        self._state = (PLCProductionCycleState.Idle, timestamp)
        self._orderCycleState = (PLCOrderCycleState.Idle, timestamp, None)
        self._preparationCycleState = (PLCPreparationCycleState.Idle, timestamp, None)
        self._queueOrderState = (PLCQueueOrderState.Idle, timestamp)
        self._moveLocationStates = {}
        for locationIndex in self._locationIndices:
            self._moveLocationStates[locationIndex] = (PLCMoveLocationState.Idle, timestamp, None)

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

    def _RunThread(self) -> None:
        controller = plccontroller.PLCController(self._memory)

        while self._isok:
            controller.Wait(timeout=0.1)

            self._RunStateMachine(controller)
            self._RunOrderCycleStateMachine(controller)
            self._RunPreparationCycleStateMachine(controller)
            self._RunQueueOrderStateMachine(controller)
            for locationIndex in self._locationIndices:
                self._RunMoveLocationStateMachine(controller, locationIndex)

    #
    # Main Production Cycle State Machine
    #

    def _SetState(self, state: PLCProductionCycleState) -> None:
        if self._IsState(state):
            return
        timestamp = time.monotonic()
        log.debug('%s -> %s, previous state lasted %.03fs', self._state[0], state, timestamp - self._state[1])
        self._state = (state, timestamp)

    def _IsState(self, state: PLCProductionCycleState) -> bool:
        return self._state[0] == state

    def _RunStateMachine(self, controller: plccontroller.PLCController) -> None:
        # we start out in the Stopped state
        # here we wait for startProductionCycle trigger
        if self._IsState(PLCProductionCycleState.Idle):
            controller.Set('isRunningProductionCycle', False)

            if controller.GetBoolean('startProductionCycle'):
                self._SetState(PLCProductionCycleState.Starting)
        
        # once startProductionCycle triggered
        # we wait for the trigger to go down first
        # before actually running any processing
        if self._IsState(PLCProductionCycleState.Starting):
            controller.Set('isRunningProductionCycle', True)

            if not controller.GetBoolean('startProductionCycle'):
                self._SetState(PLCProductionCycleState.Running)
        
        # this is the idle state, when the production cycle has started
        if self._IsState(PLCProductionCycleState.Running):
            controller.Set('isRunningProductionCycle', True)

            if controller.GetBoolean('stopProductionCycle'):
                self._SetState(PLCProductionCycleState.Stopping)

        # when stop is requested, we first need to cleanup
        # when everything is stopped, we can then transition to stopping state
        if self._IsState(PLCProductionCycleState.Stopping):
            controller.Set('isRunningProductionCycle', True)

            if self._IsOrderCycleState(PLCOrderCycleState.Stopped) and self._IsPreparationCycleState(PLCPreparationCycleState.Stopped):
                self._SetState(PLCProductionCycleState.Stopped)

        # when we receive stopProductionCycle, we need to wait for trigger to go down
        if self._IsState(PLCProductionCycleState.Stopped):
            controller.Set('isRunningProductionCycle', False)

            if not controller.GetBoolean('stopProductionCycle'):
                self._SetState(PLCProductionCycleState.Idle)

    #
    # Order Cycle State Machine
    #

    def _SetOrderCycleState(self, state: PLCOrderCycleState, order: typing.Optional[PLCOrder] = None) -> None:
        if self._IsOrderCycleState(state):
            return
        timestamp = time.monotonic()
        log.debug('%s (%r) -> %s (%r), previous state lasted %.03fs', self._orderCycleState[0], self._orderCycleState[2], state, order, timestamp - self._orderCycleState[1])
        self._orderCycleState = (state, timestamp, order)

    def _IsOrderCycleState(self, state: PLCOrderCycleState) -> bool:
        return self._orderCycleState[0] == state

    def _GetOrderCycleStateOrder(self) -> PLCOrder:
        assert(self._orderCycleState[0] in (PLCOrderCycleState.Starting, PLCOrderCycleState.Running))
        order = self._orderCycleState[2]
        assert(order is not None)
        return order

    def _RunOrderCycleStateMachine(self, controller: plccontroller.PLCController) -> None:
        if self._IsOrderCycleState(PLCOrderCycleState.Idle):
            if not self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Stopping)
            else:
                # start out with nothing running
                # pick an order to start executing without preparation
                order = None # self._SelectNextOrder()
                if order:
                    self._SetOrderCycleState(PLCOrderCycleState.Starting, order)

        # after starting the order, check that source and dest matches requirement, and call moveLocation if necessary
        # after starting the order, pick an order to start preparation
        # after starting the preparation, check that source and dest matches requirment, and call moveLocation if necessary
        # when order finish, call finishOrder
        # after finishOrder, wait for preparation to finish and start order

        if self._IsOrderCycleState(PLCOrderCycleState.Starting):
            order = self._GetOrderCycleStateOrder()
            controller.SetMultiple({
                'orderUniqueId': order.uniqueId,

                'orderPartType': order.partType,
                'orderPartSizeX': order.partSizeX,
                'orderPartSizeY': order.partSizeY,
                'orderPartSizeZ': order.partSizeZ,

                'orderNumber': order.orderNumber,
                'orderRobotId': order.robotId,

                'orderPickLocationIndex': order.pickLocationIndex,
                'orderPickContainerId': order.pickContainerId,
                'orderPickContainerType': order.pickContainerType,

                'orderPlaceLocationIndex': order.placeLocationIndex,
                'orderPlaceContainerId': order.placeContainerId,
                'orderPlaceContainerType': order.placeContainerType,

                'startOrderCycle': True,
                'stopOrderCycle': False,
            })            

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Stopping)
            elif controller.GetBoolean('isRunningOrderCycle'):
                self._SetOrderCycleState(PLCOrderCycleState.Running)

        if self._IsOrderCycleState(PLCOrderCycleState.Running):
            controller.Set('startOrderCycle', False)

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Stopping)
            elif not controller.GetBoolean('isRunningOrderCycle'):
                # handle isError and orderCycleFinishCode here
                pass

        if self._IsOrderCycleState(PLCOrderCycleState.Stopping):
            controller.SetMultiple({
                'stopImmediately': True,
                'stopOrderCycle': True,
                'startOrderCycle': False,
            })

            if not controller.GetBoolean('isRunningOrderCycle'):
                self._SetOrderCycleState(PLCOrderCycleState.Stopped)

        if self._IsOrderCycleState(PLCOrderCycleState.Stopped):
            controller.SetMultiple({
                'stopImmediately': False,
                'stopOrderCycle': False,
                'startOrderCycle': False,
            })

            if self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Idle)

    #
    # Preparation Cycle State Machine
    #

    def _SetPreparationCycleState(self, state: PLCPreparationCycleState, order: typing.Optional[PLCOrder] = None) -> None:
        if self._IsPreparationCycleState(state):
            return
        timestamp = time.monotonic()
        log.debug('%s (%r) -> %s (%r), previous state lasted %.03fs', self._preparationCycleState[0], self._preparationCycleState[2], state, order, timestamp - self._preparationCycleState[1])
        self._preparationCycleState = (state, timestamp, order)

    def _IsPreparationCycleState(self, state: PLCPreparationCycleState) -> bool:
        return self._preparationCycleState[0] == state

    def _GetPreparationCycleStateOrder(self) -> PLCOrder:
        assert(self._preparationCycleState[0] in (PLCPreparationCycleState.Starting, PLCPreparationCycleState.Running))
        order = self._preparationCycleState[2]
        assert(order is not None)
        return order

    def _RunPreparationCycleStateMachine(self, controller: plccontroller.PLCController) -> None:
        if self._IsPreparationCycleState(PLCPreparationCycleState.Idle):
            if not self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)
            elif self._IsOrderCycleState(PLCOrderCycleState.Running):
                order = None # self._SelectNextOrder()
                if order:
                    self._SetPreparationCycleState(PLCPreparationCycleState.Starting, order)

        if self._IsPreparationCycleState(PLCPreparationCycleState.Starting):
            order = self._GetOrderCycleStateOrder()
            controller.SetMultiple({
                'preparationUniqueId': order.uniqueId,

                'preparationPartType': order.partType,
                'preparationPartSizeX': order.partSizeX,
                'preparationPartSizeY': order.partSizeY,
                'preparationPartSizeZ': order.partSizeZ,

                'preparationOrderNumber': order.orderNumber,
                'preparationRobotId': order.robotId,

                'preparationPickLocationIndex': order.pickLocationIndex,
                'preparationPickContainerId': order.pickContainerId,
                'preparationPickContainerType': order.pickContainerType,

                'preparationPlaceLocationIndex': order.placeLocationIndex,
                'preparationPlaceContainerId': order.placeContainerId,
                'preparationPlaceContainerType': order.placeContainerType,

                'startPreparation': True,
                'stopPreparation': False,
            })            

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)
            elif controller.GetBoolean('isRunningPreparation'):
                self._SetPreparationCycleState(PLCPreparationCycleState.Running)

        if self._IsPreparationCycleState(PLCPreparationCycleState.Running):
            controller.Set('startPreparation', False)

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)
            elif not controller.GetBoolean('isRunningPreparation'):
                # handle isError and orderCycleFinishCode here
                pass

        if self._IsPreparationCycleState(PLCPreparationCycleState.Stopping):
            controller.SetMultiple({
                'stopPreparation': True,
                'startPreparation': False,
            })

            if not controller.GetBoolean('isRunningPreparation'):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopped)

        if self._IsPreparationCycleState(PLCPreparationCycleState.Stopped):
            controller.SetMultiple({
                'stopPreparation': False,
                'startPreparation': False,
            })

            if self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Idle)

    #
    # Move Location State Machine
    #

    def _SetMoveLocationState(self, locationIndex: int, state: PLCMoveLocationState, order: typing.Optional[PLCOrder] = None) -> None:
        if self._IsMoveLocationState(locationIndex, state):
            return
        timestamp = time.monotonic()
        log.debug('%s (%r) -> %s (%r), previous state lasted %.03fs', self._moveLocationStates[locationIndex][0], self._moveLocationStates[locationIndex][2], state, order, timestamp - self._moveLocationStates[locationIndex][1])
        self._moveLocationStates[locationIndex] = (state, timestamp, order)

    def _IsMoveLocationState(self, locationIndex: int, state: PLCMoveLocationState) -> bool:
        return self._moveLocationStates[locationIndex][0] == state

    def _GetMoveLocationStateOrder(self, locationIndex: int) -> PLCOrder:
        assert(self._moveLocationStates[locationIndex][0] in (PLCPreparationCycleState.Starting, PLCPreparationCycleState.Running))
        order = self._moveLocationStates[locationIndex][2]
        assert(order is not None)
        return order

    def _RunMoveLocationStateMachine(self, controller: plccontroller.PLCController, locationIndex: int) -> None:
        if self._IsMoveLocationState(locationIndex, PLCMoveLocationState.Idle):
            pass

    #
    # Queue Order State Machine
    #

    def _SetQueueOrderState(self, state: PLCQueueOrderState) -> None:
        if self._IsQueueOrderState(state):
            return
        timestamp = time.monotonic()
        log.debug('%s -> %s, previous state lasted %.03fs', self._queueOrderState[0], state, timestamp - self._queueOrderState[1])
        self._queueOrderState = (state, timestamp)

    def _IsQueueOrderState(self, state: PLCQueueOrderState) -> bool:
        return self._queueOrderState[0] == state

    def _RunQueueOrderStateMachine(self, controller: plccontroller.PLCController) -> None:
        if self._IsQueueOrderState(PLCQueueOrderState.Idle):
            controller.SetMultiple({
                'isRunningQueueOrder': False,
                'queueOrderFinishCode': int(PLCQueueOrderFinishCode.NotAvailable),
            })

            if controller.GetBoolean('startQueueOrder'):
                order = PLCOrder(
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
                # TODO: save the order in the state and do the actual queuing in the next state
                self._locationsQueue[order.pickLocationIndex].append(order)
                self._SetQueueOrderState(PLCQueueOrderState.Running)
                log.debug('order queued: %r', order)

        if self._IsQueueOrderState(PLCQueueOrderState.Running):
            controller.Set('isRunningQueueOrder', True)

            if not controller.GetBoolean('startQueueOrder'):
                self._SetQueueOrderState(PLCQueueOrderState.Finished)

        if self._IsQueueOrderState(PLCQueueOrderState.Finished):
            controller.SetMultiple({
                'isRunningQueueOrder': False,
                'queueOrderFinishCode': int(PLCQueueOrderFinishCode.Success),
            })
            self._SetQueueOrderState(PLCQueueOrderState.Idle)
