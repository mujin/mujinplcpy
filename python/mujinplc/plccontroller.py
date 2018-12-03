# -*- coding: utf-8 -*-

import threading
import time

import logging
log = logging.getLogger(__name__)

class PLCController:

    _memory = None # an instance of PLCMemory
    _state = None # current state which is a snapshot of the PLCMemory in time, _state is intentionally not protected by lock

    _queue = None # incoming modifications queue
    _lock = None # protects _queue
    _condition = None # condition variable for _queue

    _maxHeartbeatInterval = None # if heartbeat has not been received in this interval, connection is considered to be lost
    _heartbeatSignal = None # name of the heartbeat signal that is changed contantly
    _lastHeartbeat = None # timestamp of the last heartbeat

    def __init__(self, memory, maxHeartbeatInterval=None, heartbeatSignal=None):
        self._memory = memory
        self._state = {}

        self._queue = []
        self._lock = threading.Lock()
        self._condition = threading.Condition(self._lock)

        self._maxHeartbeatInterval = maxHeartbeatInterval
        self._heartbeatSignal = heartbeatSignal

        self._memory.AddObserver(self)

    def MemoryModified(self, modifications):
        self._Enqueue(modifications)

    def _Enqueue(self, modifications):
        # log.debug('memory modified: %r', modifications)
        if not self._heartbeatSignal or self._heartbeatSignal in modifications:
            self._lastHeartbeat = time.monotonic()
        with self._lock:
            self._queue.append(modifications)
            self._condition.notify()

    def _Dequeue(self, timeout=None, timeoutOnDisconnect=True):
        start = time.monotonic()
        modifications = None

        while True:
            if timeout is not None and timeout < 0:
                # timed out
                return None

            with self._lock:
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

    def _DequeueAll(self):
        modifications = {}
        with self._lock:
            for keyvalues in self._queue:
                modifications.update(keyvalues)
            self._queue = []
        self._state.update(modifications)

    def Sync(self):
        """
        Synchronize the local memory snapshot with what has happened already.
        """
        self._DequeueAll()

    def IsConnected(self):
        """
        Whether time since last heartbeat is within expectation indicating an active connection.
        """
        if self._maxHeartbeatInterval:
            return time.monotonic() - self._lastHeartbeat < self._maxHeartbeatInterval
        return True

    def WaitUntilConnected(self, timeout=None):
        """
        Wait until IsConnected becomes true.
        """
        while not self.IsConnected():
            start = time.monotonic()
            if not self._Dequeue(timeout=timeout, timeoutOnDisconnect=False):
                return False
            if timeout is not None:
                timeout -= time.monotonic() - start
        return True

    def WaitFor(self, key, value, timeout=None):
        """
        Wait for a key to change to a particular value.

        Specifically, if the key is already at such value, wait until it changes to something else and then changes back. If value is None, then wait for any change to the key.
        """
        return self.WaitForAny({key: value}, timeout=timeout)

    def WaitForAny(self, keyvalues, timeout=None):
        """
        Wait for multiple keys, return as soon as any one key has the expected value.

        If the passed in expected value of a key is None, then wait for any change to that key.
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

    def WaitUntil(self, key, value, timeout=None):
        """
        Wait until a key is at the expected value.

        If the key is already at such value, return immediately.
        """
        return self.WaitUntilAll({key: value}, timeout=timeout)

    def WaitUntilAll(self, expectations=None, exceptions=None, timeout=None):
        """
        Wait until multiple keys are ALL at their expected value, OR ANY one key is at its exceptional value.

        If all the keys are already satisfying the expectations, then return immediately.
        If any of the exceptional conditions is met, then return immediately.
        """
        expectations = expectations or {}
        exceptions = exceptions or {}

        # combine dictionaries
        keyvalues = {}
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

    def Set(self, key, value):
        """
        Set key in PLC memory.
        """
        self._memory.Write({key: value})

    def SetMultiple(self, keyvalues):
        """
        Set multiple keys in PLC memory.
        """
        self._memory.Write(keyvalues)

    def Get(self, key, defaultValue=None):
        """
        Get value of a key in the current state snapshot of the PLC memory.
        """
        return self._state.get(key, defaultValue)

    def SyncAndGet(self, key, defaultValue=None):
        """
        Synchronize the local memory snapshot with what has happened already, then get value of a key in the current state snapshot of the PLC memory.
        """
        self.Sync()
        return self.Get(key, defaultValue=defaultValue)

    def GetMultiple(self, keys):
        """
        Get values of multiple keys in the current state snapshot of the PLC memory.
        """
        keyvalues = {}
        for key in keys:
            if key in self._state:
                keyvalues[key] = self._state[key]
        return keyvalues

    def SyncAndGetMultiple(self, keys):
        """
        Synchronize the local memory snapshot with what has happened already, then get values of multiple keys in the current state snapshot of the PLC memory.
        """
        self.Sync()
        return self.GetMultiple(keys)

    def GetString(self, key, defaultValue=''):
        value = self.Get(key, defaultValue=defaultValue)
        if not isinstance(value, str):
            return defaultValue
        return value

    def SyncAndGetString(self, key, defaultValue=''):
        self.Sync()
        return self.GetString(key, defaultValue=defaultValue)

    def GetBoolean(self, key, defaultValue=False):
        value = self.Get(key, defaultValue=defaultValue)
        if not isinstance(value, bool):
            return defaultValue
        return value

    def SyncAndGetBoolean(self, key, defaultValue=False):
        self.Sync()
        return self.GetBoolean(key, defaultValue=defaultValue)

    def GetInteger(self, key, defaultValue=0):
        value = self.Get(key, defaultValue=defaultValue)
        if not isinstance(value, int):
            return defaultValue
        return value

    def SyncAndGetInteger(self, key, defaultValue=0):
        self.Sync()
        return self.GetInteger(key, defaultValue=defaultValue)
