"""
The test_server module implements a transport placed in between the
transport client and transport server that dumps the state and messages
received into a temporal file in order to be processed by the test module.
"""
from obfsproxy.transports.dummy import DummyTransport
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util as ut

import pickle
from time import time
from os.path import join


class TestTransport(DummyTransport):
    _history = []
    _circuitAlive = False

    def __init__(self):
        self._tempDir = const.TEST_SERVER_DIR
        ut.createdir(self._tempDir)
        self._circuitAlive = True
        super(TestTransport, self).__init__()

    def getIat(self):
        """Return inter-arrival time."""
        return time() - self._startPeriod

    def tempDump(self):
        """Dump downstream history to a temp file."""
        file_tranport = join(self._tempDir, str(id(self)))
        with open(file_tranport, "w") as f:
            pickle.dump(self._history, f)

    def receivedDownstream(self, data):
        """Got data from the client; save iat and length into history."""
        rcvDownData = data.read()
        iat = self.getIat() if self._history else 0
        self._history.append((len(rcvDownData), iat))
        self.circuit.downstream.write(rcvDownData)

    def circuitDestroyed(self, reason, side):
        """Dump history to file if circuit is alive."""
        if self._circuitAlive:
            self.tempDump()
            self._circuitAlive = False
        super(TestTransport, self).circuitDestroyed(reason, side)


class TestServer(TestTransport):
    pass
