"""
The test_server module implements test transports placed in between the
transport client and transport server that dump the state and messages
received into a temporal file in order to be processed by the test module.
"""
import obfsproxy.common.log as logging
import obfsproxy.transports.wfpadtools.util as ut
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.dummy import DummyTransport
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import pickle
from time import time
from os.path import join

log = logging.get_obfslogger()


class DumpingInterface(object):
    _history = []
    _tempDir = const.TEST_SERVER_DIR

    def __init__(self):
        ut.createdir(self._tempDir)

    def parseData(self, data):
        """Interface to parse data."""
        pass

    def tempDump(self, obj):
        """Dump data to temp file."""
        parsed = self.parseData(obj)
        if type(parsed) is list:
            dumpObj = self._history + parsed
        else:
            dumpObj = self._history.append(parsed)
        file_tranport = join(self._tempDir, str(id(self)))
        with open(file_tranport, "w") as f:
            pickle.dump(dumpObj, f)


class WFPadTestTransport(WFPadTransport, DumpingInterface):

    def __init__(self):
        DumpingInterface.__init__(self)

    def msg2dict(self, msg):
        """Return a dictionary representation of a wfpad message."""
        return {"opcode": msg.opcode,
                "payload": msg.payload,
                "args": msg.args,
                "flags": msg.flags,
                "time": time(),
                }

    def parseData(self, data):
        msgs = self._msgExtractor.extract(data)
        return [self.msg2dict(msg) for msg in msgs if msg]

    def processMessages(self, data):
        super(WFPadTestTransport, self).processMessages(data)
        self.tempDump(data)

    def receivedDownstream(self, data):
        super(WFPadTestTransport, self).receivedDownstream(data)


class WFPadTestClient(WFPadTestTransport):
    pass


class WFPadTestServer(WFPadTestTransport, DumpingInterface):
    pass


class DummyTestTransport(DummyTransport, DumpingInterface):

    def __init__(self):
        DumpingInterface.__init__(self)

    def parseData(self, data):
        return (time(), len(data))

    def receivedDownstream(self, data):
        super(DummyTestTransport, self).receivedDownstream(data)
        self.tempDump(data)


class DummyTestClient(DummyTestTransport):
    pass


class DummyTestServer(DummyTestTransport):
    pass
