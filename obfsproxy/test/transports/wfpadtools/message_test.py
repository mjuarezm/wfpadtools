import unittest

import obfsproxy.transports.wfpadtools.message as msg
from obfsproxy.transports.wfpadtools import const


class WFPadMessageFactoryTest(unittest.TestCase):

    def setUp(self):
        self.msgFactory = msg.WFPadMessageFactory()

    def tearDown(self):
        pass

    def test_normal_message(self):
        msg = self.msgFactory.new("payload", flags=const.FLAG_DATA)
        pass

    def test_control_message(self):
        # Test control message with arguments that fit in payload
        testArgs, expArgs = [1, 2], '[1, 2]'
        ctrlMsgsArgs = self.msgFactory.encapsulate(opcode=const.OP_APP_HINT,
                                                   args=testArgs)
        self.assertEqual(len(ctrlMsgsArgs), 1,
                     "More than one message for control without args "
                     "was created.")
        ctrlMsgArgs = ctrlMsgsArgs[0]
        obsArgs = ctrlMsgArgs.args
        self.assertEqual(obsArgs, expArgs,
                         "Observed control message args (%s) and "
                         "expected args (%s) do not match"
                         % (obsArgs, expArgs))

        # Test control message with arguments that do not fit
        testArgs = range(1000)
        expArgs = str(testArgs)
        ctrlMsgsArgs = self.msgFactory.encapsulate(opcode=const.OP_APP_HINT,
                                                   args=testArgs)
        self.assertTrue(len(ctrlMsgsArgs) > 1,
                     "No more than one message for control without args "
                     "was created.")


class WFPadMessageExtractorTest(unittest.TestCase):

    def setUp(self):
        self.msgFactory = msg.WFPadMessageFactory()
        self.msgExtractor = msg.WFPadMessageExtractor()

    def tearDown(self):
        pass

    def test_send_data_message(self):
        testData = "foo"
        dataMsgs = self.msgFactory.encapsulate(testData)
        strMsg = "".join([str(msg) for msg in dataMsgs])
        extractMsgs = self.msgExtractor.extract(strMsg)
        obsData = extractMsgs[0].payload
        self.assertEqual(obsData, testData,
                         "Observed data: %s does not match with"
                         " expected data: %s." % (obsData, testData))

    def test_extract_control_message(self):
        testArgs = [range(500), range(500)]
        ctrlMsgsArgs = self.msgFactory.encapsulate(opcode=const.OP_GAP_HISTO,
                                                   args=testArgs)
        strMsg = "".join([str(msg) for msg in ctrlMsgsArgs])
        extractedMsgs = self.msgExtractor.extract(strMsg)
        obsArgs = extractedMsgs[0].args
        self.assertEqual(obsArgs, testArgs,
                         "Observed args: %s does not match with"
                         " expected args: %s." % (obsArgs, testArgs))

        # Test piggybacking
        piggybackedData = "Iampiggybacked"
        ctrlMsgsArgs = self.msgFactory.encapsulate(opcode=const.OP_GAP_HISTO,
                                                   args=testArgs,
                                                   data=piggybackedData)
        strMsg = "".join([str(msg) for msg in ctrlMsgsArgs])
        extractedMsgs = self.msgExtractor.extract(strMsg)
        obsData = extractedMsgs[0].payload
        self.assertEqual(obsData, piggybackedData,
                         "Observed data: %s does not match with"
                         " expected data %s." % (obsData, piggybackedData))


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
