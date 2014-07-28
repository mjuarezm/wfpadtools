import obfsproxy.common.log as logging
from obfsproxy.test import tester
from obfsproxy.transports.wfpadtools import wfpad
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut
from obfsproxy.test.transports.wfpadtools.sttest import STTest

import json
import time
import pickle
import unittest
from sets import Set
from time import sleep
from os import listdir
from os.path import join, isfile, exists
from obfsproxy.common import transport_config
from obfsproxy.test.tester import TransportsSetUp

DEBUG = False

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')


class TestSetUp(TransportsSetUp):

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
        ut.removedir(const.TEST_SERVER_DIR)
        if DEBUG:
            self.print_output()

    def print_output(self):
        report = ""
        report += self.obfs_client.check_completion("obfsproxy client (%s)"
                                                % self.transport, report != "")
        report += self.obfs_server.check_completion("obfsproxy server (%s)"
                                                % self.transport, report != "")
        log.debug(report)

    def send_to_transport(self, data):
        self.input_chan.sendall(data)
        time.sleep(2)

    def load_wrapper(self):
        return sum([pickle.load(open(join(const.TEST_SERVER_DIR, f)))
                    for f in listdir(const.TEST_SERVER_DIR)
                        if isfile(join(const.TEST_SERVER_DIR, f))], [])


class ControlMessageCommunicationTest(TestSetUp):
    transport = "wfpadtest"
    server_args = ("wfpadtest", "server",
           "127.0.0.1:%d" % tester.SERVER_PORT,
           "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("wfpadtest", "client",
           "127.0.0.1:%d" % tester.ENTRY_PORT,
           "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def send_instruction(self, opcode, args=None):
        """Send instruction to wfpadtest client."""
        instrMsg = "TEST:{};".format(str(self.opcode))
        if args:
            instrMsg += json.dumps(args)
        self.send_to_transport(instrMsg)

    def specific_tests(self):
        """Run tests that start with `spectest`."""
        specTests = [testMethod for testMethod in dir(self)
                     if testMethod.startswith('spectest')]
        for specTest in specTests:
            getattr(self, specTest)()

    def test_control_msg_communication(self):
        """Test control messages communication."""
        # Send instruction to test server
        self.send_instruction(self.opcode, self.args)

        # Load wrapper
        self.wrapper = self.load_wrapper()
        log.debug("Messages in wrappers: %s" % self.wrapper)

        # Filter client and server messages
        self.serverDumps = [msg for msg in self.wrapper if not msg['client']]
        self.clientDumps = [msg for msg in self.wrapper if msg['client']]

        # Filter messages with `opcode`
        opcodeMsgs = [msg['opcode'] for msg in self.serverDumps
                      if msg['opcode'] == self.opcode]

        # Test the control message was received successfully
        self.assertTrue(opcodeMsgs, "Server did not receive the control "
                                    "message with opcode: %s" % self.opcode)

        # Run specific tests
        self.specific_tests()


@unittest.skip("Found error at closing socket in obfsproxy_tester.log."
               "We skip for now because this is not an important primitive.")
class SatartPaddingTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_START
    args = None


@unittest.skip("Not an important primitive. We may remove in the future.")
class StopPaddingTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_STOP
    args = None


class SendIgnoreTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_IGNORE
    args = None

    def spectest_padding_message(self):
        paddingMsgs = [msg for msg in self.clientDumps
                        if msg['flags'] == const.FLAG_PADDING]
        expNumPaddingMsgs = 1
        numPaddingMsgs = len(paddingMsgs)
        self.assertEquals(numPaddingMsgs, expNumPaddingMsgs,
                          "Observed number of padding msgs (%s)"
                          " does not match the expected one: %s"
                          % (numPaddingMsgs, expNumPaddingMsgs))


class SendPaddingTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_SEND_PADDING
    N, t = 5, 0.1
    args = [N, t]

    def spectest_n_padding_messages(self):
        paddingMsgs = [msg for msg in self.clientDumps
                        if msg['flags'] == const.FLAG_PADDING]
        expNumPaddingMsgs = self.N
        numPaddingMsgs = len(paddingMsgs)
        self.assertEquals(numPaddingMsgs, expNumPaddingMsgs,
                          "Observed number of padding msgs (%s)"
                          " does not match the expected one: %s"
                          % (numPaddingMsgs, expNumPaddingMsgs))

    def spectest_delay(self):
        controlMsg = self.serverDumps[0]
        firstPaddingMsg = sorted(self.clientDumps,
                                 key=lambda x: x['time'])[0]
        expectedDelay = self.t
        observedDelay = firstPaddingMsg['time'] - controlMsg['time']
        self.assertAlmostEqual(observedDelay, expectedDelay,
                               msg="The expected delay %s does not"
                               " match with the expected delay: %s"
                               % (observedDelay, expectedDelay),
                               delta=0.05)


class AppHintTest(ControlMessageCommunicationTest, STTest):
    """Test server sends a hint to client."""
    opcode = const.OP_APP_HINT
    sessId,  status = "id123", True
    args = [sessId, status]
    tag = True

    def spectest_num_msgs(self):
        self.assertEquals(len(self.serverDumps), 1,
                          "Number of tagged messages (%s) is not correct."
                          % (len(self.serverDumps)))

    def spectest_sessid(self):
        firstServerDumpMsg = self.serverDumps[0]
        self.assertEquals(firstServerDumpMsg['sessid'], self.sessId,
                          "The server's session Id (%s) does not match "
                          "the session Id indicated in the hint (%s)."
                          % (firstServerDumpMsg['sessid'], self.sessId))

    def spectest_state(self):
        firstServerDumpMsg = self.serverDumps[0]
        self.assertEquals(firstServerDumpMsg['visiting'], self.status,
                          "The server's state (%s) does not match "
                          "the status indicated in the hint (%s)."
                          % (firstServerDumpMsg['visiting'], self.status))


class BurstHistoTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_BURST_HISTO
    histo, labels_ms, removeTokens = range(200), range(200), False
    args = [histo, labels_ms, removeTokens]



class GapHistoTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_GAP_HISTO
    histo, labels_ms, removeTokens = range(3), range(3), False
    args = [histo, labels_ms, removeTokens]


class InjectHistoTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_INJECT_HISTO
    histo, labels_ms = range(3), range(3)
    args = [histo, labels_ms]


class TotalPadTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_TOTAL_PAD
    sessId, K, delay = "id123", 4, 1
    args = [sessId, K, delay]


class PayloadPadTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_PAYLOAD_PAD
    args = None


class BatchPadTest(ControlMessageCommunicationTest, STTest):
    opcode = const.OP_BATCH_PAD
    sessId, L, delay = "id123", 3, 1
    args = [sessId, L, delay]


@unittest.skip("")
class ExternalBuFLOTests(TestSetUp, STTest):
    transport = "buflo"
    period = 1
    psize = 1448
    mintime = 2
    server_args = ("dummytest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (tester.SHIM_PORT,
                                           tester.TESTSHIM_PORT),
                   "--period=%d" % period,
                   "--psize=%d" % psize,
                   "--mintime=%d" % mintime,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    def setUp(self):
        super(ExternalBuFLOTests, self).setUp()
        # Make request to shim
        self.shim_chan = tester.connect_with_retry(("127.0.0.1",
                                                    tester.SHIM_PORT))
        self.shim_chan.settimeout(tester.SOCKET_TIMEOUT)
        sleep(2)

    def tearDown(self):
        self.shim_chan.close()
        super(ExternalBuFLOTests, self).tearDown()

    def test_timing(self):
        super(ExternalBuFLOTests, self).direct_transfer()
        for wrapper in self.load_wrapper():
            if len(wrapper) > 2:
                iats = [wrapper[i + 1][1] - wrapper[i][1]
                            for i in range(len(wrapper[1:]))]
                for obsIat in iats:
                    self.assertAlmostEqual(self.period, obsIat,
                                       None,
                                       "The observed period %s does not match"
                                       " with the expected period %s"
                                       % (obsIat, self.period),
                                       delta=0.05)

    def test_sizes(self):
        super(ExternalBuFLOTests, self).direct_transfer()
        for wrapper in self.load_wrapper():
            print wrapper
            for length, iat in wrapper:
                print length, iat
                self.assertEqual(self.psize, length,
                                       "The observed size %s does not match"
                                       " with the expected size %s"
                                       % (length, self.psize))

    @unittest.skip("")
    def test_pad_when_visiting(self):
        wrapper = self.load_wrapper()
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


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
