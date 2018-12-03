# -*- coding: utf-8 -*-

import threading
import weakref

import logging
log = logging.getLogger(__name__)

class PLCMemory:

    _lock = None
    _entries = None
    _observers = None

    def __init__(self):
        self._lock = threading.Lock()
        self._entries = {}
        self._observers = weakref.WeakSet()

    def __del__(self):
        self.Destroy()

    def SetDestroy(self):
        pass

    def Destroy(self):
        self.SetDestroy()

    def Read(self, keys):
        keyvalues = {}
        with self._lock:
            for key in keys:
                if key in self._entries:
                    keyvalues[key] = self._entries[key]
        return keyvalues

    def Write(self, keyvalues):
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

        if observers:
            for observer in observers:
                observer.MemoryModified(modifications)

    def AddObserver(self, observer):
        modifications = None
        with self._lock:
            self._observers.add(observer)
            modifications = dict(self._entries)
        observer.MemoryModified(modifications)
