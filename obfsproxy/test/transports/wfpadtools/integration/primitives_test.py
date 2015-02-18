"""This module tests the WFPadTools primitives."""
import unittest
from time import sleep

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


# CS-BuFLO PRIMITIVES
#####################

# PAYLOAD PRIMITIVES

class PayloadPadTest(wt.PadPrimitiveTest):
    opcode = const.OP_PAYLOAD_PAD

    real_msgs = 10
    junk_msgs = 3

    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def total_pad(self):
        total = self.get_units(self.total_msgs())
        data = self.get_units(self.data_msgs())
        k = closest_power_of_two(data)
        return closest_multiple(total, k)


class TestPayloadPadMsgs(wt.BuFLOShimConfig, PayloadPadTest, tu.STTest):
    sessId, delay, msg_level = "id123", 1, True
    args = [sessId, delay, msg_level]
    units = 1


class TestPayloadPadBytes(wt.BuFLOShimConfig, PayloadPadTest, tu.STTest):
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]
    units = const.MPU  # It's only the data bytes!

    def total_pad(self):
        total = self.get_units(self.total_msgs())
        data = PayloadPadTest.LEN_DATA_STR * self.data_msgs()
        k = closest_power_of_two(data)
        return closest_multiple(total, k)


# TOTAL PAD PRIMITIVES

class TotalPadTest(wt.PadPrimitiveTest):
    opcode = const.OP_TOTAL_PAD

    real_msgs = 10
    junk_msgs = 3

    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def total_pad(self):
        total = self.get_units(self.total_msgs())
        return closest_power_of_two(total)


class TestTotalPadMsgs(wt.BuFLOShimConfig, TotalPadTest, tu.STTest):
    sessId, delay, msg_level = "id123", 1, True
    args = [sessId, delay, msg_level]
    units = 1


class TestTotalPadBytes(wt.BuFLOShimConfig, TotalPadTest, tu.STTest):
    sessId, delay,  msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]
    units = const.TOR_CELL_SIZE

    # WARNING: Pad to bytes primitives depend a lot on the size of
    # the MTU! Protocols with fixed-length size not a power of two
    # will never hit the condition. Protocols with variable length
    # cannot be predicted to reach the condition.
    server_args_list = list(wt.BuFLOShimConfig.server_args)
    server_args_list[4] = "--psize=%d" % const.TOR_CELL_SIZE  # 512 bytes!
    server_args = tuple(server_args_list)


# TAMARAW PRIMITIVES
#####################

class BatchPadTest(wt.PadPrimitiveTest):
    opcode = const.OP_BATCH_PAD

    real_msgs = 10
    junk_msgs = 3

    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def total_pad(self):
        total = self.get_units(self.total_msgs())
        return closest_multiple(total, self.L)


class TestBatchPadMsgs(wt.BuFLOShimConfig, BatchPadTest, tu.STTest):
    sessId, delay, L,  msg_level = "id123", 1, 5, True
    args = [sessId, L, delay, msg_level]
    units = 1


class TestBatchPadBytes(wt.BuFLOShimConfig, BatchPadTest, tu.STTest):
    sessId, delay, L,  msg_level = "id123", 1, 5, False
    args = [sessId, L, delay, msg_level]
    units = const.MPU


# ADAPTIVE  PRIMITIVES
######################

class TestBurstHistogram(wt.WFPadShimConfig, wt.HistoPrimitiveTest, tu.STTest):
    sessId = "id123"
    opcode = const.OP_BURST_HISTO

    tokens = 10
    delay = 10

    histo = [tokens, 0, 0, 0, 0, 0, 0]
    labels_ms = [delay, 2, 4, 8, 16, 32, -1]
    removeTokens = True
    interpolate = False
    when = "snd"
    args = [histo, labels_ms, removeTokens, interpolate, when]

    # Give server enough time to pad the end of the session
    AFTER_SESSION_TIME = AFTER_SESSION_TIME_PRIMITIVE

    def doWhileSession(self):
        wt.HistoPrimitiveTest.doWhileSession(self)
        sleep(0.1)
        self.send_to_server(self.DATA_STR)

    def test_is_padding(self):
        # Check delay histo is larger than time between ignore and data
        # the deferrer should cancel and restart.

        # Is it sampling and delaying?
        # We need to find the two adjacent ignores around data in server
        #     data_snd_time - ignore1_snd.Time < histo_delay
        #     ignore2_snd.Time - data_snd_time approx = histo_delay
        self.assertTrue(len(self.data_msgs(self.clientMsgs)) == 2)
        data_msg = self.data_msgs(self.clientMsgs)[1]
        non_ctrl_msgs = self.payload_msgs(self.clientMsgs)
        idx_data = self.get_index_msg(data_msg, non_ctrl_msgs)
        ig1 = non_ctrl_msgs[idx_data - 1]
        ig2 = non_ctrl_msgs[idx_data + 1]
        t1 = data_msg.rcvTime - ig1.rcvTime
        t2 = ig2.rcvTime - data_msg.rcvTime
        sec_delay = self.delay / const.SCALE
        self.assertTrue(t1 < sec_delay,
                        "Time between ignore before data (%s) is not less than"
                        " histo_delay (%s)" % (t1, sec_delay))
        self.assertAlmostEqual(t2, sec_delay, msg="Time between msg data "
                               "and second ignore (%s) is not similar to "
                               "histo delay (%s)." % (t2, sec_delay),
                               delta=0.05)

        # Is it removing tokens?
        histo = self.serverState["_burstHistoProbdist"]["snd"].histo
        self.assertTrue(histo[0] < self.tokens, "No token has been removed.")


class TestGapHistogram(wt.WFPadShimConfig, wt.HistoPrimitiveTest, tu.STTest):
    sessId = "id123"
    opcode = const.OP_GAP_HISTO

    tokens = 10
    delay = 10

    histo = [tokens, 0, 0, 0, 0, 0, 0]
    labels_ms = [delay, 2, 4, 8, 16, 32, -1]
    removeTokens = True
    interpolate = False
    when = "snd"
    args = [histo, labels_ms, removeTokens, interpolate, when]

    burst_delay = 1
    burst_histo = [tokens, 0, 0, 0, 0, 0, 0]
    burst_lab_ms = [burst_delay, 2, 4, 8, 16, 32, -1]
    burst_args = [burst_histo, burst_lab_ms, removeTokens, interpolate, when]

    # Give server enough time to pad the end of the session
    DURING_SESSION_TIME = 0
    AFTER_SESSION_TIME = 0

    def doBeforeSessionStarts(self):
        self.send_instruction(const.OP_TOTAL_PAD, [self.sessId, 1, False])
        sleep(0.1)
        self.send_instruction(const.OP_BURST_HISTO, self.burst_args)
        sleep(0.1)
        wt.HistoPrimitiveTest.doBeforeSessionStarts(self)

    def test_is_padding(self):
        # Is it sampling and delaying?
        # Check delay between third consecutive delay corresponds to
        # gap delay (different enough from burst delay)
        pad_msgs = self.padding_msgs(self.clientMsgs)
        pad_2 = pad_msgs[1]
        pad_3 = pad_msgs[2]
        obs_delay = pad_3.rcvTime - pad_2.rcvTime
        sec_delay = self.delay / const.SCALE

        # Similar to expected delay
        self.assertAlmostEqual(obs_delay, sec_delay, msg="Observed gap delay  "
                               "(%s) is not similar to gap delay (%s)."
                               % (obs_delay, sec_delay), delta=0.005)

        # Is it removing tokens?
        histo = self.serverState["_gapHistoProbdist"]['snd'].histo
        self.assertTrue(histo[0] < self.tokens, "No token has been removed.")


if __name__ == "__main__":
    unittest.main()
