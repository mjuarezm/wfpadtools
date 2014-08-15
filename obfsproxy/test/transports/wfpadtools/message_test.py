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

    def test_extract_control_message(self):
        testArgs = [range(500), range(500)]
        ctrlMsgsArgs = self.msgFactory.encapsulate(opcode=const.OP_GAP_HISTO,
                                                   args=testArgs)
        strMsg = "".join([str(msg) for msg in ctrlMsgsArgs])
        extractedMsgs = self.msgExtractor.extract(strMsg)
        self.assertEqual(strMsg, "".join([str(msg) for msg in extractedMsgs]),
                         "First extracted messages do not match with"
                         " first original messages.")

        # Test piggybacking
        piggybackedData = "Iampiggybacked"
        ctrlMsgsArgs = self.msgFactory.encapsulate(opcode=const.OP_GAP_HISTO,
                                                   args=testArgs,
                                                   data=piggybackedData)
        strMsg = "".join([str(msg) for msg in ctrlMsgsArgs])
        extractedMsgs = self.msgExtractor.extract(strMsg)
        self.assertEqual(strMsg, "".join([str(msg) for msg in extractedMsgs]),
                         "First extracted messages do not match with"
                         " first original messages.")

        obsPigBckdData = extractedMsgs[-1:][0].payload
        self.assertEqual(obsPigBckdData, piggybackedData,
                         "Observed piggybacked data: %s and expected"
                         " data: %s, do not match" % (obsPigBckdData,
                                                      piggybackedData))

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
