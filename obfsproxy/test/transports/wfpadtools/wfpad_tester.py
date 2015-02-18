"""Provide methods and classes to be used in tests for wfpad transports."""
import os
import unittest
from time import sleep

# WFPadTools imports
from obfsproxy.test import tester
import obfsproxy.common.log as logging
from obfsproxy.test import tester as ts
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import netutil as nu
from obfsproxy.transports.wfpadtools.util import fileutil as fu
from obfsproxy.transports.wfpadtools.util import dumputil as du
from obfsproxy.transports.wfpadtools.message import getOpcodeNames


DEBUG = os.environ["WFPAD_DEBUG"] if "WFPAD_DEBUG" in os.environ else False
# DEBUG = False

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')

TEST_MSG = "thisisatestmsg"

# Constants
SHIM_PORT = 6665
SOCKS_PORT = 6666


# CONFIGURATIONS
#############################################
class WFPadDirectConfig(object):
    transport = "wfpad"
    server_args = ("wfpad", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("wfpad", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class BuFLODirectConfig(object):
    transport = "buflo"
    server_args = ("buflo", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class WFPadShimConfig(WFPadDirectConfig):
    client_args = ("wfpad", "client",
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class BuFLOShimConfig(BuFLODirectConfig, object):
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class CSBuFLOShimConfig(object):
    transport = "csbuflo"
    server_args = ("csbuflo", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class AdaptiveShimConfig(object):
    transport = "adaptive"
    server_args = ("adaptive", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=0",
                   "--psize=%s" % const.MPU,
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("adaptive", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "--period=0",
                   "--psize=%s" % const.MPU,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class TamarawShimConfig(object):
    transport = "tamaraw"
    server_args = ("tamaraw", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--batch=1000",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("tamaraw", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--batch=1000",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


# CONFIGURATION WITH SOCKS
class WFPadShimSocksConfig(WFPadShimConfig):
    client_args = ("wfpad", "socks",
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)
    entry_port = SHIM_PORT


class BuFLOShimSocksConfig(BuFLOShimConfig, object):
    client_args = ("buflo", "socks",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "--period=1",
                   "--psize=%s" % const.MPU,
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)
    entry_port = SHIM_PORT


# DIRECT TESTS
#############################################
class DirectWFPad(WFPadDirectConfig, ts.DirectTest, unittest.TestCase):
    pass


class DirectBuFLO(BuFLODirectConfig, ts.DirectTest, unittest.TestCase):
    pass


# SHIM TESTS
#############################################
class ShimTest(ts.DirectTest):
        """Extends DirectTest to create an instance of the shim.

        It will connect/disconnect to the shim to flag start/end
        of sessions.
        """
        def setUp(self):
            super(ShimTest, self).setUp()
            self.shim_chan = ts.connect_with_retry(("127.0.0.1", SHIM_PORT))
            self.shim_chan.settimeout(ts.SOCKET_TIMEOUT)

        def tearDown(self):
            self.shim_chan.close()
            super(ShimTest, self).tearDown()


# TESTS WITH THE SHIM
#############################################
class ShimWFPad(WFPadShimConfig, ShimTest, unittest.TestCase):
    pass


class ShimBuFLO(BuFLOShimConfig, ShimTest, unittest.TestCase):
    pass


class ShimCSBuFLO(CSBuFLOShimConfig, ShimTest, unittest.TestCase):
    pass


class ShimAdaptive(AdaptiveShimConfig, ShimTest, unittest.TestCase):
    pass


class ShimTamaraw(TamarawShimConfig, ShimTest, unittest.TestCase):
    pass


# CLASSES TO TEST BIDIRECTIONAL COMMUNICATION
#############################################
class SetUpTest(nu.CommInterfaceAbstract):
    """Implement the CommInterfaceAbstract as a test class.

    The setUp method sets the bidirectional communication (obfsproxy (with
    shim) and dummy endpoints. The tearDown method closes communication
    and still-alive processes.
    """
    ENTRY_PORT = tester.ENTRY_PORT
    EXIT_PORT = tester.EXIT_PORT
    SHIM_PORTS = [SHIM_PORT, SOCKS_PORT]

    def setUp(self):
        fu.resetdir(const.TEMP_DIR)
        os.chdir(const.BASE_DIR)
        log.debug("\n\n\n\n")
        fu.resetdir(const.TEST_DUMP_DIR)
        self.setup()

    def tearDown(self):
        self.close()


class PrimitiveTest(SetUpTest):

    DATA_STR = "pad!"
    LEN_DATA_STR = len(DATA_STR)

    BEFORE_SESSION_TIME = 1
    DURING_SESSION_TIME = 1
    AFTER_SESSION_TIME = 1
    BEFORE_SESSION_END_TIME = 1

    def setUp(self):
        SetUpTest.setUp(self)
        self.doBeforeSessionStarts()
        sleep(self.BEFORE_SESSION_TIME)

        log.debug("Flag beginning of session.")
        self.start_session()
        self.doWhileSession()
        sleep(self.DURING_SESSION_TIME)

        log.debug("Flag end of session.")
        self.end_session()
        sleep(self.BEFORE_SESSION_END_TIME)
        self.doAfterSessionEnds()
        sleep(self.AFTER_SESSION_TIME)

        log.debug("Parse dumps.")
        self.parseDumps()

    def parseDumps(self):
        """Parse test dumps."""
        # Load dumps
        sleep(1)
        self.serverDumps = self.__load_wrapper("server")
        log.debug("Server Dumps: %s", self.serverDumps)
        self.clientDumps = self.__load_wrapper("client")
        log.debug("Client Dumps: %s", self.clientDumps)

        # Parse messages
        self.clientMsgs = self.__messages(self.clientDumps)
        self.serverMsgs = self.__messages(self.serverDumps)

        # States
        self.clientStates = self.__states(self.clientDumps)
        self.serverStates = self.__states(self.serverDumps)
        self.clientState = self.__last_state(self.clientDumps)
        self.serverState = self.__last_state(self.serverDumps)

    def get_index_msg(self, message, msgs):
        for i, msg in enumerate(msgs):
            if message == msg:
                return i
        return None

    def get_state(self, message, dump):
        for state, messages in dump:
            if message in messages:
                return state
        return None

    @staticmethod
    def control_msgs(msgs):
        """Return control messages."""
        return [msg for msg in msgs if msg.opcode]

    @staticmethod
    def payload_msgs(msgs):
        """Return messages with payload (either data or padding)."""
        return [msg for msg in msgs if not msg.opcode]

    @staticmethod
    def data_msgs(msgs):
        """Return padding messages."""
        return [msg for msg in msgs if msg.flags & const.FLAG_DATA]

    @staticmethod
    def padding_msgs(msgs):
        """Return padding messages."""
        return [msg for msg in msgs if msg.flags & const.FLAG_PADDING]

    def __last_state(self, dump):
        """Return last state from dump."""
        states = self.__states(dump)
        if states:
            return states[-1]
        return None

    def __messages(self, dump):
        """Return messages from dump.

        `dump` is a dictionary, and messages are always in the second
        element of the value (a tuple).
        """
        return sum([elem[1] for elem in dump], [])

    def __states(self, dump):
        """Return states from dump.

        First value element of dump (a dict) is another dictionary with
        all the pickable attributes of the transport (either client or
        server) class.
        """
        return [elem[0] for elem in dump]

    def __load_wrapper(self, end):
        """Attempts to load a dump of an endpoint from a file."""
        max_retries = 10
        for _ in xrange(max_retries):
            try:
                return du.pick_load(const.DUMPS[end])
            except:
                continue
        return []

    def doBeforeSessionStarts(self):
        """Template method to be implemented in specific tests."""
        pass

    def doWhileSession(self):
        """Template method to be implemented in specific tests."""
        pass

    def doAfterSessionEnds(self):
        """Template method to be implemented in specific tests."""
        pass


class HistoPrimitiveTest(PrimitiveTest):

    DURING_SESSION_TIME = 5
    BEFORE_SESSION_END_TIME = 1

    def doBeforeSessionStarts(self):
        self.send_instruction(self.opcode, self.args)

    def doWhileSession(self):
        self.send_to_server(self.DATA_STR)


class PadPrimitiveTest(PrimitiveTest):

    DURING_SESSION_TIME = 0
    BEFORE_SESSION_END_TIME = 1

    def doBeforeSessionStarts(self):
        self.send_instruction(const.OP_SEND_PADDING, [self.junk_msgs, 0])
        for _ in xrange(self.real_msgs):
            self.send_to_server(self.DATA_STR)

    def doWhileSession(self):
        self.send_instruction(self.opcode, self.args)

    def doAfterSessionEnds(self):
        self.send_to_server(self.DATA_STR)

    def total_pad(self):
        pass

    def get_units(self, x):
        return x * self.units

    def data_msgs(self):
        return self.real_msgs

    def total_msgs(self):
        return self.data_msgs() + self.junk_msgs

    def test_padding(self):
        total_pad = self.total_pad()
        observed_padding = self.get_units(len(self.clientMsgs))
        self.assertTrue(observed_padding > 0 and observed_padding >= total_pad
                        and observed_padding - self.get_units(1) < total_pad,
                        "The observed padding (%s) does not satisfy "
                        "the stop condition (%s)." % (observed_padding,
                                                      total_pad))


class SendControlMessageTest(PrimitiveTest):

    def doBeforeSessionStarts(self):
        """Send control msg."""
        log.debug("Sending to client the control instruction"
                  " for control msg: %s", getOpcodeNames(self.opcode))
        self.send_instruction(self.opcode, self.args)


class SendDataServerTest(SendControlMessageTest):

    def doWhileSession(self):
        """Send file to server."""
        log.debug("Sending data to server: %s", TEST_MSG)
        self.send_to_server(TEST_MSG)


class ControlMessagesTest(WFPadShimConfig, SendControlMessageTest):

    def test_control_is_received_successfully(self):
        # Test opcode of the sent message is received at the server.
        opcodes = [msg.opcode for msg in self.control_msgs(self.serverMsgs)]
        self.assertTrue(self.opcode in opcodes,
                        "Server did not receive the control "
                        "message with opcode: %s" % self.opcode)

        # Test arguments observed at the server match the sent arguments.
        all_args = [msg.args for msg in self.control_msgs(self.serverMsgs)]
        expected_args = self.args
        self.assertTrue(expected_args in all_args,
                        "Expected args (%s) not found in list of"
                        " observed args (%s)" % (expected_args, all_args))
