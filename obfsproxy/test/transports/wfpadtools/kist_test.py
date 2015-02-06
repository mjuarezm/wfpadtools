'''
Tests for the kist.py module that implements the KIST algorithm.
'''
import socket
from time import sleep
import unittest

from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.kist import estimate_write_capacity
from obfsproxy.transports.wfpadtools import test_util


HOST = "127.0.0.1"
PORT = 6666


class KistTest(unittest.TestCase):

    def setUp(self):
        pass

    def test_estimate_write_capacity_client(self):
        test_util.DummyReadWorker((HOST, PORT))
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sleep(1)
        client_socket.connect((HOST, PORT))
        buf_capacity = estimate_write_capacity(client_socket)
        i = 0
        while buf_capacity > const.MTU:
            client_socket.sendall('\0' * const.MTU)
            buf_capacity = estimate_write_capacity(client_socket)
            print i, buf_capacity
            i += 1
        self.assertTrue(buf_capacity > const.MTU)
        client_socket.close()

    def test_estimate_write_capacity_server(self):
        test_util.DummyWriteWorker((HOST, PORT))
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((HOST, PORT))
        listener.listen(1)
        (conn, _) = listener.accept()
        listener.close()
        try:
            i = 0
            while True:
                conn.recv(4096)
                buf_capacity = estimate_write_capacity(conn)
                print i, buf_capacity
                i += 1
        except Exception, e:
            print "[ReadWorker] Exception %s" % str(e)
        conn.close()


if __name__ == "__main__":
    unittest.main()
