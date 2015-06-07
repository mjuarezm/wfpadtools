import unittest
from time import sleep

from obfsproxy.test.transports.wfpadtools import wfpad_tester as wfp
from obfsproxy.transports.wfpadtools.specific.adaptive import AdaptiveTransport

class AdaptiveTest(unittest.TestCase):

    @unittest.skip("for now")
    def test_payload_padding(self):
        pass

    @unittest.skip("for now")
    def test_total_padding(self):
        pass

    def test_divide_histogram(self):
        test_histo = {1: 0, 2: 50, 3: 20, 4: 20, "inf": 0}
        test_high = {2: 0, 3: 20, 4: 20, "inf": 0}
        test_low = {1: 0, 2: 50, "inf": 0}
        low, high = AdaptiveTransport.divideHistogram(test_histo)
        self.assertDictEqual(test_high, high)
        self.assertDictEqual(test_low, low)

    def test_get_histo_from_distr_params(self):
        h = AdaptiveTransport.getHistoFromDistrParams("weibull", 2)
        pass


if __name__ == "__main__":
    unittest.main()
