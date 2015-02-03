'''
Tests for the kist.py module that implements the KIST algorithm.
'''
import unittest
import socket

from obfsproxy.transports.wfpadtools import kist


class KistTest(unittest.TestCase):

    def setUp(self):
        self.kist_class = kist.Kist()

    def test_estimate_write_capacity(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        buf_capacity = self.kist_class.estimate_write_capacity(sock)
        self.assertTrue(buf_capacity)


if __name__ == "__main__":
    unittest.main()
