'''
Tests for the kist.py module that implements the KIST algorithm.
'''
import socket
from time import sleep
import unittest

from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.kist import estimate_write_capacity
from obfsproxy.transports.wfpadtools.test_util import DummyReadWorker


HOST = "127.0.0.1"
PORT = 9891


class KistTest(unittest.TestCase):

    def setUp(self):
        self.reader = DummyReadWorker((HOST, PORT))
        self.client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sleep(1)
        self.client_socket.connect((HOST, PORT))

    def test_estimate_write_capacity(self):
        buf_capacity = 1
        while buf_capacity > 0:
            self.client_socket.sendall('\0' * const.MTU)
            buf_capacity = estimate_write_capacity(self.client_socket)
            print buf_capacity
        self.assertTrue(buf_capacity == 0)
        self.client_socket.close()


if __name__ == "__main__":
    unittest.main()
