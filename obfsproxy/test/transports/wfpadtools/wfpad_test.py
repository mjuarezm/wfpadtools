import multiprocessing
from obfsproxy.common import transport_config
from obfsproxy.network.network import StaticDestinationServerFactory
from obfsproxy.test.tester import ENTRY_PORT, SERVER_PORT
from obfsproxy.test.tester import Obfsproxy, \
    connect_with_retry, SOCKET_TIMEOUT, TEST_FILE
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport
from time import sleep, time
from twisted.internet import reactor
import unittest

import obfsproxy.common.log as logging
import obfsproxy.common.serialize as pack
from obfsproxy.test.transports.wfpadtools.sttest import STTest


DEBUG = False

# Logging settings:
log = logging.get_obfslogger()
log.set_log_severity('error')

if DEBUG:
    log.set_log_severity('debug')


class WFPadServerTestWrapper(WFPadTransport, STTest):
    """This class is a wrapper of WFPadTransport for testing.

    Overrides most WFPadTransport methods and extends some of them for
    testing.
    """
    def __init__(self):
        self.start = 0
        self.rcvIndex = 0
        self.ticking = False
        self.final = False
        self.messages = []
        super(WFPadServerTestWrapper, self).__init__()

    def receivedDownstream(self, data):
        """Test data received from client is sent within the time period."""
        if self.ticking:
            self.rcvIndex += 1
            obs_period = time() - self.start
            log.debug("Observed period in reception number %s: %s"
                       % (self.rcvIndex, obs_period))
            self.assertAlmostEqual(self.period, obs_period, None,
                                   "The observed period %s does not match"
                                   " with the expected period %s"
                                   % (obs_period, self.period), delta=0.05)
        else:
            self.rcvIndex = 0
            self.ticking = True
        self.start = time()
        super(WFPadServerTestWrapper, self).receivedDownstream(data)

    def processMessages(self, data):
        """Test data received from client satisfies specified length."""
        self.msgExtractor.recvBuf += data
        obsLen = 0
        while len(self.msgExtractor.recvBuf) >= const.HDR_LENGTH:
            self.msgExtractor.totalLen = pack.ntohs(self.msgExtractor\
                                .get_field(const.TOTLENGTH_POS,
                                           const.TOTLENGTH_LEN))
            if (len(self.msgExtractor.recvBuf) - const.HDR_LENGTH)\
                     < self.msgExtractor.totalLen:
                break
            obsLen = self.msgExtractor.totalLen + const.HDR_LENGTH
            self.msgExtractor.reset()
        if obsLen:
            log.debug("Observed length in reception number %s: %s"
                       % (self.rcvIndex, obsLen))
            self.assertTrue(self.psize == obsLen,
                       "The observed length %s does not match"
                       " with the expected length %s"
                       % (obsLen, self.psize))
        super(WFPadServerTestWrapper, self).processMessages(data)


class WFPadWorker(object):

    @staticmethod
    def work(ip, port):
        pt_config = transport_config.TransportConfig()
        pt_config.setListenerMode("server")
        pt_config.setObfsproxyMode("external")
        WFPadServerTestWrapper.setup(pt_config)
        factory = StaticDestinationServerFactory((ip, port), "server",
                                                 WFPadServerTestWrapper,
                                                 pt_config)
        reactor.listenTCP(port, factory, interface=ip)
        reactor.run()

    def __init__(self, address):
        self.worker = multiprocessing.Process(target=self.work,
                                              args=(address))
        self.worker.start()

    def stop(self):
        if self.worker.is_alive():
            self.worker.terminate()


class IntermediateTest(object):

    def setUp(self):
        self.obfs_server = WFPadWorker(("127.0.0.1", SERVER_PORT))
        sleep(0.2)
        self.obfs_client = Obfsproxy(self.client_args)
        self.input_chan = connect_with_retry(("127.0.0.1", ENTRY_PORT))
        self.input_chan.settimeout(SOCKET_TIMEOUT)

    def tearDown(self):
        self.obfs_client.stop()
        self.obfs_server.stop()
        self.input_chan.close()

    def test_send_data(self):
        self.input_chan.sendall(TEST_FILE)
        sleep(2)
        self.input_chan.close()


class WFPadTests(IntermediateTest, STTest):
    transport = "wfpad"

    def setUp(self):
        self.client_args = ("wfpad", "client",
               "127.0.0.1:%d" % ENTRY_PORT,
               "--dest=127.0.0.1:%d" % SERVER_PORT)
        super(WFPadTests, self).setUp()

    def tearDown(self):
        super(WFPadTests, self).tearDown()


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
