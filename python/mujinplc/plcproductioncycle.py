# -*- coding: utf-8 -*-

import threading
import time
import typing
from enum import Enum
from collections import deque
from . import plcmemory, plccontroller, plclogic

import logging
log = logging.getLogger(__name__)

class Order:
    """
    Struct describing order data. This Order class is  used internally
    """
    orderPartType = ""
    orderPartSizeX = 0
    orderPartSizeY = 0
    orderPartSizeZ = 0
    orderNumber = 0
    orderRobotId = 0
    orderUniqueId = ""

    orderPickLocation = 0
    orderPickContainerId = ""
    orderPickContainerType = ""
    orderPlaceLocation = 0
    orderPlaceLocation = ""
    orderPlaceContainerType = ""

class State(Enum):
    Stop = 1 # production cycle stopped. Waiting for startProductionCycle to be true.
    Idle = 2 # Production Cycle is started.  Queue is empty. System is in Idle
    Start = 3 # Queue has order, start to deal with new order.
    Running = 4 # Order from start state meet the condition , start to run order
    Finish = 5 # Order Finished. Publish orderFinishCode to high level system and wait for return to continue.

class PLCProductionCycle:
    
    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _locationIndices = None # type: typing.List[int]
    _locationsQueue = {} # type: typing.Dict[int, deque]
    _locationsQueueLock = {} # type: typing.Dict[int, threading.Lock]
    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]



    def __init__(self, memory: plcmemory.PLCMemory, maxLocationIndex: int = 4):
        self._memory = memory
        self._locationIndices = list(range(1, maxLocationIndex + 1))
        for location in self._locationIndices:
            self._locationsQueue[location] = deque()
            self._locationsQueueLock[location] = threading.Lock()

    def _DequeueOrder(self, locationIndex: int) -> None:
        """ Deqeue first order from locationIndex queue
        """
        with self._locationsQueueLock[locationIndex]:
            try:
                self._locationsQueue[locationIndex].popleft()
            except IndexError as e:
                log.error("dequeue order from location %s  error %s"%(locationIndex, e))

    def _RunQueueOrderThread(self):
        log.debug("QueueOrderThread started\n")
        controller = plccontroller.PLCController(self._memory)
        controller.Set("isQueueOrderRunning", False)
        queueOrderfinishCode = 0
        while self._isok:
            log.debug("QueueOrderThread is waiting for startQueueOrder")
            controller.WaitUntil("startQueueOrder", True)
            log.error("Receive startQueueOrder = True \n")
            controller.Set("isQueueOrderRunning", True)
            orderParams = controller.GetMultiple([
                'queueOrderPartType',
                'queueOrderNumber',
                'queueOrderRobotId',
                'queueOrderPickLocationIndex',
                'queueOrderPickContainerId',
                'queueOrderPickContainerType',
                'queueOrderPlaceLocationIndex',
                'queueOrderPlaceContainerId',
                'queueOrderPlaceContainerType',
                'queueOrderUniqueId',
            ])
            order = Order()
            order.orderUniqueId = orderParams.get("queueOrderUniqueId", "")
            order.orderPartType = orderParams.get('queueOrderPartType', '')
            order.orderNumber = orderParams.get("queueOrderNumber", 0)
            order.orderRobotId = orderParams.get("queueOrderRobotId", 0)
            order.orderPickLocation = orderParams.get("queueOrderPickLocationIndex", 0)
            order.orderPickContainerId = orderParams.get("queueOrderPickContainerId", "")
            order.orderPickContainerType = orderParams.get("queueOrderPickContainerType", "")
            order.orderPlaceLocation = orderParams.get("queueOrderPlaceLocationIndex", 0)
            order.orderPlaceContainerId = orderParams.get("queueOrderPlaceContainerId", "")
            order.orderPlaceContainerType = orderParams.get("queueOrderPlaceContainerType", "")

            try:
                if order.orderPickLocation not in self._locationIndices:
                    raise
                with self._locationsQueueLock[order.orderPickLocation]:
                    self._locationsQueue[order.orderPickLocation].append(order)
                    queueOrderFinishCode = 1
                log.debug("order unique id %s put into location %d queue, queue length = %d\n" % (order.orderUniqueId, order.orderPickLocation, len(self._locationsQueue[order.orderPickLocation])))
            except Exception as e:
                log.error('QueueOrder uniqueId = %s error = %s, %s'%(order.orderUniqueId, e, self._locationsQueue[order.orderPickLocation]))
            finally:
                controller.WaitUntil("startQueueOrder", False)
                controller.SetMultiple({
                    "isQueueOrderRunning": False,
                    "queueOrderFinishCode": queueOrderFinishCode
                })

    def __del__(self):
        self.Stop()

    def Start(self) -> None:
        self.Stop()

        # start the main monitoring thread
        self._isok = True
        self._thread = threading.Thread(target=self._RunThread, name='plcproductioncycle')
        self._thread.start()
        self._queueOrderThread = threading.Thread(target=self._RunQueueOrderThread, name="plcqueueorder")
        self._queueOrderThread.start()

    def Stop(self) -> None:
        self._isok = False
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _RunThread(self) -> None:
        controller = plccontroller.PLCController(self._memory)

        while self._isok:
            time.sleep(0.1)
