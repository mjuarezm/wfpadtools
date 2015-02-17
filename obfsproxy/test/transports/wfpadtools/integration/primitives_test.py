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

class TestSendPadding(wt.WFPadShimConfig, wt.TestSendControlMessage,
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

class TestBurstHistogram(wt.WFPadShimConfig, wt.TestSendDataServer):
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

    def test_basic_func(self):

        # Is it sampling and delaying?


        # Is it removing tokens?


        # Is it interpolating?
        pass

    def test_burst_is_padded(self):
        """Reproduce a burst and test that is padded according to histo."""
        # TODO
        pass


class TestBurstHistogramSnd(TestBurstHistogram, wt.WFPadShimConfig,
                            wt.TestSendDataServer):
    """Test primitive for sending histogram."""
    when = "snd"


class TestGapHistogram(wt.WFPadShimConfig, wt.TestSendDataServer):
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

    def test_basic_func(self):

        # Is it sampling and delaying?


        # Is it removing tokens?


        # Is it interpolating?
        pass

    def test_gap_is_padded(self):
        """Reproduce a gap and test is padded according to histo."""
        # TODO
        pass


class TestGapHistogramSnd(TestGapHistogram, wt.WFPadShimConfig,
                          wt.TestSendDataServer):
    """Test primitive for sending histogram."""
    when = "snd"


# CS-BuFLO PRIMITIVES
#####################

class TestPayloadPadMsgs(wt.BuFLOShimConfig, wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_PAYLOAD_PAD
    sessId, delay, msg_level = "id123", 1, True
    args = [sessId, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_msgs_is_multiple_of_closer_power_of_two(self):
        """Test that stop condition works for messages.

        PAYLOAD_PAD must pad end of session to closest multiple of
        the closest power of two of the number of data units (bytes
        or messages) that have been transmitted up to the moment.
        """
        last_srv_ctrl_msg = self.control_msgs(self.serverMsgs)[-1]
        end_sess_srv_st = self.get_state(last_srv_ctrl_msg, self.serverDumps)
        self.assertTrue(end_sess_srv_st, "Cannot find end of session message.")
        to_pad = end_sess_srv_st['_numMessages']['snd']
        divisor = end_sess_srv_st['_dataMessages']['snd']
        k = closest_power_of_two(divisor)
        total_pad = closest_multiple(to_pad, k)
        obs_num_cl_msgs = self.clientState["_numMessages"]['rcv']
        self.assertTrue(obs_num_cl_msgs > 0
                        and obs_num_cl_msgs >= total_pad,
                        "The observed number of sent messages (%s) has not been"
                        " padded to %s." % (obs_num_cl_msgs, total_pad))


class TestPayloadPadBytes(wt.BuFLOShimConfig, wt.TestSendDataServer,
                          tu.STTest):
    opcode = const.OP_PAYLOAD_PAD
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_bytes_is_multiple_of_power_of_two(self):
        """Test that stop condition works for bytes.

        PAYLOAD_PAD must pad end of session to closest multiple of
        the closest power of two of the number of bytes that have
        been transmitted up to the moment.
        """
        last_srv_ctrl_msg = self.control_msgs(self.serverMsgs)[-1]
        end_sess_srv_st = self.get_state(last_srv_ctrl_msg, self.serverDumps)
        self.assertTrue(end_sess_srv_st, "Cannot find end of session message.")
        to_pad = end_sess_srv_st['_totalBytes']['snd']
        divisor = end_sess_srv_st['_dataBytes']['snd']
        k = closest_power_of_two(divisor)
        total_pad = closest_multiple(to_pad, k)
        obs_num_cl_bytes = self.clientState["_totalBytes"]['rcv']
        self.assertTrue(obs_num_cl_bytes > 0
                        and obs_num_cl_bytes >= total_pad,
                        "The observed number of sent bytes (%s) has not been"
                        " padded to %s." % (obs_num_cl_bytes, total_pad))


class TestTotalPadMsgs(wt.BuFLOShimConfig, wt.TestSendDataServer, tu.STTest):
    # Primitive args
    opcode = const.OP_TOTAL_PAD
    sessId, delay, msg_level = "id123", 1, True
    args = [sessId, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_msgs_is_closest_power_of_two(self):
        """Test that stop condition works correctly.

        TOTAL_PAD must pad end of session to closest multiple of
        a power of two of the number of messages that have been
        transmitted up to the moment.
        """
        last_srv_ctrl_msg = self.control_msgs(self.serverMsgs)[-1]
        end_sess_srv_st = self.get_state(last_srv_ctrl_msg, self.serverDumps)
        self.assertTrue(end_sess_srv_st, "Cannot find end of session message.")
        to_pad = end_sess_srv_st['_numMessages']['snd']
        total_pad = closest_power_of_two(to_pad)
        obs_num_cl_msgs = self.clientState["_numMessages"]['rcv']
        self.assertTrue(obs_num_cl_msgs > 0
                        and obs_num_cl_msgs >= total_pad,
                        "The observed number of sent messages (%s) has not "
                        "been padded to %s." % (obs_num_cl_msgs, total_pad))


class TestTotalPadBytes(wt.TestSendDataServer, tu.STTest):
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
    sessId, delay, msg_level = "id123", 1000, False
    args = [sessId, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_bytes_is_closest_power_of_two(self):
        """Test that stop condition works correctly.

        TOTAL_PAD must pad end of session to closest multiple of
        a power of two of the number of bytes that have been
        transmitted up to the moment.
        """
        last_srv_ctrl_msg = self.control_msgs(self.serverMsgs)[-1]
        end_sess_srv_st = self.get_state(last_srv_ctrl_msg, self.serverDumps)
        self.assertTrue(end_sess_srv_st, "Cannot find end of session message.")
        to_pad = end_sess_srv_st['_totalBytes']['snd']
        k = closest_power_of_two(to_pad)
        total_pad = closest_multiple(to_pad, k)
        obs_num_cl_bytes = self.clientState["_totalBytes"]['rcv']
        self.assertTrue(obs_num_cl_bytes > 0
                        and obs_num_cl_bytes >= total_pad,
                        "The observed number of sent bytes (%s) has not been"
                        " padded to %s." % (obs_num_cl_bytes, total_pad))


# TAMARAW PRIMITIVES
#####################

class TestBatchPadMsgs(wt.BuFLOShimConfig, wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay, msg_level = "id123", 5, 1, True
    args = [sessId, L, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_msgs_is_multiple_of_L(self):
        """Test the number of messages received by the client is multiple of `L`.

        BATCH_PAD primitive should pad the link to multiple of `L`. Since
        we sent the control message to the server, we expect messages received
        by client to satisfy this condition.
        """
        obs_num_client_msgs = len(self.clientMsgs)
        closest_l_mult = closest_multiple(obs_num_client_msgs, self.L, ceil=False)
        self.assertTrue(obs_num_client_msgs > 0
                        and obs_num_client_msgs - 1 <= closest_l_mult,
                        "The observed number of padding messages (%s) "
                        "is not a multiple of %s."
                        % (obs_num_client_msgs, self.L))


class TestBatchPadBytes(wt.BuFLOShimConfig, wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay, msg_level = "id123", 5, 1, False
    args = [sessId, L, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_bytes_is_larger_than_closest_multiple_of_L(self):
        """Test the number of bytes received by the client is multiple of `L`.

        BATCH_PAD primitive should pad the link to multiple of `L`. Since
        we sent the control message to the server, we expect bytes received
        by client to satisfy this condition.
        """
        obs_total_bytes = self.clientState["_totalBytes"]['rcv']
        closest_l_mult = closest_multiple(obs_total_bytes, self.L, ceil=False)
        self.assertTrue(obs_total_bytes > 0
                        and obs_total_bytes - closest_l_mult <= const.MPU,
                        "The observed number of bytes (%s) is not a multiple"
                        " of %s." % (obs_total_bytes, self.L))


if __name__ == "__main__":
    unittest.main()
