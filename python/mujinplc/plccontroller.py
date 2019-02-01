# -*- coding: utf-8 -*-

import threading
import time
import typing # noqa: F401 # used in type check

from . import plcmemory

import logging
log = logging.getLogger(__name__)

class PLCController:

    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _state = None # type: typing.Dict[str, plcmemory.PLCMemory.ValueType] # current state which is a snapshot of the PLCMemory in time, _state is intentionally not protected by lock

    _queue = None # type: typing.List[typing.Mapping[str, plcmemory.PLCMemory.ValueType]] # incoming modifications queue
    _lock = None # type: threading.Lock # protects _queue
    _condition = None # type: threading.Condition # condition variable for _queue

    _maxHeartbeatInterval = None # type: typing.Optional[float] # if heartbeat has not been received in this interval, connection is considered to be lost
    _heartbeatSignal = None # type typing.Optional[str] # name of the heartbeat signal that is changed contantly
    _lastHeartbeat = None # type typing.Optional[int] # timestamp of the last heartbeat

    def __init__(self, memory: plcmemory.PLCMemory, maxHeartbeatInterval: typing.Optional[float] = None, heartbeatSignal: typing.Optional[str] = None):
        self._memory = memory
        self._state = {}

        self._queue = []
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

        self._maxHeartbeatInterval = maxHeartbeatInterval
        self._heartbeatSignal = heartbeatSignal

        self._memory.AddObserver(self)

    def MemoryModified(self, modifications: typing.Mapping[str, plcmemory.PLCMemory.ValueType]) -> None:
        self._Enqueue(modifications)

    def _Enqueue(self, modifications: typing.Mapping[str, plcmemory.PLCMemory.ValueType]) -> None:
        if not modifications:
            return
        if not self._heartbeatSignal or self._heartbeatSignal in modifications:
            self._lastHeartbeat = time.monotonic()
        with self._lock:
            self._queue.append(modifications)
            self._condition.notify()

    def _Dequeue(self, timeout: typing.Optional[float] = None, timeoutOnDisconnect: bool = True) -> typing.Optional[typing.Mapping[str, plcmemory.PLCMemory.ValueType]]:
        start = time.monotonic()
        modifications = None

        while True:
            if timeout is not None and timeout < 0:
                # timed out
                return None

            with self._lock:
                if self._queue:
                    modifications = self._queue.pop(0)
                    break
                if self._condition.wait(0.05):
                    modifications = self._queue.pop(0)
                    break

            if timeout is not None and time.monotonic() - start > timeout:
                # timed out
                return None

            if timeoutOnDisconnect and not self.IsConnected():
                # timed out because of disconnection
                return None

        self._state.update(modifications)
        return modifications

    def _DequeueAll(self) -> None:
        modifications = {} # type: typing.Dict[str, plcmemory.PLCMemory.ValueType]
        with self._lock:
            for keyvalues in self._queue:
                modifications.update(keyvalues)
            self._queue = []
        self._state.update(modifications)

    def Sync(self) -> None:
        """
        Synchronize the local memory snapshot with what has happened already.
        """
        self._DequeueAll()

    def IsConnected(self) -> bool:
        """
        Whether time since last heartbeat is within expectation indicating an active connection.
        """
        if self._maxHeartbeatInterval:
            return self._lastHeartbeat is not None and time.monotonic() - self._lastHeartbeat < self._maxHeartbeatInterval
        return True

    def Wait(self, timeout: typing.Optional[float] = None) -> bool:
        """
        Wait until anything changes.

        :return: True if successfully waited, False if timed out.
        """
        if self._Dequeue(timeout=timeout):
            return True
        return False

    def WaitUntilConnected(self, timeout: typing.Optional[float] = None) -> bool:
        """
        Wait until IsConnected becomes true.

        :return: True if successfully waited, False if timed out.
        """
        while not self.IsConnected():
            start = time.monotonic()
            if not self._Dequeue(timeout=timeout, timeoutOnDisconnect=False):
                return False
            if timeout is not None:
                timeout -= time.monotonic() - start
        return True

    def WaitFor(self, key: str, value: plcmemory.PLCMemory.ValueType, timeout: typing.Optional[float] = None) -> bool:
        """
        Wait for a key to change to a particular value.

        Specifically, if the key is already at such value, wait until it changes to something else and then changes back. If value is None, then wait for any change to the key.

        :return: True if successfully waited, False if timed out.
        """
        return self.WaitForAny({key: value}, timeout=timeout)

    def WaitForAny(self, keyvalues: typing.Mapping[str, plcmemory.PLCMemory.ValueType], timeout: typing.Optional[float] = None) -> bool:
        """
        Wait for multiple keys, return as soon as any one key has the expected value.

        If the passed in expected value of a key is None, then wait for any change to that key.

        :return: True if successfully waited, False if timed out.
        """
        while True:
            start = time.monotonic()

            modifications = self._Dequeue(timeout=timeout)
            if not modifications:
                return False

            for key, value in modifications.items():
                if key in keyvalues:
                    if keyvalues[key] is None or keyvalues[key] == value:
                        return True

            if timeout is not None:
                timeout -= time.monotonic() - start

    def WaitUntil(self, key: str, value: plcmemory.PLCMemory.ValueType, timeout: typing.Optional[float] = None) -> bool:
        """
        Wait until a key is at the expected value.

        If the key is already at such value, return immediately.

        :return: True if successfully waited, False if timed out.
        """
        return self.WaitUntilAllOrAny(expectations={key: value}, timeout=timeout)

    def WaitUntilAny(self, exceptions: typing.Optional[typing.Mapping[str, plcmemory.PLCMemory.ValueType]], timeout: typing.Optional[float] = None) -> bool:
        """
        Wait until any of the keys is at the expected value.

        If the key is already at such value, return immediately.

        :return: True if successfully waited, False if timed out.
        """
        return self.WaitUntilAllOrAny(exceptions=exceptions, timeout=timeout)

    def WaitUntilAll(self, expectations: typing.Optional[typing.Mapping[str, plcmemory.PLCMemory.ValueType]], timeout: typing.Optional[float] = None) -> bool:
        """
        Wait until all of the keys is at the expected value.

        If the key is already at such value, return immediately.

        :return: True if successfully waited, False if timed out.
        """
        return self.WaitUntilAllOrAny(expectations=expectations, timeout=timeout)


    def WaitUntilAllOrAny(self, expectations: typing.Optional[typing.Mapping[str, plcmemory.PLCMemory.ValueType]] = None, exceptions: typing.Optional[typing.Mapping[str, plcmemory.PLCMemory.ValueType]] = None, timeout: typing.Optional[float] = None) -> bool:
        """
        Wait until multiple keys are ALL at their expected value, OR ANY one key is at its exceptional value.

        If all the keys are already satisfying the expectations, then return immediately.
        If any of the exceptional conditions is met, then return immediately.

        :return: True if successfully waited, False if timed out.
        """
        expectations = expectations or {}
        exceptions = exceptions or {}

        # combine dictionaries
        keyvalues = {} # type: typing.Dict[str, plcmemory.PLCMemory.ValueType]
        keyvalues.update(expectations)
        keyvalues.update(exceptions)
        if not keyvalues:
            return True

        # always clear the queue first
        self._DequeueAll()

        while True:
            start = time.monotonic()

            # check if any exceptions is already met
            for key, value in exceptions.items():
                if key in self._state and self._state[key] == value:
                    return True

            # check if all expectations are already met
            met = True
            for key, value in expectations.items():
                if key not in self._state or self._state[key] != value:
                    met = False
                    break
            if met:
                return True

            # wait for it to change
            if not self.WaitForAny(keyvalues, timeout=timeout):
                return False

            if timeout is not None:
                timeout -= time.monotonic() - start

    def Set(self, key: str, value: plcmemory.PLCMemory.ValueType) -> None:
        """
        Set key in PLC memory.
        """
        self._memory.Write({key: value})

    def SetMultiple(self, keyvalues: typing.Mapping[str, plcmemory.PLCMemory.ValueType]) -> None:
        """
        Set multiple keys in PLC memory.
        """
        self._memory.Write(keyvalues)

    def Get(self, key: str, defaultValue: plcmemory.PLCMemory.ValueType = None) -> plcmemory.PLCMemory.ValueType:
        """
        Get value of a key in the current state snapshot of the PLC memory.
        """
        return self._state.get(key, defaultValue)

    def SyncAndGet(self, key: str, defaultValue: plcmemory.PLCMemory.ValueType = None) -> plcmemory.PLCMemory.ValueType:
        """
        Synchronize the local memory snapshot with what has happened already, then get value of a key in the current state snapshot of the PLC memory.
        """
        self.Sync()
        return self.Get(key, defaultValue=defaultValue)

    def GetMultiple(self, keys: typing.Iterator[str]) -> typing.Mapping[str, plcmemory.PLCMemory.ValueType]:
        """
        Get values of multiple keys in the current state snapshot of the PLC memory.
        """
        keyvalues = {}
        for key in keys:
            if key in self._state:
                keyvalues[key] = self._state[key]
        return keyvalues

    def SyncAndGetMultiple(self, keys: typing.Iterator[str]) -> typing.Mapping[str, plcmemory.PLCMemory.ValueType]:
        """
        Synchronize the local memory snapshot with what has happened already, then get values of multiple keys in the current state snapshot of the PLC memory.
        """
        self.Sync()
        return self.GetMultiple(keys)

    def GetString(self, key: str, defaultValue: str = '') -> str:
        value = self.Get(key, defaultValue=defaultValue)
        if not isinstance(value, str):
            return defaultValue
        return value

    def SyncAndGetString(self, key: str, defaultValue: str = '') -> str:
        self.Sync()
        return self.GetString(key, defaultValue=defaultValue)

    def GetBoolean(self, key: str, defaultValue: bool = False) -> bool:
        value = self.Get(key, defaultValue=defaultValue)
        if not isinstance(value, bool):
            return defaultValue
        return value

    def SyncAndGetBoolean(self, key: str, defaultValue: bool = False) -> bool:
        self.Sync()
        return self.GetBoolean(key, defaultValue=defaultValue)

    def GetInteger(self, key: str, defaultValue: int = 0) -> int:
        value = self.Get(key, defaultValue=defaultValue)
        if not isinstance(value, int):
            return defaultValue
        return value

    def SyncAndGetInteger(self, key: str, defaultValue: int = 0) -> int:
        self.Sync()
        return self.GetInteger(key, defaultValue=defaultValue)
