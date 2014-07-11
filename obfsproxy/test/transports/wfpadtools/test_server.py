"""
The test_server module implements a transport placed in between the
transport client and transport server that dumps the state and messages
received into a temporal file in order to be processed by the test module.
"""
from obfsproxy.transports.dummy import DummyServer
from obfsproxy.transports.wfpadtools.const import TEST_SERVER_DIR

import pickle
from time import time
from os.path import join


class TestServer(DummyServer):
    _history = []

    def __init__(self):
        self._circuitAlive = True
        super(TestServer, self).__init__()

    def getIat(self):
        """Return inter-arrival time."""
        return time() - self._startPeriod

    def temporal_dump(self):
        """Dump downstream history to a temp file."""
        file_tranport = join(TEST_SERVER_DIR, str(id(self)))
        with open(file_tranport, "w") as f:
            pickle.dump(self._history, f)

    def receivedDownstream(self, data):
        """Got data from the client; save iat and length to history."""
        rcvDownData = data.read()
        lenRcvDownData = len(rcvDownData)
        if self.__history:
            iat = self.getIat(lenRcvDownData)
            self._history.append((lenRcvDownData, iat))
        else:
            self._history.append((len(rcvDownData), 0))
        self.circuit.downstream.write(rcvDownData)

    def circuitDestroyed(self, reason, side):
        """Dump history to file if circuit is alive."""
        if self._circuitAlive:
            self.temporal_dump()
            self._circuitAlive = False
        super(TestServer, self).circuitDestroyed(reason, side)
