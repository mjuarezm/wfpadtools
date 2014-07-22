"""
The test_server module implements a transport placed in between the
transport client and transport server that dumps the state and messages
received into a temporal file in order to be processed by the test module.
"""
import obfsproxy.common.log as logging
import obfsproxy.transports.wfpadtools.util as ut
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.dummy import DummyTransport

import pickle
from time import time
from os.path import join

log = logging.get_obfslogger()


class TestTransport(DummyTransport):
    _history = []
    _currentStartTime = 0

    def __init__(self):
        log.debug("Creating new instance of test server..")
        self._tempDir = const.TEST_SERVER_DIR
        ut.createdir(self._tempDir)
        super(TestTransport, self).__init__()

    def getIat(self):
        """Return inter-arrival time."""
        return time() - self._currentStartTime

    def tempDump(self):
        """Dump downstream history to a temp file."""
        file_tranport = join(self._tempDir, str(id(self)))
        with open(file_tranport, "w") as f:
            pickle.dump(self._history[1:], f)

    def receivedDownstream(self, data):
        """Got data from the client; save iat and length into history."""
        log.debug("Test server: downstream")
        rcvDownData = data.read()
        iat = self.getIat() if self._history else 0
        self._history.append((len(rcvDownData), iat))
        self._currentStartTime = time()
        self.tempDump()
        self.circuit.upstream.write(rcvDownData)

    def receivedUpstream(self, data):
        log.debug("Test server: upstream")
        super(TestTransport, self).receivedUpstream(data)


class TestClient(TestTransport):
    pass


class TestServer(TestTransport):
    pass
