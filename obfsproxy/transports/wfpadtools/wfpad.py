"""The wfpad module implements the WFPadTools pluggable transport.

This module implements WFPadTools, a framework to develop link-padding-based
WF countermeasures in Tor. It implements a faming layer for the Tor protocol
that allows to introduce cover traffic and provides a set of primitives that
can be used to implement more specific anti-website fingerprinting strategies.

To use this framework, developers can extend the WFPadTransport, WFPadClient
and WFPadServer classes and use their methods to implement the countermeasure.


Possible primitives WFPadTools allows for:

- Since each end runs a transport itself, it allows to implement strategies
  that treat incoming and outgoing traffic independently.

- It allows to choose the inter-arrival time as a constant or to specify a
  probability distribution to draw values from it for each individual message.
  By default, the size of the packets are always padded to the MTU but one
  could also specify a different value or specify a probability distribution
  to draw packet lengths to pad to at each message.

- 

Important note: this framework is intended for research purposes and it has the
following limitations:

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

- Right now it cannot be used stand-alone (to obfuscate applications other
  than Tor, for instance).

"""
import json
import random
from sets import Set
from twisted.internet import reactor

import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message, socks_shim
from obfsproxy.transports.wfpadtools import util as ut
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.message import WFPadMessage, getOpcodeNames

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
        self.wfpad._numMessages = [0, 0]

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
    _sessId = 0
    _sendBuf = ""  # Buffer for outgoing data while transport is not connected.
    _elapsed = 0  # Counts time spent on padding.
    _consecPaddingMsgs = 0  # Counts number of consecutive padding messages.
    _visiting = False  # Flags a visit to a page.
    _currentArgs = ""  # Arguments of the current control message.
    _numMessages = [0, 0]  # Count total number of messages (snt, rcv)
    _burstHisto = {'rcv': None, 'snd': None}
    _gapHisto = {'rcv': None, 'snd': None}

    def __init__(self):
        """Initialize a WFPadTransport object."""
        log.debug("[wfad] Initializing %s (id=%s)." % (const.TRANSPORT_NAME,
                                                       str(id(self))))
        super(WFPadTransport, self).__init__()

        # Initialize the protocol's state machine.
        self._state = const.ST_WAIT

        # Buffer used for padding.
        self._paddingBuffer = Buffer()

        # Used to extract protocol messages from encrypted data.
        self._msgFactory = message.WFPadMessageFactory()
        self._msgExtractor = message.WFPadMessageExtractor()

        # Initialize probability distributions
        self._period = 0.1
        self._delayProbdist = probdist.new(lambda i, n, c: self._period,
                                            lambda i, n, c: 1)
        self._psize = const.MTU
        self._lengthProbdist = probdist.new(lambda i, n, c: self._psize,
                                             lambda i, n, c: 1)

        # Run this method to evaluate the stop condition
        # The default condition is to pad continuously.
        # More sophisticated defenses would reduce the
        # overhead by setting more sophisticated stopping conditions.
        self.stopCondition = lambda s: False

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
        msgsStr = "".join([str(msg) for msg in messages])
        self.circuit.downstream.write(msgsStr)

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
            self._numMessages[0] += len(msgs)
            self.sendMessagesDownstream(msgs)

    def sendMessage(self, payload="", paddingLen=0, flags=const.FLAG_DATA):
        """Send message over the wire."""
        msg = self._msgFactory.createWFPadMessage(payload, paddingLen, flags)
        self._numMessages[0] += 1
        self.sendMessagesDownstream([msg])

    def sendIgnore(self):
        """Simple fixed-length (CELL_SIZE) padding cell."""
        self.sendMessage(payload="",
                         paddingLen=const.MPU,
                         flags=const.FLAG_PADDING)

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
        msg = WFPadMessage()
        msgTotalLen = length if length else self.drawMessageLength()
        payloadLen = msgTotalLen - const.MIN_HDR_LEN
        dataLen = len(self._paddingBuffer)
        self._numMessages[0] += 1
        # If there is data in buffer, encapsulate and send them.
        if dataLen > 0:
            self._consecPaddingMsgs = 0
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

        # Return if the stopping condition is satisfied.
        if self.stopCondition(self):
            self.stopPadding()
            return
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
        try:
            msgs = self._msgExtractor.extract(data)
        except Exception, e:
            print str(e)
            log.exception("[wfpad] Exception extracting "
                          "messages from stream: %s" % str(e))
        self._numMessages[1] += len(msgs)
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

                if msg.args:
                    log.debug("[wfad] Message with control data received.")
                    self._currentArgs += msg.args
                    # We need to wait until we have all the args
                    if msg.totalArgsLen == len(self._currentArgs):
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
        if self._state is const.ST_PADDING:
            self._state = const.ST_CONNECTED

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream.

        Whenever data from Tor arrives, push it if we are already
        connected, or buffer it meanwhile otherwise.
        """
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            self.flushSendBuffer()
            self.pushData(d)
        else:
            self._sendBuf += d
            log.debug("[wfad] Buffered %d bytes of outgoing data." %
                      len(self._sendBuf))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            self.processMessages(d)

    #==========================================================================
    # Methods to deal with control messages
    #==========================================================================
    def receiveControlMessage(self, opcode, args=None):
        """Do operation indicated by the _opcode."""
        log.debug("Received control message with opcode %d and args: %s"
                  % (opcode, args))
        if opcode == const.OP_START:
            self.startPadding()
        elif opcode == const.OP_STOP:
            self.stopPadding()

        # Generic primitives
        if opcode == const.OP_IGNORE:
            self.relayIgnore()
        elif opcode == const.OP_SEND_PADDING:
            self.relaySendPadding(*args)
        elif opcode == const.OP_APP_HINT:
            self.relayAppHint(*args)

        # Adaptive padding primitives
        elif opcode == const.OP_BURST_HISTO:
            self.relayBurstHistogram(*args)
        elif opcode == const.OP_GAP_HISTO:
            self.gapHistogram(*args)

        # CS-BuFLO primitives
        elif opcode == const.OP_TOTAL_PAD:
            self.relayTotalPad(*args)
        elif opcode == const.OP_PAYLOAD_PAD:
            self.relayPayloadPad()

        # Tamaraw primitives
        elif opcode == const.OP_BATCH_PAD:
            self.relayBatchPad(*args)
        else:
            log.error("The received operation code is not recognized.")

#==============================================================================
# WFPad Primitives proposed by Mike Perry
# (https://lists.torproject.org/pipermail/tor-dev/2014-July/007246.html)
#==============================================================================

    def relaySendPadding(self, N, t):
        """Send the requested number of padding cells in response.

        Parameters
        ----------
        N : int
            Number of padding cells to send in response to this cell.
        t : int
            Number of microseconds delay before sending.
        """
        log.debug("[wfpad] - Sending %s padding cells after %t delay in "
                  "response to a %s control message."
                  % (N, t, getOpcodeNames(const.OP_SEND_PADDING)))
        for _ in xrange(N):
            reactor.callLater(t, self.sendIgnore)

    def relayAppHint(self, sessId, status):
        """A hint from the application layer for session start/end.

        Parameters
        ----------
        sessId : str
                 Identifies the session (e.g., keyed hash of URL bar domain).
        status : bool
                 True or False, indicating session start and end respectively.
        """
        log.debug("[wfpad] - Setting sessId to %s and visiting to %s "
                  "in response to a %s control message."
                  % (sessId, status, getOpcodeNames(const.OP_SEND_PADDING)))
        self._sessId = sessId
        self._visiting = status

    def relayBurstHistogram(self, histo, labels, removeToks=False,
                            interpolate=True, when="rcv"):
        """Specify histogram encoding the delay distribution.

        The delay distribution represents the probability of sending a single
        padding packet after a given delay in response to either an upstream
        cell, or a client-originating cell.

        Parameters
        ----------
        histo : list
            Contains delay distribution of sending an IGNORE cell after
            sending an IGNORE cell.
        labels : list
            Millisecond labels for the bins (with "infinity" bin to allow
            encoding the probability of not sending any padding packet in
            response to this packet).
        removeToks : bool
            If True, follow Adaptive Padding token removal rules.
            If False, histograms are immutable.
        interpolate : bool
            If True, randomize the delay uniformly between bin labels
            If False, use bin labels as exact delay values.
        when : str
            If set to "rcv", this histogram governs the probability of
            sending a padding packet after some delay in response to a packet
            originating from the client. If set to "snd", this histogram
            governs padding packets that are transmitted after a packet
            arrives from upstream (the middle node). In both cases, the
            padding packet is sent in the direction of the client.
        """
        def genSingletonBurst(index, bins, accumProb):
            if interpolate and index < bins - 1:
                    return random.choice(xrange(labels[index],
                                                labels[index + 1]))
            return labels[index]

        def genProbSignletonBurst(index, bins, accumProb):
            return histo[index]

        self._burstHisto[when] = probdist.new(genSingletonBurst,
                                              genProbSignletonBurst,
                                              bins=len(histo) - 1)

    def gapHistogram(self, histo, labels, removeToks=False,
                            interpolate=True, when="rcv"):
        """Specify histogram that encodes the delay distribution

        The delay distribution represents the probability of sending a
        single additional padding packet after a given delay following
        a padding packet that originated at this hop. In both cases, the
        padding packet is sent in the direction of the client.

        Parameters
        ----------
        histo : list
            Contains delay distribution of sending an IGNORE cell after
            sending an IGNORE cell.
        labels : list
            Millisecond labels for the bins (with "infinity" bin to allow
            encoding the probability of not sending any padding packet in
            response to this packet).
        removeToks : bool
            If True, follow Adaptive Padding token removal rules.
            If False, histograms are immutable.
        interpolate : bool
            If True, randomize the delay uniformly between bin labels
            If False, use bin labels as exact delay values.
        when : str
            If "rcv", this histogram applies to locally-inserted padding
            packets that were initially sent in response to client-originated
            data.  If "snd", this histogram applies to packets sent in response
            to locally-inserted padding packets sent in response to upstream
            data. Note that this means that implementations must maintain this
            metadata as internal state as the system transitions from
            BURST_HISTOGRAM initiated padding into GAP_HISTOGRAM initiated
            padding.
        """
        def genSingletonGap(index, bins, accumProb):
            if interpolate and index < bins - 1:
                return random.choice(xrange(labels[index],
                                            labels[index + 1]))
            return labels[index]

        def genProbSignletonGap(index, bins, accumProb):
            return histo[index]

        self._gapHisto[when] = probdist.new(genSingletonGap,
                                            genProbSignletonGap,
                                            bins=len(histo) - 1)

    def relayTotalPad(self, sessId, t):
        """Pad all batches to nearest 2^K cells total or until session ends.

        Pads all batches to nearest 2^K cells total or until it receives a
        relayAppHint(sessId, False).

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        t : int
            The number of microseconds to wait between cells to consider them
            part of the same batch.
        """
        self._period = t
        self._sessId = sessId
        self._delayProbdist = probdist.new(lambda i, n, c: self._period,
                                            lambda i, n, c: 1)
        # Set the stop condition to satisfy that the number of messages
        # sent within the session is a power of 2 (otherwise it'll continue
        # padding until the closest one) and that the session has finished.
        self.stopCondition = lambda self: \
                (self._numMessages[0] & (self._numMessages[0] - 1)) == 0 \
                and not self._visiting

    def relayPayloadPad(self):
        pass

    def relayBatchPad(self, sessId, L, t):
        """Pad all batches of cells to `L` cells total.

        Pad all batches to `L` cells total or until it receives a
        relayAppHint(sessId, False).

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        L : int
            The multiple of cells to pad to.
        t : int
            The number of microseconds to wait between cells to consider them
            part of the same batch.
        """
        self._period = t
        self._sessId = sessId
        self._delayProbdist = probdist.new(lambda i, n, c: self._period,
                                            lambda i, n, c: 1)
        # Set the stop condition to satisfy that the number of messages
        # sent within the session is a multiple of parameter `L` and the
        # session has finished.
        self.stopCondition = lambda self: self._numMessages[0] % L == 0 \
                                    and not self._visiting

    #==========================================================================
    # Methods to send control messages
    #==========================================================================
    def sendControlMessage(self, opcode, args=None, delay=0):
        """Send a message with a specific _opcode field."""
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
        self.sendControlMessage(const.OP_APP_HINT, args=[sessId, status])

    def sendBurstHistogram(self, histo, labels, remove_toks=False):
        self.sendControlMessage(const.OP_BURST_HISTO,
                                args=[histo, labels, remove_toks])

    def sendGapHistogram(self, histo, labels, remove_toks=False):
        self.sendControlMessage(const.OP_GAP_HISTO,
                                args=[histo, labels, remove_toks])

    def sendTotalPadRequest(self, sess_id, K, t):
        """Send request to pad all batches to 2^K cells total."""
        self.sendControlMessage(const.OP_TOTAL_PAD, args=[sess_id, K, t])

    def sendPayloadPadRequest(self):
        """TODO: not clear whether this primitive is useful for Tor."""
        self.sendControlMessage(const.OP_PAYLOAD_PAD)

    def sendBatchPadRequest(self, sess_id, L, t):
        """Send request to pad batches to L cells."""
        self.sendControlMessage(const.OP_BATCH_PAD, args=[sess_id, L, t])


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
