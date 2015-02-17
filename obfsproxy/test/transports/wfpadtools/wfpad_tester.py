"""Provide methods and classes to be used in tests for wfpad transports."""
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


DEBUG = True
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
                   "--psize=1443",
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--period=1",
                   "--psize=1443",
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
                   "--psize=1443",
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class CSBuFLOShimConfig(object):
    transport = "csbuflo"
    server_args = ("csbuflo", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SHIM_PORT),
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class AdaptiveShimConfig(object):
    transport = "adaptive"
    server_args = ("adaptive", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("adaptive", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SHIM_PORT),
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=%s" % const.DUMPS["client"])


class TamarawShimConfig(object):
    transport = "tamaraw"
    server_args = ("tamaraw", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--batch=1000",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=%s" % const.DUMPS["server"])
    client_args = ("tamaraw", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SHIM_PORT),
                   "--period=1",
                   "--psize=1443",
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
                   "--psize=1443",
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
class TestSetUp(nu.CommInterfaceAbstract):
    """Implement the CommInterfaceAbstract as a test class.

    The setUp method sets the bidirectional communication (obfsproxy (with
    shim) and dummy endpoints. The tearDown method closes communication
    and still-alive processes.
    """
    ENTRY_PORT = tester.ENTRY_PORT
    EXIT_PORT = tester.EXIT_PORT
    SHIM_PORTS = [SHIM_PORT, SOCKS_PORT]

    def setUp(self):
        log.debug("\n\n\n\n")
        fu.resetdir(const.TEST_DUMP_DIR)
        self.setup()

    def tearDown(self):
        self.close()


class PrimitiveTest(TestSetUp):

    BEFORE_SESSION_TIME = 1
    DURING_SESSION_TIME = 1
    AFTER_SESSION_TIME = 1

    def setUp(self):
        TestSetUp.setUp(self)
        self.doBeforeSessionStarts()
        sleep(self.BEFORE_SESSION_TIME)

        log.debug("Flag beginning of session.")
        self.start_session()
        self.doWhileSession()
        sleep(self.DURING_SESSION_TIME)

        log.debug("Flag end of session.")
        self.end_session()
        self.doAfterSessionEnds()
        sleep(self.AFTER_SESSION_TIME)

        log.debug("Parse dumps.")
        self.parseDumps()

    def parseDumps(self):
        """Parse test dumps."""
        # Load dumps
        sleep(1)
        serverDumps = self.__load_wrapper("server")
        log.debug("Server Dumps: %s", serverDumps)
        clientDumps = self.__load_wrapper("client")
        log.debug("Client Dumps: %s", clientDumps)

        # Parse messages
        self.clientMsgs = self.__messages(clientDumps)
        self.serverMsgs = self.__messages(serverDumps)

        # States
        self.clientStates = self.__states(clientDumps)
        self.serverStates = self.__states(serverDumps)
        self.clientState = self.__last_state(clientDumps)
        self.serverState = self.__last_state(serverDumps)

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
        try:
            return du.pick_load(const.DUMPS[end])
        except:
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


class TestSendControlMessage(PrimitiveTest):

    def doBeforeSessionStarts(self):
        """Send control msg."""
        log.debug("Sending to client the control instruction"
                  " for control msg: %s", getOpcodeNames(self.opcode))
        self.send_instruction(self.opcode, self.args)


class TestSendDataServer(TestSendControlMessage):

    def doWhileSession(self):
        """Send file to server."""
        log.debug("Sending data to server: %s", TEST_MSG)
        self.send_to_server(TEST_MSG)


class TestControlMessages(TestSendControlMessage):

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
