import json
import unittest

# WFPadTools imports
import obfsproxy.transports.wfpadtools.message as msg
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.scramblesuit import probdist


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

    def test_uniform_length(self):
        # Test payload is padded to specified length
        testData = "foo padded to MPU"
        dataMsgs = self.msgFactory.encapsulate(data=testData,
                                               lenProbdist=probdist.uniform(const.MPU))
        self.assertEqual(len(dataMsgs), 1,
                         "More than one message for control without args "
                         "was created.")
        dataMsg = dataMsgs[0]
        obsLength = len(dataMsg)
        expLength = const.MTU
        self.assertEqual(obsLength, expLength,
                         "Observed length (%s) and "
                         "expected length (%s) do not match"
                         % (obsLength, expLength))

    def test_equality(self):
        testArgs = [1, 2]
        ctrlMsgsArgs1 = self.msgFactory.encapsulate(opcode=const.OP_APP_HINT,
                                                    args=testArgs)
        ctrlMsgsArgs2 = self.msgFactory.encapsulate(opcode=const.OP_APP_HINT,
                                                    args=testArgs)
        ctrlMsgsArgs3 = self.msgFactory.encapsulate(opcode=const.OP_APP_HINT)
        self.assertTrue(ctrlMsgsArgs1 == ctrlMsgsArgs2,
                        "Equal messages are seen as different.")  # TODO: this message sucks...
        self.assertTrue(ctrlMsgsArgs1 != ctrlMsgsArgs3,
                        "Different messages are seen as equal.")


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

    def test_msg_from_string(self):
        msgs = 5 * [None]
        msgs[0] = self.msgFactory.new(payload="This is a custom "
                                      " message for you to parse.")
        msgs[1] = self.msgFactory.new(payload="This is a custom "
                                      " message for you to parse.",
                                      paddingLen=2)
        msgs[2] = self.msgFactory.new(payload="This is a custom "
                                      " message for you to parse.",
                                      flags=const.FLAG_CONTROL,
                                      opcode=const.OP_APP_HINT)
        msgs[3] = self.msgFactory.new(payload="This is a custom "
                                      " message for you to parse.",
                                      flags=const.FLAG_CONTROL,
                                      opcode=const.OP_APP_HINT,
                                      args=json.dumps([1, 2, 3, 4]))
        msgs[4] = self.msgFactory.new(payload="This is a custom "
                                      " message for you to parse.",
                                      paddingLen=1000,
                                      flags=const.FLAG_CONTROL,
                                      opcode=const.OP_APP_HINT,
                                      args=json.dumps([range(500),
                                                       range(500)]))
        for i, msg in enumerate(msgs):
            self.assertTrue(msg == self.msgExtractor.msg_from_string(str(msg)),
                            "Messages do not match for message number %d!" % i)


if __name__ == "__main__":
    unittest.main()
