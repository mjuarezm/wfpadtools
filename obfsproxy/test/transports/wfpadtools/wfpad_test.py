import obfsproxy.common.log as logging
from obfsproxy.test import tester
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut
from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import wfpad

import time
import pickle
import unittest
from sets import Set
from os import listdir
from os.path import join, isfile, exists
from obfsproxy.common import transport_config

DEBUG = True

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
        if exists(const.TEST_SERVER_DIR):
            ut.removedir(const.TEST_SERVER_DIR)
        ut.createdir(const.TEST_SERVER_DIR)
        super(TestSetUp, self).setUp()
        self.output_reader = tester.ReadWorker(("127.0.0.1", tester.EXIT_PORT))
        self.input_chan = tester.connect_with_retry(("127.0.0.1",
                                                     tester.ENTRY_PORT))
        self.input_chan.settimeout(tester.SOCKET_TIMEOUT)

    def tearDown(self):
        self.output_reader.stop()
        self.input_chan.close()
        super(TestSetUp, self).tearDown()
        #ut.removedir(const.TEST_SERVER_DIR)

    def direct_transfer(self):
        self.input_chan.sendall(tester.TEST_FILE)
        time.sleep(2)
        self.input_chan.close()

    def load_wrappers(self):
        return [pickle.load(open(join(const.TEST_SERVER_DIR, f)))
                    for f in listdir(const.TEST_SERVER_DIR)
                        if isfile(join(const.TEST_SERVER_DIR, f))]


#@unittest.skip("")
class WFPadTests(TestSetUp, unittest.TestCase):
    transport = "wfpad"
    period = 0.1
    psize = 1448
    client_args = ("--test-server=wfpadtest,127.0.0.1:%d" % tester.EXIT_PORT,
                   "wfpad", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def test_timing(self):
        super(WFPadTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            print wrapper
            for _, obsIat in wrapper:
                print obsIat
                self.assertAlmostEqual(self.period,
                                       obsIat,
                                       None,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (obsIat, self.period),
                                       delta=0.05)

    def test_sizes(self):
        super(WFPadTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            print wrapper
            for obsLength, _ in wrapper:
                print obsLength
                self.assertEqual(self.psize,
                                 obsLength,
                                 "The observed size %s does not match"
                                 " with the expected size %s"
                                 % (obsLength, self.psize))


@unittest.skip("")
class BuFLOTests(TestSetUp, STTest):
    transport = "buflo"
    period = 1
    psize = 1448
    mintime = 2
    client_args = ("--test-server=wfpadtest,127.0.0.1:%d" % tester.EXIT_PORT,
                   "buflo", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (tester.SHIM_PORT,
                                           tester.TESTSHIM_PORT),
                   "--period=%d" % period,
                   "--psize=%d" % psize,
                   "--mintime=%d" % mintime,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def setUp(self):
        super(BuFLOTests, self).setUp()
        # Make request to shim
        self.shim_chan = tester.connect_with_retry(("127.0.0.1",
                                                    tester.SHIM_PORT))
        self.shim_chan.settimeout(tester.SOCKET_TIMEOUT)

    def tearDown(self):
        self.shim_chan.close()
        super(BuFLOTests, self).tearDown()

    def test_timing(self):
        super(BuFLOTests, self).direct_transfer()
        for wrapper in self.load_wrappers():
            print wrapper
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
            print wrapper
            for length, iat in wrapper:
                print length, iat
                self.assertEqual(self.psize, length,
                                       "The observed size %s does not match"
                                       " with the expected size %s"
                                       % (length, self.psize))

    #@unittest.skip("")
    def test_pad_when_visiting(self):
        wrapper = self.load_wrappers()
        self.test_sizes()
        self.assertTrue(wrapper, "The number of messages received is not"
                        "sufficient: %d messages" % len(wrapper))


class WFPadShimObserver(STTest):

    def setUp(self):
        # Initialize transport object
        pt_config = transport_config.TransportConfig()
        pt_config.setListenerMode("server")
        pt_config.setObfsproxyMode("external")
        wfpad.WFPadClient.setup(pt_config)
        wfpadClient = wfpad.WFPadClient()

        # Create an instace of the shim
        self.shimObs = wfpad.WFPadShimObserver(wfpadClient)

        # Open a few connections
        self.shimObs.onConnect(1)
        self.shimObs.onConnect(2)
        self.shimObs.onConnect(3)

    def test_opening_connections(self):
        """Test opening new connections.

        If the observer is notified of a new open connection,
        test that the connection is added to the data structure
        and make sure session has started.
        Also test adding the same connection twice.
        """
        self.shimObs.onConnect(1)

        obsSessions = self.shimObs._sessions
        expSessions = {1: Set([1, 2, 3])}

        self.assertDictEqual(obsSessions, expSessions,
                            "Observed sessions %s do not match"
                            " with expected sessions %s."
                            % (obsSessions, expSessions))

        self.assertTrue(self.shimObs.wfpad._visiting,
                         "The session has not started."
                         "The wfpad's `_visiting` flag is `False`.")

    def test_closing_connections(self):
        """Test closing connections.

        If the observer is notified of a connection being closed,
        test that connections are removed from data structure correctly.
        Also test removing the same connection twice.
        """
        self.shimObs.onDisconnect(1)
        self.shimObs.onDisconnect(1)

        obsSessions = self.shimObs._sessions
        expSessions = {1: Set([2, 3])}

        self.assertDictEqual(obsSessions, expSessions,
                            "Observed sessions %s do not match"
                            " with expected sessions %s."
                            % (obsSessions, expSessions))

    def test_edge_cases(self):
        """Test the data structure is working properly in the edge cases.

        When the last connection is removed from data structure, make sure
        the session ends. Also, test removing a connection that is not in
        the data structure.
        """
        self.shimObs.onDisconnect(1)
        self.shimObs.onDisconnect(2)
        self.shimObs.onDisconnect(14)
        self.shimObs.onDisconnect(3)

        obsSessions = self.shimObs._sessions
        expSessions = {}

        self.assertDictEqual(obsSessions, expSessions,
                            "Observed sessions %s do not match"
                            " with expected sessions %s."
                            % (obsSessions, expSessions))

        self.assertFalse(self.shimObs.wfpad._visiting,
                         "The session has not ended."
                         "The wfpad's `_visiting` flag is `True`.")

    def test_after_removing_all_sessions(self):
        """Test session counter for new sessions.

        After removing all connections, when a new connection is started,
        the session id must be incremented. Also, test removing connection
        when data structure is empty.
        """
        self.shimObs.onDisconnect(1)
        self.shimObs.onDisconnect(2)
        self.shimObs.onDisconnect(3)
        self.shimObs.onConnect(1)

        obsSessions = self.shimObs._sessions
        expSessions = {2: Set([1])}

        self.assertDictEqual(obsSessions, expSessions,
                    "Observed sessions %s do not match"
                    " with expected sessions %s."
                    % (obsSessions, expSessions))

        self.assertTrue(self.shimObs.wfpad._visiting,
                         "The session has not started."
                         "The wfpad's `_visiting` flag is `False`.")


#@unittest.skip("")
class WFPadControlMessagesTest(STTest):

    def setUp(self):
        pass

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
