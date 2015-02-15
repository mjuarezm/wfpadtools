import json
from os.path import join, exists
from time import sleep
import time
import unittest

# WFPadTools imports
import obfsproxy.common.log as logging
from obfsproxy.test import tester
from obfsproxy.transports.wfpadtools import const, wfpad
from obfsproxy.transports.wfpadtools.util import testutil as tu
from obfsproxy.transports.wfpadtools.util import fileutil as fu
from obfsproxy.transports.wfpadtools.util import dumputil as du
from obfsproxy.transports.wfpadtools.message import getOpcodeNames


# DEBUG = True
DEBUG = True

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')

DUMPS = {"client": join(const.TEST_DUMP_DIR, "client.dump"),
         "server": join(const.TEST_DUMP_DIR, "server.dump")}

TEST_MSG = "foobar"


class TestSetUp(tester.TransportsSetUp):

    def setUp(self):
        if exists(const.TEST_DUMP_DIR):
            fu.removedir(const.TEST_DUMP_DIR)
        fu.createdir(const.TEST_DUMP_DIR)
        super(TestSetUp, self).setUp()
        self.output_reader = tu.DummyReadWorker(("127.0.0.1",
                                                 tester.EXIT_PORT))
        sleep(1.0)
        self.input_chan = tester.connect_with_retry(("127.0.0.1",
                                                     tester.ENTRY_PORT))
        self.input_chan.settimeout(tester.SOCKET_TIMEOUT)

    def tearDown(self):
        super(TestSetUp, self).tearDown()
        self.output_reader.stop()
        self.input_chan.close()
        fu.removedir(const.TEST_DUMP_DIR)
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

    def messages(self, d):
        return sum([elem[1] for elem in d.itervalues()], [])

    def states(self, d):
        return [elem[0] for elem in d.itervalues()]

    def test_control_msg_communication(self):
        """Test control messages communication."""
        # Send instruction to test server
        self.send_instruction(self.opcode, self.args)
        log.debug("Test for " + getOpcodeNames(self.opcode) +
                  " with args: %s" % self.args)

        # Load dumps
        self.serverDumps = self.load_wrapper("server")
        self.clientDumps = self.load_wrapper("client")

        # Filter messages with `opcode`
        opcodeMsgs = [msg.opcode for msg in self.messages(self.serverDumps)
                      if msg.opcode == self.opcode]

        # Test the control message was received successfully
        self.assertTrue(opcodeMsgs, "Server did not receive the control "
                                    "message with opcode: %s" % self.opcode)

        # Run specific tests
        self.specific_tests()

    def load_wrapper(self, end):
        try:
            return du.pick_load(DUMPS[end])
        except:
            # TODO: find the right exception
            return {}


class PostPrimitiveTest(ControlMessageCommunicationTest):

    def spectest_run(self):
        """Run tests that start with `posttest`."""
        self.send_instruction(const.OP_APP_HINT, [self.sessId, True])
        self.do_instructions()
        self.send_instruction(const.OP_APP_HINT, [self.sessId, False])
        # Load dumps
        self.postServerDumps = self.load_wrapper("server")
        self.postClientDumps = self.load_wrapper("client")
        specTests = [testMethod for testMethod in dir(self)
                     if testMethod.startswith('posttest')]
        for specTest in specTests:
            getattr(self, specTest)()


class SendPaddingTest(ControlMessageCommunicationTest, tu.STTest):
    # Config endpoints
    transport = "wfpad"
    server_args = ("wfpad", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT,
                   "--test=%s" % DUMPS["server"])
    client_args = ("wfpad", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
                   "--test=%s" % DUMPS["client"])

    # Arguments
    opcode = const.OP_SEND_PADDING
    N, t = 5, 1
    args = [N, t]

    def spectest_n_padding_messages(self):
        msgs = self.messages(self.clientDumps)
        paddingMsgs = [msg for msg in msgs if msg.flags == const.FLAG_PADDING]
        expNumPaddingMsgs = self.N
        numPaddingMsgs = len(paddingMsgs)
        self.assertEquals(numPaddingMsgs, expNumPaddingMsgs,
                          "Observed number of padding msgs (%s)"
                          " does not match the expected one: %s"
                          % (numPaddingMsgs, expNumPaddingMsgs))

    def spectest_delay(self):
        msgs = self.messages(self.clientDumps)
        expectedDelay = self.t / const.SCALE
        for msg0, msg1 in zip(msgs[:-1], msgs[1:]):
            obsPeriod = msg1.rcvTime - msg0.rcvTime
            self.assertAlmostEqual(obsPeriod, expectedDelay,
                                   msg="The observed delay %s does not"
                                   " match with the expected delay: %s"
                                   % (obsPeriod, expectedDelay),
                                   delta=0.005)


class AppHintTest(ControlMessageCommunicationTest, tu.STTest):
    """Test server sends a hint to client."""
    # Config endpoints
    transport = "wfpad"
    server_args = ("wfpad", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT,
                   "--test=%s" % DUMPS["server"])
    client_args = ("wfpad", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
                   "--test=%s" % DUMPS["client"])

    # Arguments
    opcode = const.OP_APP_HINT
    sessId,  status = "id123", True
    args = [sessId, status]
    tag = True

    def spectest_num_msgs(self):
        self.assertEquals(len(self.messages(self.serverDumps)), 1,
                          "Number of tagged messages (%s) is not correct."
                          % (len(self.serverDumps)))

    def spectest_sessid(self):
        firstServerState = self.states(self.serverDumps)[0]
        self.assertEquals(firstServerState['_sessId'], self.sessId,
                          "The server's session Id (%s) does not match "
                          "the session Id indicated in the hint (%s)."
                          % (firstServerState['_sessId'], self.sessId))

    def spectest_state(self):
        firstServerState = self.states(self.serverDumps)[0]
        self.assertEquals(firstServerState['_visiting'], self.status,
                          "The server's state (%s) does not match "
                          "the status indicated in the hint (%s)."
                          % (firstServerState['_visiting'], self.status))


class TotalPadTest(PostPrimitiveTest, tu.STTest):
    # Config endpoints
    transport = "buflo"
    server_args = ("buflo", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT,
                   "--test=%s" % DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
                   "--test=%s" % DUMPS["client"])

    # Arguments
    opcode = const.OP_TOTAL_PAD
    sessId, delay = "id123", 1
    args = [sessId, delay]

    def do_instructions(self):
        self.send_to_transport(tester.TEST_FILE)

    def posttest_num_messages_is_power_of_2(self):
        clientPaddingMsgs = [msg for msg in self.messages(self.postClientDumps)
                             if msg.flags & const.FLAG_PADDING]
        obsNumMessages = len(clientPaddingMsgs)
        self.assertTrue((obsNumMessages & (obsNumMessages - 1)) == 0,
                        "The observed number of padding messages (%s) "
                        "is not a power of 2." % obsNumMessages)

    def posttest_period(self):
        clientPaddingMsgs = [msg for msg in self.messages(self.postClientDumps)
                             if msg.flags & const.FLAG_PADDING]
        for msg1, msg2 in zip(clientPaddingMsgs[:-1], clientPaddingMsgs[1:]):
            observedPeriod = msg2.rcvTime - msg1.rcvTime
            expectedPeriod = self.delay
            self.assertAlmostEqual(observedPeriod, expectedPeriod,
                                   msg="The observed period %s does not"
                                   " match with the expected period: %s"
                                   % (observedPeriod, expectedPeriod),
                                   delta=0.05)


class PayloadPadBytesTest(PostPrimitiveTest, tu.STTest):
    # Config endpoints
    transport = "buflo"
    server_args = ("buflo", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT,
                   "--test=%s" % DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
                   "--test=%s" % DUMPS["client"])

    # Arguments
    opcode = const.OP_PAYLOAD_PAD
    sessId, delay, msg_level = "id123", 1, False
    args = [sessId, delay, msg_level]

    def do_instructions(self):
        self.send_to_transport(TEST_MSG)

    def posttest_num_data_bytes_correctly_padded(self):
        lastState = self.states(self.postServerDumps)[-1]
        dataSentBytes = lastState['_dataBytes']['rcv']
        totalSentBytes = lastState['_totalBytes']['rcv']
        expectedNumBytes = wfpad.bytes_after_payload_padding(dataSentBytes,
                                                             totalSentBytes)
        self.assertEqual(expectedNumBytes, dataSentBytes,
                         "The observed number of bytes (%s) "
                         "does not match the expected (%s)."
                         % (dataSentBytes, expectedNumBytes))

    def posttest_period(self):
        pass


class BatchPadTest(PostPrimitiveTest, tu.STTest):
    # Config endpoints
    transport = "buflo"
    server_args = ("buflo", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT,
                   "--test=%s" % DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
                   "--test=%s" % DUMPS["client"])

    # Arguments
    opcode = const.OP_BATCH_PAD
    sessId, L, delay = "id123", 5, 1
    args = [sessId, L, delay]

    def do_instructions(self):
        #self.send_to_transport(tester.TEST_FILE)
        pass

    def posttest_num_messages_is_multiple_of_L(self):
        clientPaddingMsgs = [msg for msg in self.messages(self.postClientDumps)
                             if msg.flags & const.FLAG_PADDING]
        obsNumMessages = len(clientPaddingMsgs)
        self.assertTrue(obsNumMessages % self.L == 0,
                        "The observed number of padding messages (%s) "
                        "is not a multiple of %s."
                        % (obsNumMessages, self.L))

    def posttest_period(self):
        clientPaddingMsgs = [msg for msg in self.messages(self.postClientDumps)
                             if msg.flags & const.FLAG_PADDING]
        for msg1, msg2 in zip(clientPaddingMsgs[:-1], clientPaddingMsgs[1:]):
            observedPeriod = msg2.rcvTime - msg1.rcvTime
            expectedPeriod = self.delay
            self.assertAlmostEqual(observedPeriod, expectedPeriod,
                                   msg="The observed period %s does not"
                                   " match with the expected period: %s"
                                   % (observedPeriod, expectedPeriod),
                                   delta=0.05)


class ConstantRateRcvHistoTests(PostPrimitiveTest, tu.STTest):
    # Config endpoints
    transport = "wfpad"
    server_args = ("wfpad", "server",
                   "127.0.0.1:%d" % tester.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % tester.EXIT_PORT,
                   "--test=%s" % DUMPS["server"])
    client_args = ("wfpad", "client",
                   "127.0.0.1:%d" % tester.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % tester.SERVER_PORT,
                   "--test=%s" % DUMPS["client"])

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
        clientPaddingMsgs = [msg for msg in self.messages(self.postClientDumps)
                             if msg.flags & const.FLAG_PADDING][0:10]
        for msg1, msg2 in zip(clientPaddingMsgs[:-1], clientPaddingMsgs[1:]):
            observedPeriod = msg2.rcvTime - msg1.rcvTime
            expectedPeriod = self.delay / const.SCALE
            self.assertAlmostEqual(observedPeriod, expectedPeriod,
                                   msg="The observed period %s does not"
                                   " match with the expected period: %s"
                                   % (observedPeriod, expectedPeriod),
                                   delta=0.005)


if __name__ == "__main__":
    unittest.main()
