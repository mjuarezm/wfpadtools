import json
import multiprocessing
from os import listdir
from os.path import join, isfile, exists
import pickle
from sets import Set
import socket
from time import sleep
import time
import unittest

from obfsproxy.common import transport_config
import obfsproxy.common.log as logging
from obfsproxy.test import tester
from obfsproxy.test.tester import TransportsSetUp, TEST_FILE
from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut
from obfsproxy.transports.wfpadtools import wfpad
from obfsproxy.transports.wfpadtools import wfpad_shim
from obfsproxy.transports.wfpadtools.message import getOpcodeNames


# DEBUG = True
DEBUG = True

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')


class DummyReadWorker(object):

    @staticmethod
    def work(host, port):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(1)
        (conn, _) = listener.accept()
        listener.close()
        try:
            while True:
                conn.recv(4096)
        except Exception, e:
            print "Exception %s" % str(e)
        conn.close()

    def __init__(self, address):
        self.worker = multiprocessing.Process(target=self.work,
                                              args=(address))
        self.worker.start()

    def stop(self):
        if self.worker.is_alive():
            self.worker.terminate()


class TestSetUp(TransportsSetUp):

    def setUp(self):
        if exists(const.TEST_SERVER_DIR):
            ut.removedir(const.TEST_SERVER_DIR)
        ut.createdir(const.TEST_SERVER_DIR)
        super(TestSetUp, self).setUp()
        self.output_reader = DummyReadWorker(("127.0.0.1", tester.EXIT_PORT))
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
                                                    % self.transport,
                                                    report != "")
        report += self.obfs_server.check_completion("obfsproxy server (%s)"
                                                    % self.transport,
                                                    report != "")
        log.debug(report)

    def send_to_transport(self, data):
        self.input_chan.sendall(data)
        time.sleep(2)

    def load_wrapper(self):
        return sum([pickle.load(open(join(const.TEST_SERVER_DIR, f)))
                    for f in listdir(const.TEST_SERVER_DIR)
                    if isfile(join(const.TEST_SERVER_DIR, f))], [])


class ControlMessageCommunicationTest(TestSetUp):

    def send_instruction(self, opcode, args=None):
        """Send instruction to wfpadtest client."""
        instrMsg = "TEST:{};".format(str(opcode))
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
        log.debug("Test for " + getOpcodeNames(self.opcode) +
                  " with args: %s" % self.args)

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


class PostPrimitiveTest(ControlMessageCommunicationTest):

    def spectest_run(self):
        """Run tests that start with `posttest`."""
        self.send_instruction(const.OP_APP_HINT, [self.sessId, True])
        self.do_instructions()
        self.send_instruction(const.OP_APP_HINT, [self.sessId, False])
        self.postWrapper = self.load_wrapper()
        log.debug("Post wrapper: %s" % self.postWrapper)
        self.postClientDumps = [msg for msg in self.postWrapper
                                if msg['client']]
        self.postServerDumps = [msg for msg in self.postWrapper
                                if not msg['client']]
        specTests = [testMethod for testMethod in dir(self)
                     if testMethod.startswith('posttest')]
        for specTest in specTests:
            getattr(self, specTest)()


class SendPaddingTest(ControlMessageCommunicationTest, STTest):
    # Config endpoints
    transport = "wfpadtest"
    server_args = ("wfpadtest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("wfpadtest", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    # Arguments
    opcode = const.OP_SEND_PADDING
    N, t = 5, 1
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
        expectedDelay = self.t / const.SCALE
        for msg0, msg1 in zip(self.clientDumps[:-1], self.clientDumps[1:]):
            obsPeriod = msg1['time'] - msg0['time']
            self.assertAlmostEqual(obsPeriod, expectedDelay,
                                   msg="The observed delay %s does not"
                                   " match with the expected delay: %s"
                                   % (obsPeriod, expectedDelay),
                                   delta=0.005)


class AppHintTest(ControlMessageCommunicationTest, STTest):
    """Test server sends a hint to client."""
    # Config endpoints
    transport = "wfpadtest"
    server_args = ("wfpadtest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("wfpadtest", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    # Arguments    
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


class TotalPadTest(PostPrimitiveTest, STTest):
    # Config endpoints
    transport = "buflotest"
    server_args = ("buflotest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("buflotest", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    # Arguments    
    opcode = const.OP_TOTAL_PAD
    sessId, delay = "id123", 1
    args = [sessId, delay]

    def do_instructions(self):
        self.send_to_transport(TEST_FILE)

    def posttest_num_messages_is_power_of_2(self):
        clientPaddingMsgs = [msg for msg in self.postClientDumps
                             if msg['flags'] == const.FLAG_PADDING]
        obsNumMessages = len(clientPaddingMsgs)
        self.assertTrue((obsNumMessages & (obsNumMessages - 1)) == 0,
                        "The observed number of padding messages (%s) "
                        "is not a power of 2." % obsNumMessages)

    def posttest_period(self):
        clientPaddingMsgs = [msg for msg in self.postClientDumps
                             if msg['flags'] == const.FLAG_PADDING]
        for msg1, msg2 in zip(clientPaddingMsgs[:-1], clientPaddingMsgs[1:]):
            observedPeriod = msg2["time"] - msg1["time"]
            expectedPeriod = self.delay
            self.assertAlmostEqual(observedPeriod, expectedPeriod,
                                   msg="The observed period %s does not"
                                   " match with the expected period: %s"
                                   % (observedPeriod, expectedPeriod),
                                   delta=0.05)


class PayloadPadBytesTest(PostPrimitiveTest, STTest):
    # Config endpoints
    transport = "buflotest"
    server_args = ("buflotest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("buflotest", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    # Arguments
    opcode = const.OP_PAYLOAD_PAD
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]

    def do_instructions(self):
        self.send_to_transport(TEST_FILE)

    def posttest_num_data_bytes_correctly_padded(self):
        lastMessage = self.postServerDumps[-1]
        dataSentBytes = lastMessage['dataBytes']['rcv']
        totalSentBytes = lastMessage['totalBytes']['rcv']
        expectedNumBytes = ut.bytes_after_payload_padding(dataSentBytes,
                                                          totalSentBytes)
        self.assertEqual(expectedNumBytes, dataSentBytes,
                         "The observed number of bytes (%s) "
                         "does not match the expected (%s)."
                         % (dataSentBytes, expectedNumBytes))

    def posttest_period(self):
        pass


class BatchPadTest(PostPrimitiveTest, STTest):
    # Config endpoints
    transport = "buflotest"
    server_args = ("buflotest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("buflotest", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    # Arguments    
    opcode = const.OP_BATCH_PAD
    sessId, L, delay = "id123", 5, 1
    args = [sessId, L, delay]

    def do_instructions(self):
        self.send_to_transport(TEST_FILE)

    def posttest_num_messages_is_multiple_of_L(self):
        clientPaddingMsgs = [msg for msg in self.postClientDumps
                             if msg['flags'] == const.FLAG_PADDING]
        obsNumMessages = len(clientPaddingMsgs)
        self.assertTrue(obsNumMessages % self.L == 0,
                        "The observed number of padding messages (%s) "
                        "is not a multiple of %s."
                        % (obsNumMessages, self.L))

    def posttest_period(self):
        clientPaddingMsgs = [msg for msg in self.postClientDumps
                             if msg['flags'] == const.FLAG_PADDING]
        for msg1, msg2 in zip(clientPaddingMsgs[:-1], clientPaddingMsgs[1:]):
            observedPeriod = msg2["time"] - msg1["time"]
            expectedPeriod = self.delay
            self.assertAlmostEqual(observedPeriod, expectedPeriod,
                                   msg="The observed period %s does not"
                                   " match with the expected period: %s"
                                   % (observedPeriod, expectedPeriod),
                                   delta=0.05)


class ConstantRateRcvHistoTests(PostPrimitiveTest, STTest):
    # Config endpoints
    transport = "wfpadtest"
    server_args = ("wfpadtest", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT)
    client_args = ("wfpadtest", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT)

    # Arguments    
    sessId = 111
    opcode = const.OP_BURST_HISTO
    delay = 2
    tokens = 100000
    histo = [tokens, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    labels_ms = [0, delay, 4, 8, 16, 32, 64, 128, 256, 512, 1024,
                 2048, 4096, 8192, 16384, 32768, 65536, -1]
    removeTokens = True
    interpolate = False
    when = "rcv"
    args = [histo, labels_ms, removeTokens, interpolate, when]

    def do_instructions(self):
        self.send_instruction(const.OP_GAP_HISTO, [self.histo,
                                                   self.labels_ms,
                                                   self.removeTokens,
                                                   self.interpolate,
                                                   "rcv"])
        sleep(0.5)
        self.send_instruction(0)
        sleep(1)

    def posttest_period(self):
        clientPaddingMsgs = [msg for msg in self.postClientDumps
                             if msg['flags'] == const.FLAG_PADDING][0:10]
        for msg1, msg2 in zip(clientPaddingMsgs[:-1], clientPaddingMsgs[1:]):
            observedPeriod = msg2["time"] - msg1["time"]
            expectedPeriod = self.delay / const.SCALE
            self.assertAlmostEqual(observedPeriod, expectedPeriod,
                                   msg="The observed period %s does not"
                                   " match with the expected period: %s"
                                   % (observedPeriod, expectedPeriod),
                                   delta=0.005)


class WFPadShimObserver(STTest):

    def setUp(self):
        # Initialize transport object
        pt_config = transport_config.TransportConfig()
        pt_config.setListenerMode("server")
        pt_config.setObfsproxyMode("external")
        wfpad.WFPadClient.setup(pt_config)
        wfpadClient = wfpad.WFPadClient()

        # Create an instace of the shim
        self.shimObs = wfpad_shim.WFPadShimObserver(wfpadClient)

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

        self.assertTrue(self.shimObs._visiting,
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

        self.assertFalse(self.shimObs._visiting,
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

        self.assertTrue(self.shimObs._visiting,
                        "The session has not started."
                        "The wfpad's `_visiting` flag is `False`.")


if __name__ == "__main__":
    unittest.main()
