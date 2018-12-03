# -*- coding: utf-8 -*-

import time
import threading
import typing
import zmq

from . import plcmemory

import logging
log = logging.getLogger(__name__)

class PLCServerSocket:
    """
    A ZMQ server socket implementation internally used by PLCServer.
    """

    _ctx = None # allocated zmq context, need to free
    _socket = None # allocated zmq socket, need to close

    def __init__(self, endpoint, ctx=None):
        if ctx is None:
            self._ctx = zmq.Context()
            ctx = self._ctx

        self._socket = ctx.socket(zmq.REP)
        self._socket.setsockopt(zmq.LINGER, 100) # discard pending messages after 100ms when closing
        self._socket.setsockopt(zmq.SNDHWM, 2) # queue at most two messages per client
        self._socket.bind(endpoint)

    def __del__(self):
        self.Destroy()

    def Destroy(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except:
                log.exception('caught exception when closing socket')
            self._socket = None

        if self._ctx is not None:
            try:
                self._ctx.destroy()
            except:
                log.exception('caught exception when destroying context')
            self._ctx = None

    def Poll(self, timeout=50):
        return self._socket.poll(timeout, zmq.POLLIN) == zmq.POLLIN

    def Receive(self):
        return self._socket.recv_json(zmq.NOBLOCK)

    def Send(self, data):
        self._socket.send_json(data, zmq.NOBLOCK)

class PLCServer:
    """
    A ZMQ server that hosts the PLC controller.
    """

    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _endpoint = None # type: str # listening endpoint to bind to
    _ctx = None # type: typing.Any # zmq context
    _thread = None # type: typing.Optional[threading.Thread] # server thread
    _isok = False # type: bool # signal that the server thread should continue to run

    def __init__(self, memory: plcmemory.PLCMemory, endpoint: str, ctx: typing.Any = None):
        self._memory = memory
        self._endpoint = endpoint
        self._ctx = ctx
        self._isok = False

    def __del__(self):
        self.Stop()

    def Start(self) -> None:
        """
        Start the PLC server on a background thread.
        """
        self.Stop()

        self._isok = True
        self._thread = threading.Thread(target=self._RunThread, name='plcserver')
        self._thread.start()

    def IsRunning(self) -> bool:
        """
        Whether ZMQ server is currently running.
        """
        return self._isok

    def SetStop(self) -> None:
        self._isok = False

    def Stop(self) -> None:
        """
        Stop the PLC server. Will block until the background thread teminates.
        """
        self.SetStop()
        if self._thread is not None:
            self._thread.join()
            self._thread = None

    def _RunThread(self) -> None:
        socket = None # zmq socket for use in this thread

        while self._isok:
            try:
                if socket is None:
                    socket = PLCServerSocket(self._endpoint, ctx=self._ctx)

                if not socket.Poll(timeout=50):
                    continue

                response = {}
                request = socket.Receive()

                try:
                    if request['command'] == 'read':
                        response['keyvalues'] = self._memory.Read(request['keys'])
                    elif request['command'] == 'write':
                        self._memory.Write(request['keyvalues'])
                except:
                    log.exception('failed to handle request: %r', request)

                socket.Send(response)

            except:
                log.exception('caught exception in server thread, resetting socket')
                if socket is not None:
                    socket.Destroy()
                    socket = None

                # sleep a little bit when exception happens
                time.sleep(200)

        if socket is not None:
            socket.Destroy()
            socket = None
