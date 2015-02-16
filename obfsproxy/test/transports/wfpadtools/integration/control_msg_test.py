"""Test control message communication from client to server."""

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import testutil as tu
import obfsproxy.test.transports.wfpadtools.wfpad_tester as wft


class TestSendPaddingControl(wft.TestControlMessages, tu.STTest):
    opcode = const.OP_SEND_PADDING
    N, t = 5, 1
    args = [N, t]


class TestAppHintControl(wft.TestControlMessages, tu.STTest):
    opcode = const.OP_APP_HINT
    sessId,  status = "id123", True
    args = [sessId, status]


class TestBurstHistoControl(wft.TestControlMessages, tu.STTest):
    sessId = "id123"
    opcode = const.OP_BURST_HISTO
    delay = 1
    tokens = 100000
    histo = [tokens, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    labels_ms = [0, delay, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
                 2048, 4096, 8192, 16384, 32768, 65536, -1]
    removeTokens = True
    interpolate = False
    when = "rcv"
    args = [histo, labels_ms, removeTokens, interpolate, when]


class TestGapHistoControl(wft.TestControlMessages, tu.STTest):
    sessId = "id123"
    opcode = const.OP_BURST_HISTO
    delay = 1
    tokens = 100000
    histo = [tokens, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    labels_ms = [0, delay, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
                 2048, 4096, 8192, 16384, 32768, 65536, -1]
    removeTokens = True
    interpolate = False
    when = "rcv"
    args = [histo, labels_ms, removeTokens, interpolate, when]


class TestTotalPadControl(wft.TestControlMessages, tu.STTest):
    opcode = const.OP_TOTAL_PAD
    sessId, delay = "id123", 1
    args = [sessId, delay]


class TestPayloadPadControl(wft.TestControlMessages, tu.STTest):
    opcode = const.OP_PAYLOAD_PAD
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]


class TestBatchPadControl(wft.TestControlMessages, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay = "id123", 5, 1
    args = [sessId, L, delay]
