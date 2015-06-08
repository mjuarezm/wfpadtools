import unittest
from time import sleep

from obfsproxy.test.transports.wfpadtools import wfpad_tester as wfp


class AdaptiveTest(wfp.AdaptiveShimConfig, wfp.PrimitiveTest,
                   unittest.TestCase):
    server_args_list = list(wfp.AdaptiveShimConfig.server_args)
    server_args = tuple(server_args_list)

    def doWhileSession(self):
        sleep(0.1)

        # Trigger padding
        self.send_to_client(self.DATA_STR)
        sleep(0.1)
        self.send_to_server(self.DATA_STR)

    @unittest.skip("for now")
    def test_payload_padding(self):
        pass

    @unittest.skip("for now")
    def test_total_padding(self):
        pass


if __name__ == "__main__":
    unittest.main()
