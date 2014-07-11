"""The wfpad module implements the Tor WF framework to develop WF defenses.

This module allows the development of various WF countermeasures based on
link-padding. It implements a faming layer to introduce dummy messages into
the stream and discard them at the other end.
"""
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message, socks_shim
from twisted.internet import reactor

import obfsproxy.common.log as logging
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.message import WFPadMessage
from sets import Set


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
        pass

    def onSessionEnds(self):
        """Do operations to be done when session ends."""
        pass


class WFPadTransport(BaseTransport):
    """Implements the Tor WF framework to develop WF countermeasures.

    This class implements methods which implement primitives and protocols
    specifications to further develop WF countermeasures.
    """
    def __init__(self):
        """Initialize a WFPadTransport object."""
        log.debug("Initializing %s." % const.TRANSPORT_NAME)

        super(WFPadTransport, self).__init__()

        # Initialize the protocol's state machine.
        self._state = const.ST_WAIT

        # Buffer for outgoing data.
        self.sendBuf = ""

        # Count time spent on padding
        self.elapsed = 0

        # Buffer used for padding.
        self.paddingBuffer = Buffer()

        # Counter for padding messages
        self.consecPaddingMsgs = 0

        # Opcode for messages
        self.opcode = None

        # Used to extract protocol messages from encrypted data.
        self.msgFactory = message.WFPadMessageFactory()
        self.msgExtractor = message.WFPadMessageExtractor()

        # Initialize probability distributions
        self.period = 0.1
        self.delayProbdist = probdist.new(lambda: self.period,
                                            lambda i, n, c: 1)
        self.psize = const.MTU
        self.lengthProbdist = probdist.new(lambda: self.psize,
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
        self.startPadding()

    def sendRemote(self, data, flags=const.FLAG_DATA):
        """Send data to the remote end once the connection is established.

        The given `data` is first encapsulated in protocol messages.  Then, the
        protocol message(s) are sent over the wire.  The argument `flags'
        specifies the protocol message flags.
        """
        log.debug("Processing %d bytes of outgoing data." % len(data))
        if self._state is const.ST_PADDING:
            self.paddingBuffer.write(data)

    def injectMessage(self, length=None, opcode=None, args=None):
        """Creates and injects WFPad messages in order to pad the link.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. Otherwise, we generate random padding
        and we send it over the wire in chunks.
        """
        msg = WFPadMessage()
        msgTotalLen = length if length else self.drawMessageLength()
        payloadLen = msgTotalLen - const.MIN_HDR_LEN
        dataLen = len(self.paddingBuffer)
        if dataLen > 0:
            log.debug("Flush buffer")
            if dataLen > payloadLen:
                log.debug("Message with no padding.")
                data = self.paddingBuffer.read(payloadLen)
                msg = self.msgFactory.createWFPadMessage(data,
                                                         opcode=opcode,
                                                         args=args)
            else:
                log.debug("Message with padding.")
                data = self.paddingBuffer.read()
                paddingLen = payloadLen - dataLen
                msg = self.msgFactory.createWFPadMessage(data,
                                                         paddingLen,
                                                         opcode=opcode,
                                                         args=args)
        else:
            log.debug("Generate padding")
            self.consecPaddingMsgs += 1
            msg = self.msgFactory.createWFPadMessage("",
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

        self.injectMessage(opcode=self.opcode)
        self.opcode = None

        delay = self.drawFlushDelay()
        self.elapsed += delay

        reactor.callLater(delay, self.flushPieces)

    def sendControlMessage(self, opcode, args, delay=0):
        """Send a message with a specific opcode field."""
        reactor.callLater(delay, self.injectMessage(opcode=opcode))

    def drawMessageLength(self):
        """Return length for a specific message.

        The final countermeasure could override this method to,
        instead of drawing the delay from a probability distribution,
        iterate over a list to mimic a specific pattern of lengths.
        """
        return self.lengthProbdist.randomSample()

    def drawFlushDelay(self):
        """Return delay between calls to `flushPieces`.

        The final countermeasure could override this method to,
        instead of drawing the delay from a probability distribution,
        iterate over a list to mimic a specific pattern of delays.
        """
        return self.delayProbdist.randomSample()

    def processMessages(self, data):
        """Acts on extracted protocol messages based on header flags.

        Data is written to the local application and padding messages are
        filtered out from the stream.
        """
        log.debug("I'm going to parse protocol messages from data.")
        if (data is None) or (len(data) == 0):
            return

        # Try to extract protocol messages.
        msgs = self.msgExtractor.extract(data)
        for msg in msgs:
            if (msgs is None) or (len(msgs) == 0):
                return
            for msg in msgs:
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
                    self.receivedControlMessage(msg.opcode, msg.args)
                else:
                    log.warning("Invalid message flags: %d." % msg.flags)
        return msgs

    def receivedControlMessage(self, opcode, args=None):
        """Do operation indicated by the opcode."""
        if opcode == const.OP_START:  # Generic primitives
            self.startPadding()
        elif opcode == const.OP_STOP:
            self.stopPadding()
        elif opcode == const.OP_IGNORE:
            self.sendIgnore()
        elif opcode == const.OP_SEND_PADDING:
            self.sendPadding(*args)
        elif opcode == const.OP_APP_HINT:
            self.sendAppHint(*args)
        elif opcode == const.OP_BURST_HISTO:  # Adaptive padding primitives
            self.sendBurstHistogram(*args)
        elif opcode == const.OP_GAP_HISTO:
            self.sendGapHistogram(*args)
        elif opcode == const.OP_INJECT_HISTO:
            self.sendInjectHistogram(*args)
        elif opcode == const.OP_TOTAL_PAD:  # CS-BuFLO primitives
            self.sendTotalPad(*args)
        elif opcode == const.OP_PAYLOAD_PAD:
            self.sendPayloadPad(*args)
        elif opcode == const.OP_BATCH_PAD:  # Tamaraw primitives
            self.sendBatchPad(*args)
        else:
            log.error("The received operation code is not recognized.")

    def sendIgnore(self):
        """Reply with a padding message."""
        reactor.callLater(0, self.injectMessage())

    def sendPadding(self, N, t):
        """Reply with `N` padding messages delayed `t` ms."""
        for _ in xrange(N):
            reactor.callLater(t, self.injectMessage())

    def sendAppHint(self, sessId, status):
        """Provides information to the server about the current session."""
        pass

    def sendBurstHistogram(self, histo, labels, remove_toks=False):
        """Replies to a burst_histo request.

        Parameters
        ----------
        histo : list
                contains delay distribution of sending an IGNORE packet after
                sending an *real* packet (with "Infinity" bin to indicate run
                termination probability).
        labels_ms : list
                    millisecond labels for the bins
        remove_toks : bool
                      if true, follow Adaptive Padding token removal rules.
                      If false, histograms are immutable.
        """
        pass

    def sendGapHistogram(self, histo, labels, remove_toks=False):
        """Replies to a gap_histo request.

        Parameters
        ----------
        histo : list
                contains delay distribution of sending an IGNORE packet after
                sending an IGNORE packet (with "Infinity" bin to indicate run
                termination probability).
        labels_ms : list
                    millisecond labels for the bins
        remove_toks : bool
                      if true, follow Adaptive Padding token removal rules.
                      If false, histograms are immutable.
        """
        pass

    def sendInjectHistogram(self, histo, labels):
        """Replies to an inject_histogram request.

        Parameters
        ----------
        histo : list
                contains probability distribution of sending an IGNORE packet
                if the wire was completely silent for that amount of time.
        labels_ms : list
                    millisecond labels for the bins

        Note: This is not an Adaptive Padding primitive, but it seems
        useful to model push-based protocols (like XMPP).
        """
        pass

    def sendTotalPad(self):
        pass

    def sendPayloadPad(self, sess_id, t):
        """Pad all batches to 2^K cells total.

        Pad all batches to 2^K cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    def sendBatchPad(self, sess_id, L, t):
        """Pad all batches to L cells total.

        Pad all batches to `L` cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    def getConsecPaddingMsgs(self):
        """Return number of padding messages."""
        return self.consecPaddingMsgs

    def setConsecPaddingMsgs(self, numPaddingMsgs):
        """Set number of padding messages."""
        self.consecPaddingMsgs = numPaddingMsgs

    def getElapsed(self):
        """Return time elapsed since padding started."""
        return self.elapsed

    def startPadding(self):
        """Changes protocol's state to ST_PADDING and starts timer."""
        self._state = const.ST_PADDING
        self.elapsed = 0
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
        queued in the meanwhile in `self.sendBuf'.
        """
        if len(self.sendBuf) == 0:
            log.debug("Send buffer is empty; nothing to flush.")
            return

        # Flush the buffered data, the application is so eager to send.
        log.debug("Flushing %d bytes of buffered application data." %
                  len(self.sendBuf))

        self.sendRemote(self.sendBuf)
        self.sendBuf = ""

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
        if self._state is const.ST_CONNECTED:
            self.circuit.downstream.write(data.read())
        elif self._state == const.ST_PADDING:
                self.sendRemote(data.read())
        else:
            self.sendBuf += data.read()
            log.debug("Buffered %d bytes of outgoing data." %
                      len(self.sendBuf))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        if self._state is const.ST_CONNECTED:
            self.circuit.upstream.write(data.read())
        elif self._state == const.ST_PADDING:
            self.processMessages(data.read())
        else:
            self.flushSendBuffer()


class WFPadClient(WFPadTransport):
    """Extend the WFPad class."""

    def __init__(self):
        """Initialize a WFPadClient object."""
        WFPadTransport.__init__(self)


class WFPadServer(WFPadTransport):
    """Extend the WFPad class."""

    def __init__(self):
        print "Starting", id(self)
        """Initialize a WFPadServer object."""
        WFPadTransport.__init__(self)
