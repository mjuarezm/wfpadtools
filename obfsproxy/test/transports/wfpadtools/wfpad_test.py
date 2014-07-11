from obfsproxy.test import tester
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut
from obfsproxy.test.transports.wfpadtools.sttest import STTest
import obfsproxy.common.log as logging

import pickle
import unittest
from time import sleep
from os import listdir
from os.path import join, isfile


DEBUG = False

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')


class TestSetUp(object):

    def setUp(self):
        ut.createdir(const.TEST_SERVER_DIR)  # Create temp dir
        self.obfs_client = tester.Obfsproxy(self.client_args)
        sleep(0.2)
        self.input_chan = tester.connect_with_retry(("127.0.0.1",
                                                     tester.ENTRY_PORT))
        self.input_chan.settimeout(tester.SOCKET_TIMEOUT)

    def tearDown(self):
        self.obfs_client.stop()
        self.input_chan.close()
        ut.removedir(const.TEST_SERVER_DIR)  # Remove temp dir

    def send_data(self):
        self.input_chan.sendall(tester.TEST_FILE)
        sleep(5)
        self.input_chan.close()

    def load_wrappers(self):
        return [pickle.load(open(join(const.TEST_SERVER_DIR, f)))
                    for f in listdir(const.TEST_SERVER_DIR)
                        if isfile(join(const.TEST_SERVER_DIR, f))]


#@unittest.skip("")
class WFPadTests(TestSetUp, STTest):
    transport = "wfpad"

    def setUp(self):
        self.client_args = (
               "--test-server=%d" % tester.EXIT_PORT,
               "wfpad", "client",
               "127.0.0.1:%d" % tester.ENTRY_PORT,
               "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
               )
        super(WFPadTests, self).setUp()

    def tearDown(self):
        super(WFPadTests, self).tearDown()


class BuFLOTests(TestSetUp, STTest):
    transport = "buflo"
    period = 0.1
    psize = 1448
    mintime = 2
    client_args = (
           "--test-server=%s" % tester.EXIT_PORT,
           "buflo", "client",
           "127.0.0.1:%d" % tester.ENTRY_PORT,
           "--socks-shim=%d,%d" % (tester.SHIM_PORT, tester.SOCKS_PORT),
           "--period=%s" % period,
           "--psize=%s" % psize,
           "--mintime=%s" % mintime,
           "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def test_timing(self):
        self.send_data()
        for wrapper in self.load_wrappers():
            for obsIat in wrapper:
                print obsIat
                self.assertAlmostEqual(self.period, obsIat,
                                       None,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (obsIat, self.period),
                                       delta=0.05)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
