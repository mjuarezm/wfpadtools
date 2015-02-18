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


if __name__ == "__main__":
    unittest.main()
