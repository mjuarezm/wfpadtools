from os import listdir
from os.path import join, isfile
import pickle
import time
import unittest

import obfsproxy.common.log as logging
from obfsproxy.test import tester
from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut
from obfsproxy.test.transports.wfpadtools.webfp_tests import BuFLOTorTest

DEBUG = False

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')


class TransportsSetUpTest(object):
    def setUp(self):
        self.obfs_client = tester.Obfsproxy(self.client_args)

    def tearDown(self):
        self.obfs_client.stop()


class TestSetUp(TransportsSetUpTest):

    def setUp(self):
        super(TestSetUp, self).setUp()
        self.output_reader = tester.ReadWorker(("127.0.0.1",
                                                tester.EXIT_PORT))
        ut.createdir(const.TEST_SERVER_DIR)  # Create temp dir
        self.input_chan = tester.connect_with_retry(("127.0.0.1",
                                                    tester.ENTRY_PORT))
        self.input_chan.settimeout(tester.SOCKET_TIMEOUT)

    def tearDown(self):
        super(TestSetUp, self).tearDown()
        self.output_reader.stop()
        self.input_chan.close()
        ut.removedir(const.TEST_SERVER_DIR)  # Remove temp dir

    def direct_transfer(self):
        self.input_chan.sendall(tester.TEST_FILE)
        time.sleep(2)
        self.input_chan.close()

    def load_wrappers(self):
        return [pickle.load(open(join(const.TEST_SERVER_DIR, f)))
                    for f in listdir(const.TEST_SERVER_DIR)
                        if isfile(join(const.TEST_SERVER_DIR, f))]


@unittest.skip("")
class WFPadTests(TestSetUp, unittest.TestCase):
    transport = "wfpad"
    period = 0.1
    psize = 1448
    client_args = ("--test-server=127.0.0.1:%d" % tester.EXIT_PORT,
                   "wfpad", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def test_timing(self):
        super(WFPadTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            for _, obsIat in wrapper:
                print obsIat
                self.assertAlmostEqual(self.period, obsIat,
                                       None,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (obsIat, self.period),
                                       delta=0.05)

    def test_sizes(self):
        super(WFPadTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            for obsLength, _ in wrapper:
                print obsLength
                self.assertEqual(self.psize, obsLength,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (obsLength, self.psize))


#@unittest.skip("")
class BuFLOTests(TestSetUp, STTest):
    transport = "buflo"
    period = 0.1
    psize = 1448
    mintime = 2
    client_args = ("--test-server=127.0.0.1:%d" % tester.EXIT_PORT,
                   "buflo", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (tester.SHIM_PORT,
                                           tester.SOCKS_PORT),
                   "--period=%d" % period,
                   "--psize=%d" % psize,
                   "--mintime=%d" % mintime,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def test_timing(self):
        super(BuFLOTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            for _, obsIat in wrapper:
                self.assertAlmostEqual(self.period, obsIat,
                                       None,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (obsIat, self.period),
                                       delta=0.05)

    def test_sizes(self):
        super(BuFLOTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            for length, iat in wrapper:
                print length, iat
                self.assertEqual(self.psize, length,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (length, self.psize))

    def test_pad_when_visiting(self):
        ut.get_page(url="http://127.0.0.1", port=tester.SHIM_PORT)
#         shim_chan = tester.connect_with_retry(("127.0.0.1",
#                                                     tester.SHIM_PORT))
#         shim_chan.settimeout(tester.SOCKET_TIMEOUT)
        wrapper = self.load_wrappers()
        self.test_sizes()
        self.assertTrue(wrapper, "The number of messages received is not"
                        "sufficient: %d messages" % len(wrapper))
#         shim_chan.close()

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
