# -*- coding: utf-8 -*-

import threading
import time
import typing
from enum import Enum
from . import plcmemory, plccontroller

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

class PLCProductionCycle:
    
    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _locationIndices = None # type: typing.List[int]

    _isok = False # type: bool
    _thread = None # type: typing.Optional[threading.Thread]

    class State(Enum):
        Stop = 1 # production cycle stopped. Waiting for startProductionCycle to be true.
        Idle = 2 # Production Cycle is started.  Queue is empty. System is in Idle
        Start = 3 # Queue has order, start to deal with new order.
        Running = 4 # Order from start state meet the condition , start to run order
        Finish = 5 # Order Finished. Publish orderFinishCode to high level system and wait for return to continue.

    def __init__(self, memory: plcmemory.PLCMemory, maxLocationIndex: int = 4):
        self._memory = memory
        self._locationIndices = list(range(1, maxLocationIndex + 1))

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
            time.sleep(0.1)
