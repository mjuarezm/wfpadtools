"""
The socks_shim module implements a lightweight shim between the Tor
Browser and the SocksPort to allow extraction of request start/stop times.

Limitations:

 * Currently only SOCKS session start/end times are measured.  Things like HTTP
   pipelining will make the estimate inaccurate.

 * The information is only available on the client side.  If the server needs
   to continue to send padding till a specified duration past the request end,
   the application request ("visit") termination time must be communicated to
   the server.

 * When multiple bridges are being used concurrently, there is no easy way to
   disambiguate which bridge the application session will end up using.
   Solving this correctly will require modifications to the tor core code, till
   then, only use 1 bridge at a time.
"""
from twisted.internet import reactor
from twisted.internet.protocol import Protocol, Factory
from twisted.internet.endpoints import TCP4ClientEndpoint, TCP4ServerEndpoint

from obfsproxy.network.buffer import Buffer
import obfsproxy.common.log as logging

log = logging.get_obfslogger()

class _ShimClientProtocol(Protocol):
    _id = None
    _shim = None
    _server = None

    def __init__(self, factory, shim, server):
        self._shim = shim
        self._server = server

    def connectionMade(self):
        self._id = self._shim.notifyConnect()
        self._server._client = self
        self.writeToSocksPort(self._server._buf.read())

    def connectionLost(self, reason):
        self._shim.notifyDisconnect(self._id)

    def dataReceived(self, data):
        self._server.writeToClient(data)

    def writeToSocksPort(self, data):
        if data:
            self.transport.write(data)

class _ShimClientFactory(Factory):
    _shim = None
    _server = None

    def __init__(self, shim, server):
        self._shim = shim
        self._server = server

    def buildProtocol(self, addr):
        return _ShimClientProtocol(self, self._shim, self._server)

class _ShimServerProtocol(Protocol):
    _shim = None
    _socks_port = None
    _buf = None
    _client = None

    def __init__(self, factory, shim, socks_port):
        self._shim = shim
        self._socks_port = socks_port
        self._buf = Buffer()

    def connectionMade(self):
        ep = TCP4ClientEndpoint(reactor, '127.0.0.1', self._socks_port)
        f = _ShimClientFactory(self._shim, self)
        d = ep.connect(f)
        d.addErrback(self.onConnectFailed)

    def onConnectFailed(self, e):
        log.warning('[shim]: client connect failed: %s', e)

    def dataReceived(self, data):
        if self._client:
            self._client.writeToSocksPort(data)
        else:
            self._buf.write(data)

    def writeToClient(self, data):
        if data:
            self.transport.write(data)

class _ShimServerFactory(Factory):
    _shim = None
    _socks_port = None

    def __init__(self, shim, socks_port):
        self._shim = shim
        self._socks_port = socks_port

    def buildProtocol(self, addr):
        return _ShimServerProtocol(self, self._shim, self._socks_port)

class SocksShim(object):
    _observers = None
    _id = None

    def __init__(self, shim_port=9250, socks_port=9150):
        self._observers = []
        self._id = 0
        ep = TCP4ServerEndpoint(reactor, shim_port, interface='127.0.0.1')
        ep.listen(_ShimServerFactory(self, socks_port))

    def registerObserver(self, observer):
        self._observers.append(observer)

    def deregisterObserver(self, observer):
        self._observers.remove(observer)

    def notifyConnect(self):
        self._id += 1
        log.debug('[shim]: notifyConnect: id=%d', self._id)
        for o in self._observers:
            o.onConnect(self._id)
        return self._id

    def notifyDisconnect(self, conn_id):
        log.debug('[shim]: notifyDisconnect: id=%d', conn_id)
        for o in self._observers:
            o.onDisconnect(conn_id)

_instance = None

def new(shim_port=9250, socks_port=9150):
    global _instance
    if _instance:
        raise RuntimeError('SOCKS shim already running')
    _instance = SocksShim(shim_port, socks_port)

def get():
    global _instance
    if _instance is None:
        # XXX: Should this just return None?
        raise RuntimeError('SOCKS shim is not running')
    return _instance
