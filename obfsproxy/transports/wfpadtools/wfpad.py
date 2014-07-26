"""The wfpad module implements the WFPadTools pluggable transport.

This module implements WFPadTools, a framework to develop link-padding-based
WF countermeasures in Tor. It implements a faming layer for the Tor protocol
that allows to introduce cover traffic and provides a set of primitives that
can be used to implement more specific anti-website fingerprinting strategies.

To use this framework, developers can extend the WFPadTransport, WFPadClient
and WFPadServer classes and use their methods to implement the countermeasure.

Note: this framework is intended for research purposes and it has the following
limitations:

- This module does not provide obfuscation of its protocol signature. That is
  why it must be always combined with another transport that does provide it.
  For example, the child transport that implements the final countermeasure
  might take care of this.

- It only pads until the bridge but in the typical website fingerprinting
  scenario, the adversary might be sitting on the entry guard. Any final
  website fingerprinting countermeasure should run padding until the middle
  node in order to protect against this threat model.

- For now we assume the user is browsing using a single tab. Right now the
  SOCKS shim proxy (socks_shim.py module) cannot distinguish SOCKS requests
  coming from different pages. In the future, in case these primitives are
  ported to Tor, there might be easier ways to get this sort of information.

- It provides tools for padding-based countermeasure. It shouldn't be used
  for other type of strategies.

"""
import json
from sets import Set
from twisted.internet import reactor

import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message, socks_shim
from obfsproxy.transports.wfpadtools import util as ut
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.message import WFPadMessage

log = logging.get_obfslogger()


class WFPadShimObserver(object):
    """Observer class for the SOCKS's shim.

    This class provides methods to signal the start and end of web sessions.
    It observes events from the proxy shim that indicate SOCKS requests from
    FF, and it counts the alive connections to infer the life of a session.

    `onSessionStarts()` and `onSessionEnds()` methods provide an interface for
    transport classes implementing final WF countermeasures. These two methods
    might be extended by the observers defined in these child transports.
    """
    _sessId = 0
    _sessions = {}

    def __init__(self, instanceWFPadTransport):
        """Instantiates a new `ShimObserver` object."""
        self.wfpad = instanceWFPadTransport
        self._sessions = {}
        self._sessId = 0

    def getNumConnections(self, sessId):
        """Return the number of open connections for session `sessId`."""
        if sessId not in self._sessions:
            return 0
        return len(self._sessions[sessId])

    def onConnect(self, connId):
        """Add id of new connection to the set of open connections."""
        if self.getNumConnections(self._sessId) == 0:
            self._sessId += 1
            self.onSessionStarts(connId)
        if self._sessId in self._sessions:
            self._sessions[self._sessId].add(connId)
        else:
            self._sessions[self._sessId] = Set([connId])

    def onDisconnect(self, connId):
        """Remove id of connection to the set of open connections."""
        if self._sessId in self._sessions and \
            connId in self._sessions[self._sessId]:
                self._sessions[self._sessId].remove(connId)
        if self.getNumConnections(self._sessId) == 0:
            self.onSessionEnds(connId)
            if self._sessId in self._sessions:
                del self._sessions[self._sessId]

    def onSessionStarts(self, connId):
        """Sets wfpad's `_visiting` flag to `True`."""
        log.debug("[wfad] Session %d begins." % connId)
        self.wfpad._visiting = True

    def onSessionEnds(self, connId):
        """Sets wfpad's `_visiting` flag to `False`."""
        log.debug("[wfad] Session %d ends." % connId)
        self.wfpad._visiting = False


class WFPadTransport(BaseTransport):
    """Implements the base class for the WFPadTools transport.

    This class provides the methods that implement primitives for
    different existing website fingerprinting countermeasures, and
    that can be used to generate even new ones that have not been
    specified yet. This class also provides an interface for the
    responses to these primitives of the other end.
    """
    _sendBuf = ""  # Buffer for outgoing data while transport is not connected.
    _elapsed = 0  # Counts time spent on padding.
    _consecPaddingMsgs = 0  # Counts number of consecutive padding messages.
    _visiting = False  # Flags a visit to a page.
    _currentArgs = ""  # Arguments of the current control message.

    def __init__(self):
        """Initialize a WFPadTransport object."""
        log.debug("[wfad] Initializing %s." % const.TRANSPORT_NAME)
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

        # Get global shim object.
        if self.weAreClient and self.shim_args and not socks_shim.get():
            try:
                shim_port, socks_port = self.shim_args
                socks_shim.new(int(shim_port), int(socks_port))
            except Exception as e:
                log.error('Failed to initialize SOCKS shim: %s', e)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments fort the SOCKS shim."""
        subparser.add_argument('--socks-shim',
                               action='store',
                               dest='shim',
                               help='wfpad SOCKS shim (shim_port,socks_port)')
        super(WFPadTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Validates the arguments calling the parent's method."""
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
        # Note that this is not a WF defense by itself.
        log.info("\n\n"
                  "########################################################\n"
                  " WFPad isn't a Website Fingerprinting defense by itself.\n"
                  "########################################################\n")

        # Set whether we are a client or not.
        cls.weAreClient = transportConfig.weAreClient
        cls.weAreServer = not cls.weAreClient
        cls.weAreExternal = transportConfig.weAreExternal

    def circuitConnected(self):
        """Initiate handshake.

        This method is only relevant for clients since servers never initiate
        handshakes.
        # TODO: implement handshake
        """
        # Change state to ST_CONNECTED
        self._state = const.ST_CONNECTED

        # Once we are connected we can flush data accumulated in the buffer.
        self.flushSendBuffer()

    def flushSendBuffer(self):
        """Flush the application's queued data.

        The application could have sent data while we were busy authenticating
        the remote machine.  This method flushes the data which could have been
        queued in the meanwhile in `self._sendBuf'.
        """
        if len(self._sendBuf) == 0:
            log.debug("[wfad] Send buffer is empty; nothing to flush.")
            return

        # Flush the buffered data, the application is so eager to send.
        log.debug("[wfad] Flushing %d bytes of buffered application data." %
                  len(self._sendBuf))

        self.pushData(self._sendBuf)
        self._sendBuf = ""

    def sendMessagesDownstream(self, messages):
        """Sends `messages` over the wire.

        Cast messages to str, concatenate them and write them to downstream.
        """
        self.circuit.downstream.write("".join([str(msg) for msg in messages]))

    def pushData(self, data, opcode=None, args=None):
        """Push `data` forward either to a buffer or to the other end.

        If we're padding, we push data to the padding buffer. Otherwise, we
        encapsulate data into WFPad messages and send them downstream directly.
        """
        log.debug("[wfad] Processing %d bytes of outgoing data." % len(data))
        if self._state is const.ST_PADDING:
            self._paddingBuffer.write(data)
        else:
            msgs = self._msgFactory.createWFPadMessages(data,
                                            flags=const.FLAG_DATA,
                                            opcode=opcode,
                                            args=args)
            self.sendMessagesDownstream(msgs)

    def sendMessage(self, payload="", paddingLen=0, flags=const.FLAG_DATA):
        """Send message over the wire."""
        msg = self._msgFactory.createWFPadMessage(payload,
                                                   paddingLen,
                                                   flags)
        self.sendMessagesDownstream([msg])

    def sendControlMessages(self, opcode, args):
        """Send control messages."""
        msgs = self._msgFactory.createWFPadControlMessages(opcode, args)
        self.sendMessagesDownstream(msgs)

    def flushPaddingBuffer(self, length=None, opcode=None, args=None):
        """Reads from buffer and creates messages to send them over the link.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. Otherwise, we generate random padding
        and we send it over the wire in chunks.
        After every write call, control is given back to the Twisted reactor.
        The function is called again after a certain delay, which is sampled
        from the time probability distribution.
        """
        # Return if the stopping condition is satisfied.
        if self.stopCondition():
            self.stopPadding()
            return

        msg = WFPadMessage()
        msgTotalLen = length if length else self.drawMessageLength()
        payloadLen = msgTotalLen - const.MIN_HDR_LEN
        dataLen = len(self._paddingBuffer)

        # If there is data in buffer, encapsulate and send them.
        if dataLen > 0:
            log.debug("[wfad] Data found in buffer. Flush buffer.")

            # If data in buffer fills the specified length, we just
            # encapsulate and send the message.
            if dataLen > payloadLen:
                log.debug("[wfad] Message with no padding.")
                data = self._paddingBuffer.read(payloadLen)
                msg = self._msgFactory.createWFPadMessage(data,
                                                         opcode=opcode,
                                                         args=args)

            # If data in buffer does not fill the message's payload,
            # pad so that it reaches the specified length.
            else:
                log.debug("[wfad] Message with padding.")
                data = self._paddingBuffer.read()
                paddingLen = payloadLen - dataLen
                msg = self._msgFactory.createWFPadMessage(data,
                                                         paddingLen,
                                                         opcode=opcode,
                                                         args=args)

        # If buffer is empty, generate padding messages.
        else:
            log.debug("[wfad] Generate padding message.")
            self._consecPaddingMsgs += 1
            msg = self._msgFactory.createWFPadMessage("",
                                                     payloadLen,
                                                     flags=const.FLAG_PADDING,
                                                     opcode=opcode,
                                                     args=args)
        self.sendMessagesDownstream([msg])

        # Compute the delay for the next message.
        delay = self.drawFlushDelay()
        self._elapsed += delay
        reactor.callLater(delay, self.flushPaddingBuffer)

    def processMessages(self, data):
        """Extract WFPad protocol messages.

        Data is written to the local application and padding messages are
        filtered out.
        """
        log.debug("[wfad] Parse protocol messages from data.")

        # Make sure there actually is data to be parsed.
        if (data is None) or (len(data) == 0):
            return

        # Try to extract protocol messages.
        msgs = []
        print "XXX TRY...."
        try:
            msgs = self._msgExtractor.extract(data)
            print "XXX MSGS1:", msgs
        except Exception, e:
            print str(e)
            log.exception("[wfpad] Exception extracting "
                          "messages from stream: %s" % str(e))

        print "XXX MSGS", msgs
        for msg in msgs:

            if (msgs is None) or (len(msgs) == 0):
                return

            # Forward data to the application.
            if msg.flags == const.FLAG_DATA:
                log.debug("[wfad] Data flag detected, relaying to data stream")
                self.circuit.upstream.write(msg.payload)

            # Filter padding messages out.
            elif msg.flags == const.FLAG_PADDING:
                log.debug("[wfad] Padding message ignored.")
                pass

            # Process control messages
            elif msg.flags == const.FLAG_CONTROL:
                print "XXX OPCODE:", msg.opcode

                if msg.args:
                    print "XXX ARGS", msg.args
                    log.debug("[wfad] Message with control data received.")
                    self._currentArgs += msg.args
                    continue

                    # We need to wait until we have all the args
                    if not msg.argsTotalLen > len(self._currentArgs):
                        args = json.loads(self._currentArgs)
                        self.circuit.upstream.write(msg.payload)
                        self.receiveControlMessage(msg.opcode, args)
                        self._currentArgs = ""
                else:
                    self.receiveControlMessage(msg.opcode)

            # Otherwise, flag not recognized
            else:
                log.warning("Invalid message flags: %d." % msg.flags)

        return msgs

    def drawMessageLength(self):
        """Return length for a specific message.

        The final countermeasure could override this method to,
        instead of drawing the delay from a probability distribution,
        iterate over a list to mimic a specific pattern of lengths.
        """
        return self._lengthProbdist.randomSample()

    def drawFlushDelay(self):
        """Return delay between calls to `flushPaddingBuffer`.

        The final countermeasure could override this method to,
        instead of drawing the delay from a probability distribution,
        iterate over a list to mimic a specific pattern of delays.
        """
        return self._delayProbdist.randomSample()

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
        self.flushPaddingBuffer()

    def stopPadding(self):
        """Changes protocol's state to ST_CONNECTED and stops timer."""
        self._state = const.ST_CONNECTED
        self.flushPaddingBuffer()

    def stopCondition(self):
        """Return the evaluation of the stopping condition.

        We assume that the most general scheme is to be continuously padding.
        More sophisticated defenses try to reduce the overhead by setting a
        stopping condition.
        """
        return False

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream.

        Whenever data from Tor arrives, push it if we are already
        connected, or buffer it meanwhile otherwise.
        """
        d = data.read()
        print "UP"
        if self._state >= const.ST_CONNECTED:
            self.pushData(d)
        else:
            self._sendBuf += d
            log.debug("[wfad] Buffered %d bytes of outgoing data." %
                      len(self._sendBuf))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        d = data.read()
        print "DOWN", d
        if self._state >= const.ST_CONNECTED:
            self.processMessages(d)

    #==========================================================================
    # Methods to deal with control messages
    #==========================================================================
    def receiveControlMessage(self, opcode, args=None):
        """Do operation indicated by the _opcode."""
        print "RCVD CTRL", opcode

        log.error("Received control message with opcode %d and args: %s"
                  % (opcode, args))
        if opcode == const.OP_START:
            self.startPadding()
        elif opcode == const.OP_STOP:
            self.stopPadding()

        # Generic primitives
        if opcode == const.OP_IGNORE:
            self.sendIgnore()
        elif opcode == const.OP_SEND_PADDING:
            self.sendPadding(*args)
        elif opcode == const.OP_APP_HINT:
            self.appHint(*args)

        # Adaptive padding primitives
        elif opcode == const.OP_BURST_HISTO:
            self.burstHistogram(*args)
        elif opcode == const.OP_GAP_HISTO:
            self.gapHistogram(*args)
        elif opcode == const.OP_INJECT_HISTO:
            self.injectHistogram(*args)

        # CS-BuFLO primitives
        elif opcode == const.OP_TOTAL_PAD:
            self.totalPad(*args)
        elif opcode == const.OP_PAYLOAD_PAD:
            self.payloadPad(*args)

        # Tamaraw primitives
        elif opcode == const.OP_BATCH_PAD:
            self.batchPad(*args)
        else:
            log.error("The received operation code is not recognized.")

    def sendIgnore(self, N=1):
        """Reply with a padding message."""
        for _ in xrange(N):
            reactor.callLater(0, self.sendMessage,
                              payload="",
                              paddingLen=const.MPU,
                              flags=const.FLAG_PADDING)

    def sendPadding(self, N, t):
        """Reply with `N` padding messages delayed `t` ms."""
        print "XXX SENDIGNORE"
        self.sendIgnore(N)

    def appHint(self, sessId, status):
        """Provides information to the server about the current session.

        Limitation: we assume the user is browsing in a single tab.
        """
        print "APP HINT RECEIVED: ", sessId, status
        self._visiting = status

    def burstHistogram(self, histo, labels, remove_toks=False):
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

    def gapHistogram(self, histo, labels, remove_toks=False):
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

    def injectHistogram(self, histo, labels):
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

    def totalPad(self):
        pass

    def payloadPad(self, sess_id, t):
        """Pad all batches to 2^K cells total.

        Pad all batches to 2^K cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    def batchPad(self, sess_id, L, t):
        """Pad all batches to L cells total.

        Pad all batches to `L` cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    #==========================================================================
    # Methods to send control messages
    #==========================================================================
    def sendControlMessage(self, opcode, args=None, delay=0):
        """Send a message with a specific _opcode field."""
        print "XXX SNDCTRL", opcode
        reactor.callLater(delay,
                          self.sendControlMessages,
                          opcode=opcode,
                          args=args)

    def sendStartPaddingRequest(self):
        """Send a start padding as control message."""
        self.sendControlMessage(const.OP_START)

    def sendStopPaddingRequest(self):
        """Send a start padding as control message."""
        self.sendControlMessage(const.OP_STOP)

    def sendIgnoreRequest(self):
        """Send an ignore request as control message."""
        self.sendControlMessage(const.OP_IGNORE)

    def sendPaddingCellsRequest(self, N, t):
        """Send an ignore request as control message."""
        self.sendControlMessage(const.OP_SEND_PADDING,
                                args=[N, t])

    def sendAppHintRequest(self, sessNumber, status=True):
        """Send an app hint request as control message.

        We hash the session number, the PT object id and a timestamp
        in order to get a unique identifier.

        Parameters
        ----------
        sessNumber : int
        status : boolean
                indicates whether a session starts (True) or ends (False).
        """
        sessId = ut.hash_text(str(sessNumber)
                               + str(id(self))
                               + str(ut.timestamp()))
        print "SEND HINT!"
        self.sendControlMessage(const.OP_APP_HINT, args=[sessId, status])

    def sendBurstHistogram(self, histo, labels, remove_toks=False):
        self.sendControlMessage(const.OP_BURST_HISTO,
                                args=[histo, labels, remove_toks])

    def sendGapHistogram(self, histo, labels, remove_toks=False):
        self.sendControlMessage(const.OP_GAP_HISTO,
                                args=[histo, labels, remove_toks])

    def sendInjectHistogram(self, histo, labels):
        self.sendControlMessage(const.OP_INJECT_HISTO, args=[histo, labels])

    def sendTotalPadRequest(self):
        pass

    def sendPayloadPadRequest(self, sess_id, t):
        """Pad all batches to 2^K cells total.

        Pad all batches to 2^K cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    def sendBatchPadRequest(self, sess_id, L, t):
        pass


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
