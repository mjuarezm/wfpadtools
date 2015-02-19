"""Provides general network-related utility methods."""
import os
import sys
import json
import Queue
import socket
import struct
import requesocks
import threading
from time import sleep
from random import randint

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
from obfsproxy.test.tester import TransportsSetUp
from obfsproxy.transports.wfpadtools.util import genutil as gu
from obfsproxy.transports.wfpadtools.util import logutil

log = logutil.get_logger("netutil")


class CommInterfaceAbstract(TransportsSetUp):
    """Implement methods for a class with a CommunicationInterface instance.

    The instance must be named `commInterf`.
    """
    ENTRY_PORT = None
    EXIT_PORT = None
    SHIM_PORTS = None

    def setup(self):
        """Sets dummy and obfsproxy endpoints for bidirectional comm."""
        os.chdir(const.BASE_DIR)
        self.shim_commInterf = CommunicationInterface()
        self.commInterf = CommunicationInterface()
        self.shim_commInterf = CommunicationInterface()
        self.commInterf.listen((const.LOCALHOST, self.EXIT_PORT))
        sleep(0.3)
        TransportsSetUp.setUp(self)
        sleep(4)
        self.commInterf.connect((const.LOCALHOST, self.ENTRY_PORT))

    def send(self, msg, direction=const.OUT, op=False, wait=True):
        """Send msg to obfsproxy client or server.

        The `op` option is used to indicate that we're passing
        a test instruction to the client. See the testutil module.
        """
        if direction is const.OUT:
            self.commInterf.send('client', msg, op, wait=wait)
        elif direction is const.IN:
            self.commInterf.send('server', msg, wait=wait)
        else:
            raise ValueError("Invalid direction!")

    def send_instruction(self, opcode, args=None):
        """Send instruction to client."""
        instrMsg = "TEST:{};".format(str(opcode))
        if args:
            instrMsg += json.dumps(args)
        self.send_to_client(instrMsg, op=True)

    def send_to_client(self, msg, op=False):
        """Shortcut method for sending to the client."""
        self.send(msg, const.OUT, op)

    def send_to_server(self, msg):
        """Shortcut method for sending to the server."""
        self.send(msg, const.IN)

    def start_session(self):
        """Make TCP connection to shim to flag start of session to PT."""
        self.shim_commInterf.listen((const.LOCALHOST, self.SHIM_PORTS[1]))
        sleep(0.2)
        self.shim_commInterf.connect((const.LOCALHOST, self.SHIM_PORTS[0]))

    def end_session(self):
        """Destroy TCP connection to shim to flag end of session to PT."""
        self.shim_commInterf.close()

    def close(self):
        """Close the communication interface."""
        TransportsSetUp.tearDown(self)
        self.commInterf.close()
        self.commInterf.terminate()


class BiTransportSetup(CommInterfaceAbstract):
    """Implement the setup of the interface in the init.

    This class allows instantiating the setup as a regular class,
    not as a test case class.
    """
    def __init__(self):
        """Run the parent class setup method."""
        self.setup()


class Command(object):
    """ A command to the server thread.
        Each command type has its associated data:

        LISTEN:    (host, port) tuple
        CONNECT:   (host, port) tuple
        SEND:       Data string
        RECEIVE:    Data length (optional)
        CLOSE:      None
    """
    LISTEN, CONNECT, SEND, RECEIVE, CLOSE = range(5)

    def __init__(self, command_type, data=None):
        self.type = command_type
        self.data = data


class Reply(object):
    """ A reply from an endpoint thread.
        Each reply type has its associated data:

        ERROR:      The error string
        SUCCESS:    Depends on the command - for RECEIVE it's the received
                    data string, for others None.
    """
    ERROR, SUCCESS = range(2)

    def __init__(self, reply_type, data=None):
        self.type = reply_type
        self.data = data


class CommunicationInterface(object):

    def __init__(self):
        self.endpoints = {'client': SocketClientThread(use_header=False),
                          'server': SocketServerThread(use_header=False)
                          }
        self._start()

    def _start(self):
        log.debug("Setting up dummy worker endpoints.")
        for endpoint in self.endpoints.itervalues():
            endpoint.start()

    def send(self, sndr, data, op=False, wait=True):
        rcvr = 'server' if sndr is 'client' else 'client'
        log.debug("%s sending %sbytes of data to %s", sndr, len(data), rcvr)
        if not wait:  # SPEEDUP: Let's try to ignore replies
            return
        self.endpoints[sndr].cmd_q.put(Command(Command.SEND, data))
        if op:
            return self.wait_reply(sndr)
        self.endpoints[rcvr].cmd_q.put(Command(Command.RECEIVE, len(data)))
        return self.wait_replies(sndr, rcvr)

    def listen(self, address):
        log.debug("Dummy server is listening at %s", address)
        self.endpoints["server"].cmd_q.put(Command(Command.LISTEN, address))

    def connect(self, address):
        log.debug("Dummy client connects to %s", address)
        self.endpoints["client"].cmd_q.put(Command(Command.CONNECT, address))
        return self.wait_replies()

    def close(self):
        log.debug("Dummy workers are being closed.")
        for endpoint in self.endpoints.itervalues():
            endpoint.cmd_q.put(Command(Command.CLOSE))
        return self.wait_replies()

    def terminate(self):
        for endpoint in self.endpoints.itervalues():
            endpoint.join()

    def wait_replies(self, first='client', second='server'):
        return (self.wait_reply(first), self.wait_reply(second))

    def wait_reply(self, endpoint):
        reply = None
        while not reply:
            reply = self.get_reply(endpoint)
            if reply:
                log.debug("Got reply from endpoint %s: (%s, %s)",
                          endpoint, reply[0], reply[1])
        return reply

    def get_reply(self, endpoint):
        try:
            reply = self.endpoints[endpoint].reply_q.get(block=False)
            status = "SUCCESS" if reply.type == Reply.SUCCESS else "ERROR"
            info_msg = '%s reply %s: %s' % (endpoint.__class__,
                                            status,
                                            reply.data)
            if reply.type is Reply.ERROR:
                raise Exception(info_msg)
            return (reply.type, reply.data)
        except Queue.Empty:
            return None


class SocketThread(threading.Thread):
    """ Implements a threaded socket.

    Can be controlled via the cmd_q Queue attribute. Replies are placed in
    the reply_q Queue attribute.

    Source from: https://github.com/eliben/code-for-blog
    """
    def __init__(self, cmd_q=None,
                 reply_q=None, use_header=False, extra_handlers=None):
        super(SocketThread, self).__init__()
        self.cmd_q = cmd_q or Queue.Queue()
        self.reply_q = reply_q or Queue.Queue()
        self.alive = threading.Event()
        self.alive.set()
        self.socket = None
        self.use_header = use_header
        self.handlers = {
            Command.LISTEN: None,
            Command.CONNECT: None,
            Command.CLOSE: self._handle_CLOSE,
            Command.SEND: self._handle_SEND,
            Command.RECEIVE: self._handle_RECEIVE,
        }
        for key, handler in extra_handlers.iteritems():
            self.handlers[key] = handler

    def run(self):
        while self.alive.isSet():
            try:
                # Queue.get with timeout to allow checking self.alive
                cmd = self.cmd_q.get(True, 0.1)
                self.handlers[cmd.type](cmd)
            except Queue.Empty:
                continue

    def join(self, timeout=None):
        self.alive.clear()
        threading.Thread.join(self, timeout)

    def _handle_CLOSE(self, cmd):
        self.socket.close()
        reply = Reply(Reply.SUCCESS)
        self.reply_q.put(reply)

    def _handle_SEND(self, cmd):
        header = ''
        if self.use_header:
            header = struct.pack('<L', len(cmd.data))
        try:
            self.socket.sendall(header + cmd.data)
            self.reply_q.put(self._success_reply())
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))

    def _handle_RECEIVE(self, cmd):
        try:
            if self.use_header:
                header_data = self._recv_n_bytes(4)
                if len(header_data) == 4:
                    msg_len = struct.unpack('<L', header_data)[0]
                else:
                    raise RuntimeError("Header format not recognized.")
            else:
                msg_len = cmd.data
            data = self._recv_n_bytes(msg_len)
            if len(data) == msg_len:
                self.reply_q.put(self._success_reply(data))
                return
            self.reply_q.put(self._error_reply('Socket closed prematurely'))
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))

    def _recv_n_bytes(self, n):
        """ Convenience method for receiving exactly n bytes from
            self.socket (assuming it's open and connected).
        """
        data = ''
        while len(data) < n:
            chunk = self.socket.recv(n - len(data))
            if chunk == '':
                break
            data += chunk
        return data

    def _error_reply(self, errstr):
        return Reply(Reply.ERROR, errstr)

    def _success_reply(self, data=None):
        return Reply(Reply.SUCCESS, data)


class SocketClientThread(SocketThread):
    """Extends the socket thread to implement a threaded client."""
    def __init__(self, cmd_q=None, reply_q=None, use_header=True):
        client_handler = {Command.CONNECT: self._handle_CONNECT}
        super(SocketClientThread, self).__init__(extra_handlers=client_handler)

    def _handle_CONNECT(self, cmd):
        try:
            self.socket = socket.socket(
                socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((cmd.data[0], cmd.data[1]))
            self.reply_q.put(self._success_reply())
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))


class SocketServerThread(SocketThread):
    """Extends the socket thread to implement a threaded server."""
    def __init__(self, cmd_q=None, reply_q=None, use_header=True):
        server_handler = {Command.LISTEN: self._handle_LISTEN}
        super(SocketServerThread, self).__init__(extra_handlers=server_handler)

    def _handle_LISTEN(self, cmd):
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.socket.bind((cmd.data[0], cmd.data[1]))
            self.socket.listen(1)
            self.socket, self.address = self.socket.accept()
            self.reply_q.put(self._success_reply())
        except IOError as e:
            self.reply_q.put(self._error_reply(str(e)))
        except:
            self.reply_q.put(self._error_reply(sys.exc_info()[0]))


def rand_ip():
    """Return a random IP (non-realistic)."""
    return ".".join([str(randint(1, 254)) for _ in xrange(4)])


def get_local_ip():
    """Return local IP address."""
    google_dns_server_ip = '8.8.8.8'
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect((google_dns_server_ip, 80))
    local_ip = s.getsockname()[0]
    s.close()
    return local_ip


def get_free_ports(n=1):
    """Return free socket port.

    WARNING: doesn't guarantee that port will be free from
    the end of this function, till a new socket is bind to it.
    """
    ports, socks = [], []
    for _ in xrange(n):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', 0))
        free_port = s.getsockname()[1]
        socks.append(s)
        ports.append(free_port)
    for s in socks:
        s.close()
    if n == 1:
        return free_port
    return ports


@gu.memodict
def toIP(ipaddr):
    '''Return  4 bytes to an string with IP format (o1.o2.o3.o4).'''
    return ".".join(map(str, struct.unpack("!BBBB", ipaddr)))


def get_url(url):
    """Return body of HTTP request to `url`."""
    import urllib2
    response = urllib2.urlopen('http://python.org/')
    html = response.read()
    return html


def get_page(url, port, timeout, max_retries=1):
    if max_retries == 1:
        session = requesocks.session()
    elif max_retries > 1:
        session = requesocks.session(config={'max_retries': 10})
    else:
        raise
    session.proxies = {'http': 'socks5://127.0.0.1:{}'.format(port),
                       'https': 'socks5://127.0.0.1:{}'.format(port)}
    return session.get(url, timeout=timeout)


def get_default_gateway_linux():
    """Read the default gateway directly from /proc."""
    with open("/proc/net/route") as fh:
        for line in fh:
            fields = line.strip().split()
            if fields[1] != '00000000' or not int(fields[3], 16) & 2:
                continue
            return socket.inet_ntoa(struct.pack("<L", int(fields[2], 16)))
