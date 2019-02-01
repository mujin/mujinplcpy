# -*- coding: utf-8 -*-

import time
import threading
import typing
import socket
import select
import json

from . import plcmemory

import logging
log = logging.getLogger(__name__)

class PLCUDPServerSocket:
    """
    A UDP server socket implementation internally used by PLCUDPServer.
    """

    _socket = None # allocated udp socket, need to close

    def __init__(self, port):
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.bind(('', port))

    def __del__(self):
        self.Destroy()

    def Destroy(self):
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception as e:
                log.exception('caught exception when closing socket: %s', e)
            self._socket = None

    def Poll(self, timeout=50):
        rlist, _, xlist = select.select([self._socket], [], [self._socket], timeout / 1000.0)
        if self._socket in xlist:
            raise Exception('socket exception detected')
        return self._socket in rlist

    def Receive(self):
        data, address = self._socket.recvfrom(64 * 1024)
        return json.loads(data.decode('utf-8')), address

    def Send(self, data, address):
        self._socket.sendto(json.dumps(data).encode('utf-8'), address)

class PLCUDPServer:
    """
    A UDP server that hosts the PLC controller.
    """

    _memory = None # type: plcmemory.PLCMemory # an instance of PLCMemory
    _port = None # type: int # listening port to bind to
    _thread = None # type: typing.Optional[threading.Thread] # server thread
    _isok = False # type: bool # signal that the server thread should continue to run

    def __init__(self, memory: plcmemory.PLCMemory, port: int):
        self._memory = memory
        self._port = port
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
        Whether the server is currently running.
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
                    socket = PLCUDPServerSocket(self._port)

                if not socket.Poll(timeout=50):
                    continue

                response = {}
                request, address = socket.Receive()

                try:
                    response['seqid'] = request['seqid']
                    response['timestamp'] = int(time.monotonic() * 1e9)
                    if 'writevalues' in request:
                        self._memory.Write(request['writevalues'])
                    if 'read' in request:
                        response['readvalues'] = self._memory.Read(request['read'])
                except Exception as e:
                    log.exception('failed to handle request: %s: %r', e, request)

                socket.Send(response, address)

            except Exception as e:
                log.exception('caught exception in server thread, resetting socket: %s', e)
                if socket is not None:
                    socket.Destroy()
                    socket = None

                # sleep a little bit when exception happens
                time.sleep(0.2)

        if socket is not None:
            socket.Destroy()
            socket = None
