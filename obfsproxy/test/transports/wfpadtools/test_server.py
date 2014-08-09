"""
The test_server module implements test transports placed in between the
transport client and transport server that dump the state and messages
received into a temporal file in order to be processed by the test module.
"""
import obfsproxy.common.log as logging
import obfsproxy.transports.wfpadtools.util as ut
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.dummy import DummyTransport
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport, WFPadClient,\
    WFPadServer

import pickle
from time import time
from os.path import join
import json

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
            self._history = self._history + parsed
        else:
            self._history.append(parsed)
        file_transport = join(self._tempDir, str(id(self)))
        with open(file_transport, "w") as f:
            pickle.dump(self._history, f)


class WFPadTestTransport(WFPadTransport, DumpingInterface):

    def __init__(self):
        DumpingInterface.__init__(self)
        WFPadTransport.__init__(self)

    def msg2dict(self, msg):
        """Return a dictionary representation of a wfpad message."""
        return {"opcode": msg.opcode,
                "payload": msg.payload,
                "args": msg.args,
                "flags": msg.flags,
                "time": time(),
                "client": self.weAreClient,
                "visiting": self._visiting,
                "sessid": self._sessId,
                "ctrlId": msg.ctrlId,
                "totalArgsLen": msg.totalArgsLen,
                "numMessages": self._numMessages
                }

    def concatControlMsg(self, msgs):
        ctrlMsgs = [msg for msg in msgs if msg['flags'] == const.FLAG_CONTROL]
        noCtrlMsgs = [msg for msg in msgs if msg['flags'] != const.FLAG_CONTROL]
        if not ctrlMsgs:
            return noCtrlMsgs
        finalMsg = ctrlMsgs[0]
        for msg in ctrlMsgs[1:]:
            finalMsg["args"] += msg["args"]
        return [finalMsg] + noCtrlMsgs

    def parseData(self, msgs):
        parsed = [self.msg2dict(msg) for msg in msgs if msg]
        ctrlConcat = self.concatControlMsg(parsed)
        return ctrlConcat

    def receivedUpstream(self, data):
        d = data.read()
        isControl = self.parseControl(d)
        if isControl:
            return
        if self._state >= const.ST_CONNECTED:
            self.pushData(d)
            self.tempDump(d)
        else:
            self._sendBuf += d

    def processMessages(self, data):
        msgs = super(WFPadTestTransport, self).processMessages(data)
        self.tempDump(msgs)


class WFPadTestClient(WFPadTestTransport, WFPadClient):

    def parseControl(self, data):
        if ":" in data:
            op, payload = data.split(":")
            if op == "TEST":
                opcode, args_str = payload.split(";")
                opcode = int(opcode)
                args = None
                if args_str != "":
                    args = json.loads(args_str)
                WFPadClient.sendControlMessage(self, opcode, args)
            return True
        else:
            return False


class WFPadTestServer(WFPadTestTransport, WFPadServer):
    pass


class DummyTestTransport(DummyTransport, DumpingInterface):

    def __init__(self):
        DumpingInterface.__init__(self)
        DummyTransport.__init__(self)

    def parseData(self, data):
        return (len(data), time())

    def receivedDownstream(self, data):
        d = data.read()
        self.circuit.upstream.write(d)
        self.tempDump(d)


class DummyTestClient(DummyTestTransport):
    pass


class DummyTestServer(DummyTestTransport):
    pass
