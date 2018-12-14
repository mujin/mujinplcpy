# -*- coding: utf-8 -*-

import pytest

from mujinplc import plcmemory

def test_BasicMemoryOperations():
    memory = plcmemory.PLCMemory()
    assert memory.Read(['testSignal']) == {}
    memory.Write({'testSignal': True})
    assert memory.Read(['testSignal']) == {'testSignal': True}

@pytest.mark.parametrize('keyvalues', [
    {'special': None},
    {'booleanSignal': True},
    {'booleanSignal': False},
    {'stringSignal': ''},
    {'stringSignal': 'string'},
    {'integerSignal': 0},
    {'integerSignal': 1},
    {'integerSignal': 2},
    {'integerSignal': -1},
    {'integerSignal': 10000},
])
def test_MemoryValueTypes(keyvalues):
    memory = plcmemory.PLCMemory()
    memory.Write(keyvalues)
    assert memory.Read(keyvalues.keys()) == keyvalues
