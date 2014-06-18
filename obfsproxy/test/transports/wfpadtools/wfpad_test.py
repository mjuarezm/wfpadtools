from obfsproxy.test.tester import DirectTest
from obfsproxy.test.tester import SERVER_PORT, EXIT_PORT, ENTRY_PORT
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import message
from obfsproxy.transports.wfpadtools import wfpad, const
import random
from time import sleep
import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest
import obfsproxy.transports.wfpadtools.util as ut


class MessagesTest(STTest):

    def assert_num_encapsulated_msgs(self, len_data, expected_num):
        test_msgs = self.create_test_msgs(len_data)
        num_msgs = len(test_msgs)
        self.assertEqual(num_msgs, expected_num,
                         "Number of messages created %s does not match with "
                         "expected number of messages %s, Length data is %s."
                         % (num_msgs, expected_num, len_data))

    def create_test_msg(self, length=const.MPU, flags=const.FLAG_DATA):
        data = ut.rand_str(length)
        return message.WFPadMessage(data)

    def create_test_msgs(self, length=const.MPU, flags=const.FLAG_DATA):
        data = ut.rand_str(length)
        return message.createWFPadMessages(data, flags=const.FLAG_DATA)

    def test_create_wfpad_msgs(self):
        # Assert size of message's payload
        self.assert_num_encapsulated_msgs(const.MPU - 1, 1)
        self.assert_num_encapsulated_msgs(const.MPU, 1)
        self.assert_num_encapsulated_msgs(const.MPU + 1, 2)

        # Assert flag
        test_msg = self.create_test_msg()
        self.assertEqual(test_msg.flags, const.FLAG_DATA,
                         "Flag data is not set correctly in test message.")


class MessageExtractorTest(MessagesTest):

    def setUp(self):
        self.extractor = message.WFPadMessageExtractor()
        MessagesTest.setUp(self)

    def msg_to_str(self, msg):
        return str(msg.totalLen) + str(msg.payloadLen) \
            + str(msg.flags) + str(msg.payload)

    def test_extract_msgs(self):
        NUM_TEST_MSGS = 4
        msgs = self.create_test_msgs(const.MPU * NUM_TEST_MSGS)
        data = "".join([self.msg_to_str(msg) for msg in msgs])
        msgs = self.extractor.extract(data)
        msg1 = msgs[0]
        flags = msg1.flags
        self.assertEqual(flags, const.FLAG_DATA,
                         "FLAG_DATA (%s) is not correctly parsed from the"
                         " message: %s" % (const.FLAG_DATA, flags))


class WFPadTests(DirectTest, STTest):
    transport = "buflo"

    def setUp(self):
        self.server_args = ("buflo", "server",
               "127.0.0.1:%d" % SERVER_PORT,
               "--period=0.1",
               "--psize=1448",
               "--mintime=2",
               "--dest=127.0.0.1:%d" % EXIT_PORT)
        self.client_args = ("buflo", "client",
               "127.0.0.1:%d" % ENTRY_PORT,
               "--period=0.1",
               "--psize=1448",
               "--mintime=2",
               "--dest=127.0.0.1:%d" % SERVER_PORT)
        super(WFPadTests, self).setUp()

    def tearDown(self):
        super(WFPadTests, self).tearDown()

    def test_padding(self):
        pass


class WFPadTest(STTest):
    """Test methods from WFPadTransport class."""
    class DataStream():

        def __init__(self, data):
            self.data = data

        def __len__(self):
            return len(self.data)

        def read(self):
            return self.data

    def generate_stream(self, output, t_max, psize=1):
        t = 0
        while t < t_max:
            sleep_t = random.random()
            t += sleep_t
            if random.randrange(2):
                output(self.DataStream(ut.rand_str(size=psize)))
            sleep(sleep_t)

    def test_buflo(self):
        period = 2
        psize = 1
        wfpad_client = wfpad.WFPadClient(probdist.new(lambda: period),
                                         probdist.new(lambda: psize))
        wfpad_client.circuitConnected()
        self.generate_stream(wfpad_client.receivedUpstream, 20)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
