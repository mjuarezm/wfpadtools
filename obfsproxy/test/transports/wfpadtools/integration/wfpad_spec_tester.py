import unittest

# WFPadTools imports
from obfsproxy.test import tester as ts

# Constants
SHIM_PORT = 6665
SOCKS_PORT = 6666


# DIRECT TESTS

class DirectWFPad(ts.DirectTest, unittest.TestCase):
    transport = "wfpad"
    server_args = ("wfpad", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT,
                   "--test=/tmp/client.dump")
    client_args = ("wfpad", "client",
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT,
                   "--test=/tmp/client.dump")


class DirectBuFLO(ts.DirectTest, unittest.TestCase):
    transport = "buflo"
    server_args = ("buflo", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT)
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)


class DirectShimTest(ts.DirectTest):
        """Extends DirectTest to create an instance of the shim.

        It will connect/disconnect to the shim to flag start/end
        of sessions.
        """
        def setUp(self):
            super(DirectShimTest, self).setUp()
            self.shim_chan = ts.connect_with_retry(("127.0.0.1", SHIM_PORT))
            self.shim_chan.settimeout(ts.SOCKET_TIMEOUT)

        def tearDown(self):
            self.shim_chan.close()
            super(DirectShimTest, self).tearDown()


# TESTS WITH THE SHIM


class DirectShimWFPad(DirectShimTest, unittest.TestCase):
    transport = "wfpad"
    server_args = ("wfpad", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT)
    client_args = ("wfpad", "client",
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)


class DirectShimBuFLO(DirectShimTest, unittest.TestCase):
    transport = "buflo"
    server_args = ("buflo", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT)
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SOCKS_PORT),
                   "--period=1",
                   "--psize=1443",
                   "--mintime=10",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)


class DirectShimCSBuFLO(DirectShimTest, unittest.TestCase):
    transport = "csbuflo"
    server_args = ("csbuflo", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT)
    client_args = ("buflo", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SHIM_PORT),
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)


class DirectShimTamaraw(DirectShimTest, unittest.TestCase):
    transport = "tamaraw"
    server_args = ("tamaraw", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--batch=1000",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT)
    client_args = ("tamaraw", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SHIM_PORT),
                   "--period=1",
                   "--psize=1443",
                   "--batch=1000",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)


class DirectShimAdaptivePadding(DirectShimTest, unittest.TestCase):
    transport = "adaptive"
    server_args = ("adaptive", "server",
                   "127.0.0.1:%d" % ts.SERVER_PORT,
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.EXIT_PORT)
    client_args = ("adaptive", "client",
                   "127.0.0.1:%d" % ts.ENTRY_PORT,
                   "--socks-shim=%d,%d" % (SHIM_PORT, SHIM_PORT),
                   "--period=1",
                   "--psize=1443",
                   "--dest=127.0.0.1:%d" % ts.SERVER_PORT)
