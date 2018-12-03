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
        modifications = {}
        observers = None
        with self._lock:
            for key, value in keyvalues.items():
                if key in self._entries and value == self._entries[key]:
                    continue
                self._entries[key] = value
                modifications[key] = value

            if modifications:
                observers = list(self._observers)

        # notify observers of the modifications
        if observers:
            for observer in observers:
                observer.MemoryModified(modifications)

    def AddObserver(self, observer: typing.Any) -> None:
        modifications = None
        with self._lock:
            self._observers.add(observer)
            modifications = dict(self._entries)
        observer.MemoryModified(modifications)
