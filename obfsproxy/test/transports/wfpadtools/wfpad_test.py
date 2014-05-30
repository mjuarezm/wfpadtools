import random
from time import sleep
import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import wfpad
import obfsproxy.transports.wfpadtools.util as ut


class WFPadTest(STTest):
    """Test methods from WFPadTransport class."""

    class DataStream():

        def __init__(self, data):
            self.data = data

        def read(self):
            return self.data

    def generate_stream(self, output, t_max, psize=1):
        t = 0
        while t < t_max:
            sleep_t = random.random()
            t += sleep_t
            if random.randrange(2):
                output(self.DataStream(ut.rand_str(size=psize)))
            sleep(sleep_t)

    def test_padding(self):
        wfpad_client = wfpad.WFPadClient()
        wfpad_client.circuitConnected()
        self.generate_stream(wfpad_client.receivedUpstream, 5)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
