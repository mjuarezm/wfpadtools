import unittest
from time import sleep

# WFPadTools imports
from obfsproxy.transports.wfpadtools.const import SCALE
from obfsproxy.test.transports.wfpadtools import wfpad_tester as wfp


class TestBuFLOStopPadding(wfp.BuFLOShimConfig, wfp.PrimitiveTest,
                           unittest.TestCase):
    mintime = 2000
    server_args_list = list(wfp.BuFLOShimConfig.server_args)
    server_args_list[5] = "--mintime=%d" % mintime
    server_args = tuple(server_args_list)

    def doWhileSession(self):
        sleep(0.1)
        # Trigger padding
        self.send_to_server(self.DATA_STR)

    def test_stop_after_mintime(self):
        padding_msgs = self.padding_msgs(self.clientMsgs)
        assert(len(padding_msgs) > 2)
        first_msg_time = padding_msgs[0].rcvTime
        last_msg_time = padding_msgs[-1].rcvTime
        elapsed = last_msg_time - first_msg_time
        assert(elapsed > 0)
        sec_time = self.mintime / SCALE
        self.assertAlmostEqual(elapsed, sec_time, msg="Observed elapsed "
                               "time (%s) and buflo mintime (%s) don't match."
                               % (elapsed, sec_time),
                               delta=1)

if __name__ == "__main__":
    unittest.main()
