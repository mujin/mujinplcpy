# -*- coding: utf-8 -*-

import threading
import time

import logging
log = logging.getLogger(__name__)

class PLCController:

    _memory = None # an instance of PLCMemory
    _state = None # current state which is a snapshot of the PLCMemory in time
    _queue = None # incoming modifications queue
    _lock = None # protects _queue
    _condition = None # condition variable for _queue

    _maxHeartbeatInterval = None
    _heartbeatSignal = None
    _lastHeartbeat = None

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
        log.debug('memory modified: %r', modifications)
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
        self._DequeueAll()

    def IsConnected(self):
        if self._maxHeartbeatInterval:
            return time.monotonic() - self._lastHeartbeat < self._maxHeartbeatInterval
        return True

    def WaitUntilConnected(self, timeout=None):
        while not self.IsConnected():
            start = time.monotonic()
            if not self._Dequeue(timeout=timeout):
                return False
            if timeout is not None:
                timeout -= time.monotonic() - start
        return True

    def WaitFor(self, key, value, timeout=None):
        return self.WaitForAny({key: value}, timeout=timeout)

    def WaitForAny(self, keyvalues, timeout=None):
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
        return self.WaitUntilAll({key: value}, timeout=timeout)

    def WaitUntilAll(self, expectations, exceptions=None, timeout=None):
        exceptions = exceptions or {}

        # combine dictionaries
        keyvalues = dict(expectations.items() + exceptions.items())

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
        self._memory.Write({key: value})

    def SetMultiple(self, keyvalues):
        self._memory.Write(keyvalues)

    def Get(self, key, defaultValue=None):
        return self._state.get(key, defaultValue)

    def SyncAndGet(self, key, defaultValue=None):
        self.Sync()
        return self.Get(key, defaultValue=defaultValue)

    def GetMultiple(self, keys):
        keyvalues = {}
        for key in keys:
            if key in self._state:
                keyvalues[key] = self._state[key]
        return keyvalues

    def SyncAndGetMultiple(self, keys):
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
