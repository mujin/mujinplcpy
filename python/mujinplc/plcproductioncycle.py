# -*- coding: utf-8 -*-

# TODO:
# - [ ] check isModeAuto
# - [ ] check isSystemReady
# - [ ] check isCycleReady
# - [ ] handle isError
# - [ ] stop productionCycle with error
# - [ ] add state timeouts

import threading
import typing # noqa: F401 # used in type check
import time
import enum

from . import plcmemory, plccontroller
from .plcproductionrunner import PLCMoveLocationFinishCode, PLCQueueOrderFinishCode, PLCFinishOrderFinishCode, PLCProductionCycleFinishCode
from .plclogic import PLCOrderCycleFinishCode, PLCPreparationFinishCode
from . import PLCDataObject

import logging
log = logging.getLogger(__name__)

class PLCOrder(PLCDataObject):
    """
    Struct describing order data. Used internally.
    """
    uniqueId = '' # type: str

    partType = '' # type: str # type of the product to be picked, for example: 'cola'
    partSizeX = 0 # type: int
    partSizeY = 0 # type: int
    partSizeZ = 0 # type: int

    orderNumber = 0 # type: int # number of items to be picked, for example: 1

    robotName = '' # type: str

    pickLocationIndex = 0 # type: int # index of location for source container, location defined on mujin pendant
    pickContainerId = '' # type: str # barcode of the source container, for example: '010023'
    pickContainerType = '' # type: str # type of the source container, if all the same, set to ''

    placeLocationIndex = 0 # type: int # index of location for dest container, location defined on mujin pendant
    placeContainerId = '' # type: str # barcode of the dest contianer, for example: 'pallet1'
    placeContainerType = '' # type: str # type of the source container, if all the same, set to ''

    packInputPartIndex = 0 # type: int # when using packFormation, index of the part in the pack
    packFormationComputationName = '' # type: str # when using packFormation, name of the formation

    numPutInDestination = 0 # type: int
    numLeftInOrder = 0 # type: int
    orderCycleFinishCode = PLCOrderCycleFinishCode.FinishedNotAvailable # type: PLCOrderCycleFinishCode
    preparationFinishCode = PLCPreparationFinishCode.PreparationNotAvailable # type: PLCPreparationFinishCode
    finishOrderFinishCode = PLCFinishOrderFinishCode.NotAvailable # type: PLCFinishOrderFinishCode

    ignoreFinishPosition = False # type: bool

    pickContainer = None # type: typing.Optional[PLCContainer]
    placeContainer = None # type: typing.Optional[PLCContainer]

class PLCContainer(PLCDataObject):
    """
    Struct describing a container on queue at a location. Used internally.
    """
    orders = None # type: typing.List[PLCOrder]

    locationIndex = 0 # type: int
    containerId = '' # type: str
    containerType = '' # type: str

    def __init__(self, *args, **kwargs):
        self.orders = []
        super(PLCContainer, self).__init__(*args, **kwargs)

class PLCLocationRequest(PLCDataObject):
    expectedContainerId = '' # type: str
    expectedContainerType = '' # type: str
    orderUniqueId = '' # type: str
    moveLocaitonFinishCode = PLCMoveLocationFinishCode.NotAvailable # type: PLCMoveLocationFinishCode

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
    Finish = 'finish'
    Finishing = 'finishing'
    Finished = 'finished'
    Stopping = 'stopping'
    Stopped = 'stopped'

class PLCPreparationCycleState(enum.Enum):
    Idle = 'idle'
    Starting = 'starting'
    Running = 'running'
    Stopping = 'stopping'
    Stopped = 'stopped'

class PLCLocationState(enum.Enum):
    Idle = 'idle'
    Move = 'move'
    Moving = 'moving'
    Moved = 'moved'
    Stopped = 'stopped'

class PLCQueueOrderState(enum.Enum):
    Idle = 'idle'
    Running = 'running'
    Succeeded = 'succeeded'
    Disabled = 'disabled'

class PLCProductionCycle:

    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _locationIndices = None # type: typing.List[int]
    _ordersQueue = None # type: typing.List[PLCOrder]
    _locationsQueue = None # type: typing.Dict[int, typing.List[PLCContainer]]
    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]
    _state = None # type: typing.Tuple[PLCProductionCycleState, float] # current state and state transition timestamp
    _orderCycleState = None # type: typing.Tuple[PLCOrderCycleState, float, typing.Optional[PLCOrder]] # current state and state transition timestamp and current order
    _preparationCycleState = None # type: typing.Tuple[PLCPreparationCycleState, float, typing.Optional[PLCOrder]] # current state and state transition timestamp and current order
    _queueOrderState = None # type: typing.Tuple[PLCQueueOrderState, float, typing.Optional[PLCOrder]]
    _locationStates = None # type: typing.Dict[int, typing.Tuple[PLCLocationState, float, typing.Optional[PLCLocationRequest]]]
    _lastPreparedOrder = None # type: typing.Optional[PLCOrder]

    def __init__(self, memory: plcmemory.PLCMemory, maxLocationIndex: int = 4):
        self._memory = memory
        self._locationIndices = list(range(1, maxLocationIndex + 1))
        self._ordersQueue = []
        self._locationsQueue = {}
        for locationIndex in self._locationIndices:
            self._locationsQueue[locationIndex] = []

        # initialize the states
        timestamp = time.monotonic()
        self._state = (PLCProductionCycleState.Idle, timestamp)
        self._orderCycleState = (PLCOrderCycleState.Idle, timestamp, None)
        self._preparationCycleState = (PLCPreparationCycleState.Idle, timestamp, None)
        self._locationStates = {}
        for locationIndex in self._locationIndices:
            self._locationStates[locationIndex] = (PLCLocationState.Stopped, timestamp, None)
        self._queueOrderState = (PLCQueueOrderState.Disabled, timestamp, None)

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
                self._RunLocationStateMachine(controller, locationIndex)

    #
    # Main Production Cycle State Machine
    #

    def _SetState(self, state: PLCProductionCycleState) -> None:
        if self._IsState(state):
            return
        timestamp = time.monotonic()
        log.info('%s -> %s, elapsed %.03fs', self._state[0], state, timestamp - self._state[1])
        self._state = (state, timestamp)

    def _IsState(self, *states: PLCProductionCycleState) -> bool:
        return self._state[0] in states

    def _RunStateMachine(self, controller: plccontroller.PLCController) -> None:
        # we start out in the Stopped state
        # here we wait for startProductionCycle trigger
        if self._IsState(PLCProductionCycleState.Idle):
            controller.Set('isRunningProductionCycle', False)

            if controller.GetBoolean('startProductionCycle') and not controller.GetBoolean('stopProductionCycle'):
                self._SetState(PLCProductionCycleState.Starting)

        # once startProductionCycle triggered
        # we wait for the trigger to go down first
        # before actually running any processing
        if self._IsState(PLCProductionCycleState.Starting):
            controller.SetMultiple({
                'isRunningProductionCycle': True,
                'productionCycleFinishCode': int(PLCProductionCycleFinishCode.NotAvailable),
            })

            if controller.GetBoolean('stopProductionCycle'):
                self._SetState(PLCProductionCycleState.Stopping)
            elif not controller.GetBoolean('startProductionCycle'):
                self._SetState(PLCProductionCycleState.Running)

        # this is the main running state, when the production cycle has started
        if self._IsState(PLCProductionCycleState.Running):
            controller.SetMultiple({
                'isRunningProductionCycle': True,
                'productionCycleFinishCode': int(PLCProductionCycleFinishCode.NotAvailable),
            })

            if controller.GetBoolean('stopProductionCycle'):
                self._SetState(PLCProductionCycleState.Stopping)

        # when stop is requested, we first need to cleanup
        # when everything is stopped, we can then transition to stopping state
        if self._IsState(PLCProductionCycleState.Stopping):
            controller.SetMultiple({
                'isRunningProductionCycle': True,
                'productionCycleFinishCode': int(PLCProductionCycleFinishCode.NotAvailable),
            })

            # check if everything is stopped, then transition to stopped state
            allFinished = True
            if not self._IsOrderCycleState(PLCOrderCycleState.Stopped):
                allFinished = False
            if not self._IsPreparationCycleState(PLCPreparationCycleState.Stopped):
                allFinished = False
            for locationIndex in self._locationIndices:
                if not self._IsLocationState(locationIndex, PLCLocationState.Stopped):
                    allFinished = False
            if not self._IsQueueOrderState(PLCQueueOrderState.Disabled):
                allFinished = False
            if allFinished:
                self._SetState(PLCProductionCycleState.Stopped)

        # when we receive stopProductionCycle, we need to wait for trigger to go down
        if self._IsState(PLCProductionCycleState.Stopped):
            controller.SetMultiple({
                'isRunningProductionCycle': False,
                'productionCycleFinishCode': int(PLCProductionCycleFinishCode.Success),
            })

            if not controller.GetBoolean('stopProductionCycle'):
                self._SetState(PLCProductionCycleState.Idle)

    #
    # Order Cycle State Machine
    #

    def _SetOrderCycleState(self, state: PLCOrderCycleState, order: typing.Optional[PLCOrder] = None) -> None:
        if self._IsOrderCycleState(state):
            return
        timestamp = time.monotonic()
        log.info('%s (%r) -> %s (%r), elapsed %.03fs', self._orderCycleState[0], self._orderCycleState[2], state, order, timestamp - self._orderCycleState[1])
        self._orderCycleState = (state, timestamp, order)

    def _IsOrderCycleState(self, *states: PLCOrderCycleState) -> bool:
        return self._orderCycleState[0] in states

    def _GetOrderCycleStateOrder(self) -> PLCOrder:
        order = self._orderCycleState[2]
        assert(order is not None)
        return order

    def _RunOrderCycleStateMachine(self, controller: plccontroller.PLCController) -> None:
        if self._IsOrderCycleState(PLCOrderCycleState.Idle):
            if not self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Stopping)
            elif not controller.GetBoolean('isModeAuto') or not controller.GetBoolean('isSystemReady') or not controller.GetBoolean('isCycleReady'):
                # need to wait until starting condition is met
                pass
            elif self._IsPreparationCycleState(PLCPreparationCycleState.Starting, PLCPreparationCycleState.Running):
                # if preparation is running, need to wait for it to finish
                pass
            else:
                candidate = None
                if self._lastPreparedOrder is not None and self._lastPreparedOrder in self._ordersQueue:
                    candidate = self._lastPreparedOrder
                else:
                    candidate = self._GetOrderCandidate()

                if candidate:
                    self._SetOrderCycleState(PLCOrderCycleState.Starting, candidate)

        if self._IsOrderCycleState(PLCOrderCycleState.Starting):
            order = self._GetOrderCycleStateOrder()
            controller.SetMultiple({
                'orderUniqueId': order.uniqueId,

                'orderPartType': order.partType,
                'orderPartSizeX': order.partSizeX,
                'orderPartSizeY': order.partSizeY,
                'orderPartSizeZ': order.partSizeZ,

                'orderNumber': order.orderNumber,
                'orderRobotName': order.robotName,

                'orderPickLocation': order.pickLocationIndex,
                'orderPickContainerId': order.pickContainerId,
                'orderPickContainerType': order.pickContainerType,

                'orderPlaceLocation': order.placeLocationIndex,
                'orderPlaceContainerId': order.placeContainerId,
                'orderPlaceContainerType': order.placeContainerType,

                'orderPackInputPartIndex': order.packInputPartIndex,
                'orderPackFormationComputationName': order.packFormationComputationName,
                'orderIgnoreFinishPosition': order.ignoreFinishPosition,

                'startOrderCycle': True,
                'stopOrderCycle': False,
            })

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Stopping)
            elif controller.GetBoolean('isRunningOrderCycle'):
                # prepared order is now used and cannot be used again
                if self._lastPreparedOrder is order:
                    self._lastPreparedOrder = None
                self._SetOrderCycleState(PLCOrderCycleState.Running, order)

        if self._IsOrderCycleState(PLCOrderCycleState.Running):
            controller.Set('startOrderCycle', False)

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Stopping)
            elif not controller.GetBoolean('isRunningOrderCycle'):
                # handle isError and orderCycleFinishCode here
                order = self._GetOrderCycleStateOrder()
                order.orderCycleFinishCode = PLCOrderCycleFinishCode(controller.GetInteger('orderCycleFinishCode'))
                order.numPutInDestination = controller.GetInteger('numPutInDestination')
                order.numLeftInOrder = controller.GetInteger('numLeftInOrder')
                self._SetOrderCycleState(PLCOrderCycleState.Finish, order)

        if self._IsOrderCycleState(PLCOrderCycleState.Finish):
            order = self._GetOrderCycleStateOrder()
            controller.SetMultiple({
                'finishOrderOrderUniqueId': order.uniqueId,
                'finishOrderOrderCycleFinishCode': int(order.orderCycleFinishCode),
                'finishOrderNumPutInDestination': order.numPutInDestination,
                'finishOrderNumLeftInOrder': order.numLeftInOrder,
                'startFinishOrder': True,
            })
            if controller.GetBoolean('isRunningFinishOrder'):
                self._SetOrderCycleState(PLCOrderCycleState.Finishing, order)

        if self._IsOrderCycleState(PLCOrderCycleState.Finishing):
            controller.Set('startFinishOrder', False)

            if not controller.GetBoolean('isRunningFinishOrder'):
                order = self._GetOrderCycleStateOrder()
                order.finishOrderFinishCode = PLCFinishOrderFinishCode(controller.GetInteger('finishOrderFinishCode'))
                # TODO: check finishCode and stop the whole production cycle?

                # remove order from queue
                self._ordersQueue.remove(order)
                if order.pickContainer:
                    order.pickContainer.orders.remove(order)
                if order.placeContainer:
                    order.placeContainer.orders.remove(order)

                self._SetOrderCycleState(PLCOrderCycleState.Finished, order)

        if self._IsOrderCycleState(PLCOrderCycleState.Finished):
            if self._IsState(PLCProductionCycleState.Running):
                self._SetOrderCycleState(PLCOrderCycleState.Idle)
            else:
                self._SetOrderCycleState(PLCOrderCycleState.Stopped)

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
        log.info('%s (%r) -> %s (%r), elapsed %.03fs', self._preparationCycleState[0], self._preparationCycleState[2], state, order, timestamp - self._preparationCycleState[1])
        self._preparationCycleState = (state, timestamp, order)

    def _IsPreparationCycleState(self, *states: PLCPreparationCycleState) -> bool:
        return self._preparationCycleState[0] in states

    def _GetPreparationCycleStateOrder(self) -> PLCOrder:
        order = self._preparationCycleState[2]
        assert(order is not None)
        return order

    def _RunPreparationCycleStateMachine(self, controller: plccontroller.PLCController) -> None:
        if self._IsPreparationCycleState(PLCPreparationCycleState.Idle):
            if not self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)
            elif not controller.GetBoolean('isModeAuto') or not controller.GetBoolean('isSystemReady'):
                # need to wait until starting condition is met
                pass
            elif not self._IsOrderCycleState(PLCOrderCycleState.Starting):
                # when the order cycle is nost just starting, we can consider whether to start next preparation

                # see if we have a current running order
                currentOrder = None
                if self._IsOrderCycleState(PLCOrderCycleState.Running, PLCOrderCycleState.Finish, PLCOrderCycleState.Finishing, PLCOrderCycleState.Finished):
                    currentOrder = self._GetOrderCycleStateOrder()

                candidate = self._GetOrderCandidate(currentOrder)
                if candidate and candidate is not self._lastPreparedOrder:
                    # found a new order that we should be preparing for
                    self._lastPreparedOrder = None
                    self._SetPreparationCycleState(PLCPreparationCycleState.Starting, candidate)

        if self._IsPreparationCycleState(PLCPreparationCycleState.Starting):
            order = self._GetPreparationCycleStateOrder()
            controller.SetMultiple({
                'preparationUniqueId': order.uniqueId,

                'preparationPartType': order.partType,
                'preparationPartSizeX': order.partSizeX,
                'preparationPartSizeY': order.partSizeY,
                'preparationPartSizeZ': order.partSizeZ,

                'preparationOrderNumber': order.orderNumber,
                'preparationRobotName': order.robotName,

                'preparationPickLocation': order.pickLocationIndex,
                'preparationPickContainerId': order.pickContainerId,
                'preparationPickContainerType': order.pickContainerType,

                'preparationPlaceLocation': order.placeLocationIndex,
                'preparationPlaceContainerId': order.placeContainerId,
                'preparationPlaceContainerType': order.placeContainerType,

                'preparationPackInputPartIndex': order.packInputPartIndex,
                'preparationPackFormationComputationName': order.packFormationComputationName,
                'preparationIgnoreFinishPosition': order.ignoreFinishPosition,

                'startPreparation': True,
                'stopPreparation': False,
            })

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)
            elif controller.GetBoolean('isRunningPreparation'):
                self._SetPreparationCycleState(PLCPreparationCycleState.Running, order)

        if self._IsPreparationCycleState(PLCPreparationCycleState.Running):
            controller.Set('startPreparation', False)

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)
            elif not controller.GetBoolean('isRunningPreparation'):
                # TODO: handle isError and orderCycleFinishCode here
                order = self._GetPreparationCycleStateOrder()
                order.preparationFinishCode = PLCPreparationFinishCode(controller.GetInteger('preparationFinishCode'))
                self._lastPreparedOrder = order
                self._SetPreparationCycleState(PLCPreparationCycleState.Stopping)

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

    def _SetLocationState(self, locationIndex: int, state: PLCLocationState, request: typing.Optional[PLCLocationRequest] = None) -> None:
        if self._IsLocationState(locationIndex, state):
            return
        timestamp = time.monotonic()
        log.info('location%d, %s (%r) -> %s (%r), elapsed %.03fs', locationIndex, self._locationStates[locationIndex][0], self._locationStates[locationIndex][2], state, request, timestamp - self._locationStates[locationIndex][1])
        self._locationStates[locationIndex] = (state, timestamp, request)

    def _IsLocationState(self, locationIndex: int, *states: PLCLocationState) -> bool:
        return self._locationStates[locationIndex][0] in states

    def _GetLocationStateRequest(self, locationIndex: int) -> PLCLocationRequest:
        request = self._locationStates[locationIndex][2]
        assert(request is not None)
        return request

    def _RunLocationStateMachine(self, controller: plccontroller.PLCController, locationIndex: int) -> None:
        if self._IsLocationState(locationIndex, PLCLocationState.Idle):
            controller.Set('startMoveLocation%d' % locationIndex, False)

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetLocationState(locationIndex, PLCLocationState.Stopped)
            else:
                queue = self._locationsQueue[locationIndex]
                while queue:
                    if queue[0].orders:
                        break
                    # container has finished its usage, okay to move away
                    log.info('popping no longer used container: %r', queue[0])
                    queue.pop(0)

                request = PLCLocationRequest(
                    expectedContainerId = '*',
                    expectedContainerType = '*',
                )
                if queue:
                    request = PLCLocationRequest(
                        expectedContainerId = queue[0].containerId,
                        expectedContainerType = queue[0].containerType,
                        orderUniqueId = queue[0].orders[0].uniqueId
                    )

                if request.expectedContainerId != controller.GetString('location%dContainerId' % locationIndex) or \
                   request.expectedContainerType != controller.GetString('location%dContainerType' % locationIndex):
                    self._SetLocationState(locationIndex, PLCLocationState.Move, request)

        if self._IsLocationState(locationIndex, PLCLocationState.Move):
            request = self._GetLocationStateRequest(locationIndex)
            controller.SetMultiple({
                'moveLocation%dExpectedContainerId' % locationIndex: request.expectedContainerId,
                'moveLocation%dExpectedContainerType' % locationIndex: request.expectedContainerType,
                'moveLocation%dOrderUniqueId' % locationIndex: request.orderUniqueId,
                'startMoveLocation%d' % locationIndex: True,
            })

            if controller.GetBoolean('isRunningMoveLocation%d' % locationIndex):
                self._SetLocationState(locationIndex, PLCLocationState.Moving, request)


        if self._IsLocationState(locationIndex, PLCLocationState.Moving):
            controller.Set('startMoveLocation%d' % locationIndex, False)

            if not controller.GetBoolean('isRunningMoveLocation%d' % locationIndex):
                request = self._GetLocationStateRequest(locationIndex)
                request.moveLocaitonFinishCode = PLCMoveLocationFinishCode(controller.GetInteger('moveLocation%dFinishCode' % locationIndex))
                # TODO: check finish code and set next state based on that
                self._SetLocationState(locationIndex, PLCLocationState.Moved, request)

        if self._IsLocationState(locationIndex, PLCLocationState.Moved):
            controller.Set('startMoveLocation%d' % locationIndex, False)

            if self._IsState(PLCProductionCycleState.Running):
                self._SetLocationState(locationIndex, PLCLocationState.Idle)
            else:
                self._SetLocationState(locationIndex, PLCLocationState.Stopped)

        if self._IsLocationState(locationIndex, PLCLocationState.Stopped):
            controller.Set('startMoveLocation%d' % locationIndex, False)

            if self._IsState(PLCProductionCycleState.Running):
                self._SetLocationState(locationIndex, PLCLocationState.Idle)


    #
    # Queue Order State Machine
    #

    def _SetQueueOrderState(self, state: PLCQueueOrderState, order: typing.Optional[PLCOrder] = None) -> None:
        if self._IsQueueOrderState(state):
            return
        timestamp = time.monotonic()
        log.info('%s (%r) -> %s (%r), elapsed %.03fs', self._queueOrderState[0], self._queueOrderState[2], state, order, timestamp - self._queueOrderState[1])
        self._queueOrderState = (state, timestamp, order)

    def _IsQueueOrderState(self, *states: PLCQueueOrderState) -> bool:
        return self._queueOrderState[0] in states

    def _GetQueueOrderStateOrder(self) -> PLCOrder:
        order = self._queueOrderState[2]
        assert(order is not None)
        return order

    def _RunQueueOrderStateMachine(self, controller: plccontroller.PLCController) -> None:
        # in idle state, we wait for startQueueOrder trigger
        if self._IsQueueOrderState(PLCQueueOrderState.Idle):
            controller.Set('isRunningQueueOrder', False)

            if not self._IsState(PLCProductionCycleState.Running):
                self._SetQueueOrderState(PLCQueueOrderState.Disabled)
            elif controller.GetBoolean('startQueueOrder'):
                order = PLCOrder(
                    uniqueId = controller.GetString('queueOrderUniqueId'),

                    partType = controller.GetString('queueOrderPartType'),
                    partSizeX = controller.GetInteger('queueOrderPartSizeX'),
                    partSizeY = controller.GetInteger('queueOrderPartSizeY'),
                    partSizeZ = controller.GetInteger('queueOrderPartSizeZ'),

                    orderNumber = controller.GetInteger('queueOrderNumber'),

                    robotName = controller.GetString('queueOrderRobotName'),

                    pickLocationIndex = controller.GetInteger('queueOrderPickLocationIndex'),
                    pickContainerId = controller.GetString('queueOrderPickContainerId'),
                    pickContainerType = controller.GetString('queueOrderPickContainerType'),

                    placeLocationIndex = controller.GetInteger('queueOrderPlaceLocationIndex'),
                    placeContainerId = controller.GetString('queueOrderPlaceContainerId'),
                    placeContainerType = controller.GetString('queueOrderPlaceContainerIndex'),

                    packInputPartIndex = controller.GetInteger('queueOrderPackInputPartIndex'),
                    packFormationComputationName = controller.GetString('queueOrderPackFormationComputationName'),

                    ignoreFinishPosition = controller.GetBoolean('queueOrderIgnoreFinishPosition'),
                )
                self._SetQueueOrderState(PLCQueueOrderState.Running, order)

        # in running state, we queue the order and transition to success
        if self._IsQueueOrderState(PLCQueueOrderState.Running):
            controller.SetMultiple({
                'isRunningQueueOrder': True,
                'queueOrderFinishCode': int(PLCQueueOrderFinishCode.NotAvailable),
            })

            if not controller.GetBoolean('startQueueOrder'):
                # TODO: check order parameters here
                order = self._GetQueueOrderStateOrder()

                # deal with pick container
                if order.pickLocationIndex in self._locationIndices and order.pickContainerId:
                    pickContainer = None
                    for container in self._locationsQueue[order.pickLocationIndex]:
                        # reuse the previous container if found
                        if (container.containerId, container.containerType) == (order.pickContainerId, order.pickContainerType):
                            pickContainer = container
                            break
                    if not pickContainer:
                        pickContainer = PLCContainer(
                            locationIndex = order.pickLocationIndex,
                            containerId = order.pickContainerId,
                            containerType = order.pickContainerType,
                        )
                        self._locationsQueue[pickContainer.locationIndex].append(pickContainer)
                    pickContainer.orders.append(order)
                    order.pickContainer = pickContainer

                # deal with place container
                if order.placeLocationIndex in self._locationIndices and order.placeContainerId:
                    placeContainer = None
                    for container in self._locationsQueue[order.placeLocationIndex]:
                        # reuse the previous container if found
                        if (container.containerId, container.containerType) == (order.placeContainerId, order.placeContainerType):
                            placeContainer = container
                            break
                    if not placeContainer:
                        placeContainer = PLCContainer(
                            locationIndex = order.placeLocationIndex,
                            containerId = order.placeContainerId,
                            containerType = order.placeContainerType,
                        )
                        self._locationsQueue[placeContainer.locationIndex].append(placeContainer)
                    placeContainer.orders.append(order)
                    order.placeContainer = placeContainer

                # add the order to queue
                self._ordersQueue.append(order)
                self._SetQueueOrderState(PLCQueueOrderState.Succeeded)
                log.warn('order queued on production cycle: %r', order)

        # succeeded queuing, need to set finish code
        if self._IsQueueOrderState(PLCQueueOrderState.Succeeded):
            controller.SetMultiple({
                'isRunningQueueOrder': False,
                'queueOrderFinishCode': int(PLCQueueOrderFinishCode.Success),
            })
            if not self._IsState(PLCProductionCycleState.Running):
                self._SetQueueOrderState(PLCQueueOrderState.Disabled)
            else:
                self._SetQueueOrderState(PLCQueueOrderState.Idle)

        # functionality disabled because of main cycle state
        if self._IsQueueOrderState(PLCQueueOrderState.Disabled):
            controller.Set('isRunningQueueOrder', False)

            if self._IsState(PLCProductionCycleState.Running):
                self._SetQueueOrderState(PLCQueueOrderState.Idle)

    #
    # Utilities.
    #

    def _GetOrderCandidate(self, currentOrder: typing.Optional[PLCOrder] = None) -> typing.Optional[PLCOrder]:
        """
        Get the next order to prepare or execute.

        :return: None if there isn't any order suitable
        """
        candidates = self._ListOrderCandidates(currentOrder)
        if candidates:
            return candidates[0]
        return None

    def _ListOrderCandidates(self, currentOrder: typing.Optional[PLCOrder] = None) -> typing.List[PLCOrder]:
        """
        Get a list of candidate orders

        :return: a list of candidates ranking from high priority to low priority.
        """

        # first thing is to figure out what orders will be possible next
        # this means the order must have its pick and place container at the top of the queue after the current order finishes
        # we cannot consider an order that is blocked until some other order finishes
        # unless it is blocked by the current order, which is okay

        candidates = []
        for order in self._ordersQueue:
            if order is currentOrder:
                continue

            # need to make sure that the container is going to be next on the locations
            nextContainerAtPickLocation = None
            queue = self._locationsQueue[order.pickLocationIndex]
            if queue:
                nextContainerAtPickLocation = queue[0]
                if nextContainerAtPickLocation.orders == [currentOrder]:
                    nextContainerAtPickLocation = queue[1] if len(queue) > 1 else None
            if nextContainerAtPickLocation is not order.pickContainer:
                continue

            # need to make sure that the container is going to be next on the locations
            nextContainerAtPlaceLocation = None
            queue = self._locationsQueue[order.placeLocationIndex]
            if queue:
                nextContainerAtPlaceLocation = queue[0]
                if nextContainerAtPlaceLocation.orders == [currentOrder]:
                    nextContainerAtPlaceLocation = queue[1] if len(queue) > 1 else None
            if nextContainerAtPlaceLocation is not order.placeContainer:
                continue

            candidates.append(order)

        if not currentOrder:
            return candidates

        # if we have current running order, then we need to consider the priority in case of multiple possible orders
        # some orders are immediately executable while others needs the locations used by current order

        availableCandidates = [] # type: typing.List[PLCOrder]
        pickableCandidates = [] # type: typing.List[PLCOrder]
        placeableCandidates = [] # type: typing.List[PLCOrder]
        unavailableCandidates = [] # type: typing.List[PLCOrder]

        for order in candidates:
            if order.pickLocationIndex != currentOrder.pickLocationIndex and order.placeLocationIndex != currentOrder.placeLocationIndex:
                availableCandidates.append(order)
            elif order.pickLocationIndex != currentOrder.pickLocationIndex:
                pickableCandidates.append(order)
            elif order.placeLocationIndex != currentOrder.placeLocationIndex:
                placeableCandidates.append(order)
            else:
                unavailableCandidates.append(order)

        return availableCandidates + pickableCandidates + placeableCandidates + unavailableCandidates
