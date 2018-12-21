# -*- coding: utf-8 -*-

import threading
import weakref
import typing

import logging
log = logging.getLogger(__name__)

class PLCMemory:
    """
    PLCMemory is a key-value store that supports locked PLC memory read write operations.
    """

    ValueType = typing.Optional[typing.Union[str, int, bool]]

    _lock = None # type: threading.Lock
    _entries = None # type: typing.Dict
    _observers = None # type: typing.Set[typing.Any]

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = {}
        self._observers = weakref.WeakSet()

    def Read(self, keys: typing.Iterable[str]) -> typing.Mapping[str, ValueType]:
        """
        Atomically read PLC memory.

        :param keys: An array of strings representing the named memory addresses.\
        :return: A dictionary containing the mapping between requested memory addresses and their stored values. If a requested address does not exist in the memory, it will be omitted here.
        """
        keyvalues = {}
        with self._lock:
            for key in keys:
                if key in self._entries:
                    keyvalues[key] = self._entries[key]
        return keyvalues

    def Write(self, keyvalues: typing.Mapping[str, ValueType]) -> None:
        """
        Atomically write PLC memory.

        :param keyvalues: A dictionary containing the mapping between named memory addresses and their desired values.
        """
        with self._lock:
            modifications = {}
            for key, value in keyvalues.items():
                if key in self._entries and value == self._entries[key]:
                    continue
                modifications[key] = value
            self._entries.update(modifications)

            # notify observers of the modifications
            # have to do it under lock to guarantee ordering
            if modifications:
                for observer in self._observers:
                    observer.MemoryModified(modifications)

    def AddObserver(self, observer: typing.Any) -> None:
        with self._lock:
            self._observers.add(observer)

            # notify observer of the current state
            observer.MemoryModified(dict(self._entries))

class PLCMemoryLogger:

    _ignoredKeys = None # type: typing.Iterable[str]

    def __init__(self, memory: PLCMemory, ignoredKeys: typing.Optional[typing.Iterable[str]] = None):
        self._ignoredKeys = ignoredKeys or []
        memory.AddObserver(self)

    def MemoryModified(self, modifications: typing.Mapping[str, PLCMemory.ValueType]) -> None:
        modificationsCopy = dict(modifications)
        for key in self._ignoredKeys:
            modificationsCopy.pop(key, None)
        if modificationsCopy:
            log.debug('%r', modificationsCopy)
