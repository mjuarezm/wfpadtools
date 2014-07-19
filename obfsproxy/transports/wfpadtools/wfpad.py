"""The wfpad module implements the Tor WF framework to develop WF defenses.

This module allows the development of various WF countermeasures based on
link-padding. It implements a faming layer to introduce dummy messages into
the stream and discard them at the other end.
"""
from sets import Set
from twisted.internet import reactor

import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message, socks_shim
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.message import WFPadMessage
from obfsproxy.transports.wfpadtools.padtools import ControlMessageReceiver, \
    ControlMessageSender


log = logging.get_obfslogger()


class WFPadShimObserver(object):
    """Observer class for the SOCKS's shim.

    This class provides signaling to start and end of web page sessions.
    We need to monitor how many sessions are currently pending by counting
    connect/disconnect notifications.
    """
    def __init__(self, instanceWFPadTransport):
        """Instantiates a new `ShimObserver` object."""
        self._connections = Set([])
        self.wfpad = instanceWFPadTransport

    def getNumConnections(self):
        """Return num of open connections."""
        return len(self._connections)

    def onConnect(self, conn_id):
        """A new connection starts."""
        if self.getNumConnections() == 0:
            self.onSessionStarts()
        self._connections.add(conn_id)

    def onDisconnect(self, conn_id):
        """An open connection finishes."""
        if conn_id in self._connections:
            self._connections.remove(conn_id)
        if self.getNumConnections() == 0:
            self.onSessionEnds()

    def onSessionStarts(self):
        """Do operations to be done when session starts."""
        log.debug("A session has started.")
        self.wfpad._sessionNumber += 1
        self.wfpad._visiting = True

    def onSessionEnds(self):
        """Do operations to be done when session ends."""
        log.debug("A session has ended.")
        self.wfpad._visiting = False


class WFPadTransport(BaseTransport):
    """Implements the Tor WF framework to develop WF countermeasures.

    This class implements methods which implement primitives and protocols
    specifications to further develop WF countermeasures.
    """
    _sessionNumber = 0
    _sendBuf = ""  # Buffer for outgoing data.
    _elapsed = 0  # Count time spent on padding
    _consecPaddingMsgs = 0  # Counter for padding messages
    _opcode = None  # Opcode for messages
    _visiting = False  # Indicates whether we are in the middle of a visit
    _controlReceiver = ControlMessageReceiver()
    _controlSender = ControlMessageSender()

    def __init__(self):
        """Initialize a WFPadTransport object."""
        log.debug("Initializing %s." % const.TRANSPORT_NAME)

        super(WFPadTransport, self).__init__()

        # Initialize the protocol's state machine.
        self._state = const.ST_WAIT

        # Buffer used for padding.
        self._paddingBuffer = Buffer()

        # Used to extract protocol messages from encrypted data.
        self._msgFactory = message.WFPadMessageFactory()
        self._msgExtractor = message.WFPadMessageExtractor()

        # Initialize probability distributions
        self._period = 0.01
        self._delayProbdist = probdist.new(lambda: self._period,
                                            lambda i, n, c: 1)
        self._psize = const.MTU
        self._lengthProbdist = probdist.new(lambda: self._psize,
                                             lambda i, n, c: 1)

        if self.weAreClient and self.shim_args and not socks_shim.get():
            try:
                shim_port, socks_port = self.shim_args
                socks_shim.new(int(shim_port), int(socks_port))
            except Exception as e:
                log.error('Failed to initialize SOCKS shim: %s', e)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments."""
        subparser.add_argument('--socks-shim',
                               action='store',
                               dest='shim',
                               help='wfpad SOCKS shim (shim_port,socks_port)')
        super(WFPadTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        parentalApproval = super(
            WFPadTransport, cls).validate_external_mode_cli(args)
        if not parentalApproval:
            raise PluggableTransportError(
                "Pluggable Transport args invalid: %s" % args)
        cls.shim_args = None
        if args.shim:
            cls.shim_args = args.shim.split(',')

    @classmethod
    def setup(cls, transportConfig):
        """Called once when obfsproxy starts."""
        log.error("\n\n"
                  "########################################################\n"
                  " WFPad isn't a Website Fingerprinting defense by itself.\n"
                  "########################################################\n")

        cls.weAreClient = transportConfig.weAreClient
        cls.weAreServer = not cls.weAreClient
        cls.weAreExternal = transportConfig.weAreExternal

    def circuitConnected(self):
        """Initiate handshake.

        This method is only relevant for clients since servers never initiate
        handshakes.
        """
        self._state = const.ST_CONNECTED
        self.flushSendBuffer()
        # Start padding link
        #self.startPadding()

    def sendRemote(self, data, flags=const.FLAG_DATA):
        """Send data to the remote end once the connection is established.

        The given `data` is first encapsulated in protocol messages.  Then, the
        protocol message(s) are sent over the wire.  The argument `flags'
        specifies the protocol message flags.
        """
        log.debug("Processing %d bytes of outgoing data." % len(data))
        if self._state is const.ST_PADDING:
            self._paddingBuffer.write(data)
        else:
            self.sendMessages(data)

    def sendMessages(self, data):
        """Encapsulates `data` in messages and sends over the link."""
        msgs = self._msgFactory.createWFPadMessages(data)
        str_msgs = "".join([str(msg) for msg in msgs])
        self.circuit.downstream.write(str_msgs)

    def encapsulateBufferData(self, length=None, opcode=None, args=None):
        """Reads from buffer and creates messages to send them over the link.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. Otherwise, we generate random padding
        and we send it over the wire in chunks.
        """
        msg = WFPadMessage()
        msgTotalLen = length if length else self.drawMessageLength()
        payloadLen = msgTotalLen - const.MIN_HDR_LEN
        dataLen = len(self._paddingBuffer)
        if dataLen > 0:
            log.debug("Flush buffer")
            if dataLen > payloadLen:
                log.debug("Message with no padding.")
                data = self._paddingBuffer.read(payloadLen)
                msg = self._msgFactory.createWFPadMessage(data,
                                                         opcode=opcode,
                                                         args=args)
            else:
                log.debug("Message with padding.")
                data = self._paddingBuffer.read()
                paddingLen = payloadLen - dataLen
                msg = self._msgFactory.createWFPadMessage(data,
                                                         paddingLen,
                                                         opcode=opcode,
                                                         args=args)
        else:
            log.debug("Generate padding")
            self._consecPaddingMsgs += 1
            msg = self._msgFactory.createWFPadMessage("",
                                                     payloadLen,
                                                     flags=const.FLAG_PADDING,
                                                     opcode=opcode,
                                                     args=args)
        self.circuit.downstream.write(str(msg))

    def flushPieces(self):
        """Write the application data in chunks to the wire.

        After every write call, control is given back to the Twisted reactor.
        The function is called again after a certain delay, which is sampled
        from the time probability distribution.
        """
        if self.stopCondition():
            self.stopPadding()
            return

        self.encapsulateBufferData(opcode=self._opcode)
        self._opcode = None

        delay = self.drawFlushDelay()
        self._elapsed += delay

        reactor.callLater(delay, self.flushPieces)

    def drawMessageLength(self):
        """Return length for a specific message.

        The final countermeasure could override this method to,
        instead of drawing the delay from a probability distribution,
        iterate over a list to mimic a specific pattern of lengths.
        """
        return self._lengthProbdist.randomSample()

    def drawFlushDelay(self):
        """Return delay between calls to `flushPieces`.

        The final countermeasure could override this method to,
        instead of drawing the delay from a probability distribution,
        iterate over a list to mimic a specific pattern of delays.
        """
        return self._delayProbdist.randomSample()

    def processMessages(self, data):
        """Acts on extracted protocol messages based on header flags.

        Data is written to the local application and padding messages are
        filtered out from the stream.
        """
        log.debug("I'm going to parse protocol messages from data.")
        if (data is None) or (len(data) == 0):
            return

        # Try to extract protocol messages.
        msgs = self._msgExtractor.extract(data)
        for msg in msgs:
            if (msgs is None) or (len(msgs) == 0):
                return
            # Forward data to the application.
            if msg.flags == const.FLAG_DATA:
                log.debug("Data flag detected, relaying to data stream")
                self.circuit.upstream.write(msg.payload)
            # Filter padding messages out.
            elif msg.flags == const.FLAG_PADDING:
                log.debug("Padding message ignored.")
            elif msg.flags == const.FLAG_CONTROL:
                log.debug("Message with control data received.")
                self.circuit.upstream.write(msg.payload)
                self.receivedControlMessage(msg._opcode, msg.args)
            else:
                log.warning("Invalid message flags: %d." % msg.flags)
        return msgs

    def getConsecPaddingMsgs(self):
        """Return number of padding messages."""
        return self._consecPaddingMsgs

    def setConsecPaddingMsgs(self, numPaddingMsgs):
        """Set number of padding messages."""
        self._consecPaddingMsgs = numPaddingMsgs

    def getElapsed(self):
        """Return time _elapsed since padding started."""
        return self._elapsed

    def startPadding(self):
        """Changes protocol's state to ST_PADDING and starts timer."""
        self._state = const.ST_PADDING
        self._elapsed = 0
        self.flushPieces()

    def stopPadding(self):
        """Changes protocol's state to ST_CONNECTED and stops timer."""
        self._state = const.ST_CONNECTED
        self.flushPieces()

    def stopCondition(self):
        """Return the evaluation of the stop condition.

        We assume that the most general scheme is to be continuously padding.
        More sophisticated defenses try to reduce the overhead and set a
        stopping condition.
        """
        return False

    def flushSendBuffer(self):
        """Flush the application's queued data.

        The application could have sent data while we were busy authenticating
        the remote machine.  This method flushes the data which could have been
        queued in the meanwhile in `self._sendBuf'.
        """
        if len(self._sendBuf) == 0:
            log.debug("Send buffer is empty; nothing to flush.")
            return

        # Flush the buffered data, the application is so eager to send.
        log.debug("Flushing %d bytes of buffered application data." %
                  len(self._sendBuf))

        self.sendRemote(self._sendBuf)
        self._sendBuf = ""

    def runBeforeFlushing(self):
        """Perform the following operations before flushing the buffer.

        This method is called at the beginning of the flushPieces method. It
        might be used to eventually change the probability distributions used
        for sampling lengths and delays. An edge case could be to change the
        length and delay for each individual message to mimick some predefined
        traffic template.
        """
        pass

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream."""
        if self._state >= const.ST_CONNECTED:
            self.sendRemote(data.read())
        else:
            self._sendBuf += data.read()
            log.debug("Buffered %d bytes of outgoing data." %
                      len(self._sendBuf))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        if self._state >= const.ST_CONNECTED:
            self.processMessages(data.read())


class WFPadClient(WFPadTransport):
    """Extend the WFPad class."""

    def __init__(self):
        """Initialize a WFPadClient object."""
        WFPadTransport.__init__(self)


class WFPadServer(WFPadTransport):
    """Extend the WFPad class."""

    def __init__(self):
        """Initialize a WFPadServer object."""
        WFPadTransport.__init__(self)
