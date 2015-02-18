"""This module tests the WFPadTools primitives."""
import unittest

# WFPadTools imports
import obfsproxy.common.log as logging
from obfsproxy.test import tester as ts
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import testutil as tu
from obfsproxy.test.transports.wfpadtools import wfpad_tester as wt
from obfsproxy.transports.wfpadtools.util.mathutil import closest_power_of_two,\
    closest_multiple

# Logging settings:
log = logging.get_obfslogger()


AFTER_SESSION_TIME_PRIMITIVE = 5


# GENERAL PRIMITIVES
#####################

class TestSendPadding(wt.WFPadShimConfig, wt.SendControlMessageTest,
                      tu.STTest):
    opcode = const.OP_SEND_PADDING
    N, t = 5, 1
    args = [N, t]

    def test_number_and_delay_padding_messages(self):
        """Test that number of messages is correct."""
        # If we sent a SEND_PADDING message to the server, we expect
        # `N` padding (send_ignore) messages back.
        # Delay correctness is tested in the timing module.
        client_padding_msgs = self.padding_msgs(self.clientMsgs)
        expected_num_pad_msgs = self.N
        observed_num_pad_msgs = len(client_padding_msgs)
        self.assertEqual(expected_num_pad_msgs, observed_num_pad_msgs,
                         "Observed num of pad messages (%s) does not match the"
                         " expected num of pad messages (%s)."
                         % (observed_num_pad_msgs, expected_num_pad_msgs))


# ADAPTIVE  PRIMITIVES
######################

class TestBurstHistogram(wt.WFPadShimConfig, wt.SendDataServerTest, tu.STTest):
    sessId = "id123"
    opcode = const.OP_BURST_HISTO
    delay = 1
    tokens = 100000
    histo = [tokens, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    labels_ms = [0, delay, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
                 2048, 4096, 8192, 16384, 32768, 65536, -1]
    removeTokens = True
    interpolate = True
    when = "rcv"
    args = [histo, labels_ms, removeTokens, interpolate, when]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    @unittest.skip("Skip for now...")
    def test_basic_func(self):

        # Is it sampling and delaying?


        # Is it removing tokens?


        # Is it interpolating?
        pass

    @unittest.skip("Skip for now...")
    def test_burst_is_padded(self):
        """Reproduce a burst and test that is padded according to histo."""
        # TODO
        pass


class TestBurstHistogramSnd(TestBurstHistogram, wt.WFPadShimConfig,
                            wt.SendDataServerTest):
    """Test primitive for sending histogram."""
    when = "snd"


class TestGapHistogram(wt.WFPadShimConfig, wt.SendDataServerTest, tu.STTest):
    sessId = "id123"
    opcode = const.OP_BURST_HISTO
    delay = 1
    tokens = 100000
    histo = [tokens, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    labels_ms = [0, delay, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
                 2048, 4096, 8192, 16384, 32768, 65536, -1]
    removeTokens = True
    interpolate = True
    when = "rcv"
    args = [histo, labels_ms, removeTokens, interpolate, when]

    @unittest.skip("Skip for now...")
    def test_basic_func(self):

        # Is it sampling and delaying?


        # Is it removing tokens?


        # Is it interpolating?
        pass

    @unittest.skip("Skip for now...")
    def test_gap_is_padded(self):
        """Reproduce a gap and test is padded according to histo."""
        # TODO
        pass


class TestGapHistogramSnd(TestGapHistogram, wt.WFPadShimConfig,
                          wt.SendDataServerTest):
    """Test primitive for sending histogram."""
    when = "snd"


# PADDING PRIMITIVES
####################

class PaddingPrimitiveTest(wt.SendDataServerTest):
    sessId, delay, msg_level = "id123", 1, True
    args = [sessId, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def get_topad(self, end_sess_srv_st):
        """Either messages or bytes."""
        pass

    def get_totalpad(self, end_sess_srv_st):
        """Total expected padding.

        Depends on the particular primitive.
        """
        pass

    def get_end_session_state(self):
        """Return end session of state."""
        # Get last control message received by server (end of session)
        last_srv_ctrl_msg = self.control_msgs(self.serverMsgs)[-1]
        # Get the state of the server associated to that message
        end_sess_srv_st = self.get_state(last_srv_ctrl_msg, self.serverDumps)
        # Check state has been found successfully
        self.assertTrue(end_sess_srv_st, "Cannot find end of session message.")
        return end_sess_srv_st


    def test_num_sent_msg(self):
        """Test that stop condition works for messages."""
        # Get end of session state
        end_sess_srv_st = self.get_end_session_state()
        # Get to pad units
        pad_units = self.get_topad(end_sess_srv_st)
        total_pad = self.get_totalpad(end_sess_srv_st)
        obs_num_cl_msgs = pad_units['rcv']
        self.assertTrue(obs_num_cl_msgs > 0
                        and obs_num_cl_msgs >= total_pad,
                        "The observed  padding (%s) does not match "
                        " the total pad (%s)." % (obs_num_cl_msgs, total_pad))


class PaddingPrimitiveTestMsgs(PaddingPrimitiveTest):
    sessId, delay, msg_level = "id123", 1, True
    args = [sessId, delay, msg_level]

    def get_topad(self, end_sess_srv_st):
        return self.clientState['_numMessages']


class PaddingPrimitiveTestBytes(PaddingPrimitiveTest):
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]

    def get_topad(self, end_sess_srv_st):
        return self.clientState['_totalBytes']

# CS-BuFLO PRIMITIVES
#####################

class TestPayloadPadMsgs(wt.BuFLOShimConfig, PaddingPrimitiveTestMsgs, tu.STTest):
    opcode = const.OP_PAYLOAD_PAD

    def get_totalpad(self, end_sess_srv_st):
        to_pad = end_sess_srv_st['_numMessages']['snd']
        divisor = end_sess_srv_st['_dataMessages']['snd']
        k = closest_power_of_two(divisor)
        return closest_multiple(to_pad, k)


class TestPayloadPadBytes(wt.BuFLOShimConfig, PaddingPrimitiveTestBytes, tu.STTest):
    opcode = const.OP_PAYLOAD_PAD

    def get_totalpad(self, end_sess_srv_st):
        to_pad = end_sess_srv_st['_totalBytes']['snd']
        divisor = end_sess_srv_st['_dataBytes']['snd']
        k = closest_power_of_two(divisor)
        return closest_multiple(to_pad, k)


class TestTotalPadMsgs(wt.BuFLOShimConfig, PaddingPrimitiveTestMsgs, tu.STTest):
    opcode = const.OP_TOTAL_PAD

    def get_totalpad(self, end_sess_srv_st):
        to_pad = end_sess_srv_st['_numMessages']['snd']
        return closest_power_of_two(to_pad)


class TestTotalPadBytes(PaddingPrimitiveTestBytes, tu.STTest):
    # Transport args
    # WARNING: Pad to bytes primitives depend a lot on the size of
    # the MTU! Protocols with fixed-length size not a power of two
    # will never hit the condition. Protocols with variable length
    # cannot be predicted to reach the condition.
    psize = const.TOR_CELL_SIZE  # 512 bytes, it is a power of 2!
    transport = "buflo"
    server_args = ("buflo", "server",
                "127.0.0.1:%d" % ts.SERVER_PORT,
                "--period=1",
                "--psize=%d" % psize,
                "--mintime=10",
                "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                "--test=%s" % const.DUMPS["server"])
    client_args = ("buflo", "client",
                "127.0.0.1:%d" % ts.ENTRY_PORT,
                "--socks-shim=%d,%d" % (wt.SHIM_PORT, wt.SOCKS_PORT),
                "--period=1",
                "--psize=%d" % psize,
                "--mintime=10",
                "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                "--test=%s" % const.DUMPS["client"])

    # Primitive args
    opcode = const.OP_TOTAL_PAD

    def get_totalpad(self, end_sess_srv_st):
        to_pad = end_sess_srv_st['_totalBytes']['snd']
        return closest_power_of_two(to_pad)


# TAMARAW PRIMITIVES
#####################

class TestBatchPadMsgs(wt.WFPadShimConfig, PaddingPrimitiveTestMsgs, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, delay, L,  msg_level = "id123", 1, 5, True
    args = [sessId, L, delay, msg_level]

    def get_totalpad(self, end_sess_srv_st):
        to_pad = end_sess_srv_st['_numMessages']['snd']
        return closest_multiple(to_pad, self.L)


class TestBatchPadBytes(wt.WFPadShimConfig, PaddingPrimitiveTestBytes, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay, msg_level = "id123", 1, 5, True
    args = [sessId, delay, L, msg_level]

    def get_totalpad(self, end_sess_srv_st):
        to_pad = end_sess_srv_st['_numMessages']['snd']
        return closest_multiple(to_pad, self.L)


if __name__ == "__main__":
    unittest.main()
