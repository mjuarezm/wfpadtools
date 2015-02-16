"""This module tests the WFPadTools primitives."""
import unittest

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import testutil as tu
from obfsproxy.test.transports.wfpadtools import wfpad_tester as wt


class TestSendPadding(wt.TestSendControlMessage, tu.STTest):
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


class TestBatchPadMsgs(wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay, msg_level = "id123", 5, 1, True
    args = [sessId, L, delay, msg_level]

    # Give server enough time to send padding
    AFTER_SESSION_TIME = 5

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


class TestBatchPadBytes(wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay, msg_level = "id123", 5, 1, False
    args = [sessId, L, delay, msg_level]

    # Give server enough time to send padding
    AFTER_SESSION_TIME = 5

    def test_num_sent_bytes_is_multiple_of_L(self):
        """Test the number of bytes received by the client is multiple of `L`.

        BATCH_PAD primitive should pad the link to multiple of `L`. Since
        we sent the control message to the server, we expect bytes received
        by client to satisfy this condition.
        """
        obs_total_bytes = self.clientState["_totalBytes"]['rcv']
        self.assertTrue(obs_total_bytes > 0
                        and obs_total_bytes % self.L == 0,
                        "The observed number of bytes (%s) "
                        "is not a multiple of %s."
                        % (obs_total_bytes, self.L))


class TestPayloadPad(wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_PAYLOAD_PAD
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]

    # Give server enough time to send padding
    AFTER_SESSION_TIME = 5

    def test_num_data_bytes_correctly_padded(self):
        pass


class TotalPadPad(wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_TOTAL_PAD
    sessId, delay = "id123", 1
    args = [sessId, delay]

    # Give server enough time to send padding
    AFTER_SESSION_TIME = 5

    def test_num_messages_is_power_of_2(self):
        pass

if __name__ == "__main__":
    unittest.main()
