"""""Provide test classes for benchmarking timing properties of WFPadTools."""
import unittest

# WFPadTools imports
from obfsproxy.test import tester
import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools import const
from obfsproxy.test.transports.wfpadtools import wfpad_tester as wt
from obfsproxy.transports.wfpadtools.util import testutil as tu
from util.util import consec_elem

# Logging timing stats:
log = logging.get_obfslogger()


class TestrRTT(wt.WFPadShimConfig, wt.TestSendControlMessage,
               tu.STTest):
    """Estimate mean roundtrip time."""
    # repetitions of sending padding
    repetitions = 3

    # Args of control message
    opcode = const.OP_SEND_PADDING
    N, t = 1, 1
    args = [N, t]

    def doWhileSession(self):
        for _ in xrange(self.repetitions):
            wt.TestSendControlMessage.doWhileSession(self)

    @unittest.skip("Skip for now.")
    def test_timing(self):
        """Test that delay is correct."""
        ignores_rcv_times = [e.rcvTime for e in self.padding_msgs(self.clientMsgs)]
        controls_rcv_times = [e.rcvTime for e in self.control_msgs(self.serverMsgs)]
        rtt_times = consec_elem(ignores_rcv_times)
        # TODO
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

if __name__ == "__main__":
    unittest.main()
