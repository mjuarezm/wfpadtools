"""This module tests the WFPadTools primitives."""
import unittest

# WFPadTools imports
import obfsproxy.common.log as logging
from obfsproxy.test import tester as ts
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import testutil as tu
from obfsproxy.test.transports.wfpadtools import wfpad_tester as wt
from obfsproxy.transports.wfpadtools.util.mathutil import closest_power_of_two

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
        """Test that number of messages and delay are correct."""
        # If we sent a SEND_PADDING message to the server, we expect
        # `N` padding (send_ignore) messages back after delay `t`.

        # Test that the number of padding messages is correct.
        client_padding_msgs = self.padding_msgs(self.clientMsgs)
        expected_num_pad_msgs = self.N
        observed_num_pad_msgs = len(client_padding_msgs)
        self.assertEqual(expected_num_pad_msgs, observed_num_pad_msgs,
                         "Observed num of pad messages (%s) does not match the"
                         " expected num of pad messages (%s)."
                         % (observed_num_pad_msgs, expected_num_pad_msgs))

        # Test that the delay after the control message was sent is correct.
        first_ignore_rcv_client = self.padding_msgs(self.clientMsgs)[0]
        control_msg_rcv_server = self.control_msgs(self.serverMsgs)[0]
        ign_ts = float(first_ignore_rcv_client.rcvTime)
        ctl_ts = float(control_msg_rcv_server.rcvTime)
        observed_delay = ign_ts - ctl_ts  # as ctrl msg goes before 1st ignore
        expected_delay = self.t / const.SCALE
        self.assertAlmostEqual(expected_delay, observed_delay,
                               msg="Observed delay (%s-%s=%s) does not match"
                               " the expected delay (%s)."
                               % (ign_ts, ctl_ts, observed_delay,
                                  expected_delay), delta=0.05)


# ADAPTIVE  PRIMITIVES
######################

class TestBurstHistogram(wt.WFPadShimConfig, wt.TestSendDataServer):
    pass


class TestGapHistogram(wt.WFPadShimConfig, wt.TestSendDataServer):
    pass


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
        obs_num_client_msgs = len(self.clientMsgs)
        num_data_msgs = len(self.data_msgs(self.clientMsgs))
        L = closest_power_of_two(num_data_msgs)
        self.assertTrue(obs_num_client_msgs > 0
                        and obs_num_client_msgs % L == 0,
                        "The observed number of sent messages (%s) "
                        "is not a multiple of %s." % (obs_num_client_msgs, L))


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
        obs_num_cl_bytes = self.clientState["_totalBytes"]['rcv']
        num_data_bytes = self.clientState["_dataBytes"]['rcv']
        L = closest_power_of_two(num_data_bytes)
        self.assertTrue(obs_num_cl_bytes > 0
                        and obs_num_cl_bytes % L == 0,
                        "The observed number of sent bytes (%s) is not a"
                        " multiple of %s." % (obs_num_cl_bytes, L))

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
        obs_num_client_msgs = len(self.clientMsgs)
        L = closest_power_of_two(obs_num_client_msgs)
        self.assertTrue(obs_num_client_msgs > 0
                        and obs_num_client_msgs % L == 0,
                        "The observed number of sent messages (%s) "
                        "is not a multiple of %s." % (obs_num_client_msgs, L))


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
        obs_num_cl_bytes = self.clientState["_totalBytes"]['rcv']
        L = closest_power_of_two(obs_num_cl_bytes)
        self.assertTrue(obs_num_cl_bytes > 0
                        and obs_num_cl_bytes % L == 0,
                        "The observed number of sent bytes (%s) is not a"
                        " multiple of %s." % (obs_num_cl_bytes, L))


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
        self.assertTrue(obs_num_client_msgs > 0
                        and obs_num_client_msgs % self.L == 0,
                        "The observed number of padding messages (%s) "
                        "is not a multiple of %s."
                        % (obs_num_client_msgs, self.L))


class TestBatchPadBytes(wt.BuFLOShimConfig, wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay, msg_level = "id123", 5, 1, False
    args = [sessId, L, delay, msg_level]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def test_num_sent_bytes_is_multiple_of_L(self):
        """Test the number of bytes received by the client is multiple of `L`.

        BATCH_PAD primitive should pad the link to multiple of `L`. Since
        we sent the control message to the server, we expect bytes received
        by client to satisfy this condition.
        """
        obs_total_bytes = self.clientState["_totalBytes"]['rcv']
        self.assertTrue(obs_total_bytes > 0
                        and obs_total_bytes % self.L == 0,
                        "The observed number of bytes (%s) is not a multiple"
                        " of %s." % (obs_total_bytes, self.L))


if __name__ == "__main__":
    unittest.main()
