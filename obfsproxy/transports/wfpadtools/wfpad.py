"""The wfpad module implements the WFPadTools Tor pluggable transport.

This module implements WFPadTools, a framework to develop link-padding-based
website fingerprinting countermeasures in Tor. It implements a faming layer for
the Tor protocol that allows to add cover traffic and provides a set of
primitives that can be used to implement more specific anti-website
fingerprinting strategies.

To use this framework, developers can extend the WFPadTransport, WFPadClient
and WFPadServer classes included in this module and use their methods to
develop the pluggable transport that implements the specific countermeasure.

In addition to a protocol to insert dummy messages in a stream of Tor data,
WFPadTools implements a set of primitives that have been proposed by Mike
Perry in:

gitweb.torproject.org/user/mikeperry/torspec.git/blob/refs/heads/multihop-
padding-primitives:/proposals/ideas/xxx-multihop-padding-primitives.txt

These primitives have been extracted from existing website fingerprinting
designs within the research community, such as Tamaraw, CS-BuFLO and Adaptive
Padding. They have been generalized in order to allow for a broader set of
possible strategies.

For further details see /doc/wfpadtools/wfpadtools-spec.txt.

Important features of the WFPadTools design:

- It allows to pad each specific message to a specified length or to specify
  a probability distribution to draw a value for the length each time.

- It allows to specify the probability distributions for delays after data
  messages and delays after padding messages.

- Since each end runs an instance of the transport, it allows to implement
  strategies that treat incoming and outgoing traffic independently.

- It allows for constant-rate padding by specifying uniform distributions for
  the delays and allows to specify a general stop condition for padding. This
  allows to implements strategies such as BuFLO, CS-BuFLO and Tamaraw.

- It allows to add padding in response to traffic coming upstream (e.g., web
  server or Tor) and/or in response to downstream traffic (coming from the
  other end). Distributions governing these two can be specified independently.

Important note: this framework is intended for research purposes and it has the
following limitations:

- This module does not provide encryption. That is why it must be always
  combined with another transport that does provide it. For example, the
  transport that implements the final countermeasure by extending
  WFPadTransport might take care of this.

- It only pads until the bridge but in a typical website fingerprinting
  scenario the adversary might be sitting on the entry guard. Any final
  website fingerprinting countermeasure should run padding until the middle
  node in order to protect against this threat model.

- For now we assume the user is browsing using a single tab. Right now the
  SOCKS shim proxy (socks_shim.py module) cannot distinguish SOCKS requests
  coming from different pages. In the future, in case these primitives are
  implemented in Tor, there might be easier ways to get this sort of
  application-level information.

- This implementation might be vulnerable to timing attacks (exploit timing
  timing differences between padding messages vs data messages. Although
  there is a small random component (e.g., state of the network and use of
  resources), a final implementation should take care of that.

- It provides tools for padding-based countermeasures. It cannot be used
  for other type of strategies.

- It cannot be used stand-alone (to obfuscate applications other
  than Tor, for instance).

"""
import json
from twisted.internet import reactor, task

import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message as mes
from obfsproxy.transports.wfpadtools import message, socks_shim
from obfsproxy.transports.wfpadtools import util as ut
import obfsproxy.transports.wfpadtools.const as const
from twisted.internet.defer import Deferred, CancelledError


log = logging.get_obfslogger()


class WFPadShimObserver(object):
    """Observer class for the SOCKS's shim.

    This class provides methods to signal the start and end of web sessions.
    It observes events from the proxy shim that indicate SOCKS requests from
    FF, and it counts the alive connections to infer the life of a session.
    """

    def __init__(self, instanceWFPadTransport):
        """Instantiates a new `WFPadShimObserver` object."""
        log.debug("[wfpad - shim obs] New instance of the shim observer.")
        self._wfpad = instanceWFPadTransport
        self._connections = []
        self._visiting = False
        self._sessId = 0

    def onConnect(self, connId):
        """Add id of new connection to list of open connections."""
        assert(connId not in self._connections)
        if len(self._connections) == 0:
            self._sessId += 1
            self.onSessionStarts()
        self._connections.append(connId)

    def onDisconnect(self, connId):
        """Remove id of connection from list of open connections."""
        assert(connId in self._connections)
        self._connections.remove(connId)
        if len(self._connections) == 0:
            self.onSessionEnds()

    def onSessionStarts(self):
        """Sets wfpad's `_visiting` flag to `True`."""
        log.debug("[wfpad - shim obs] Session %s begins." % self._sessId)
        self._visiting = True
        self._wfpad._numMessages = {'rcv': 0, 'snd': 0}
        self._wfpad.onSessionStarts(self._sessId)

    def onSessionEnds(self):
        """Sets wfpad's `_visiting` flag to `False`."""
        log.debug("[wfpad - shim obs] Session %s ends." % self._sessId)
        self._visiting = False
        self._wfpad.onSessionEnds(self._sessId)

    def getSessId(self):
        """Return a hash of the current session id.

        We concatenate with a timestamp to get a unique session Id.
        In the final countermeasure we can hash the URL to set particular
        padding strategies for individual pages.
        """
        return ut.hash_text(str(self._sessId) + str(ut.timestamp()))


class WFPadTransport(BaseTransport):
    """Implements the base class for the WFPadTools transport.

    This class provides the methods that implement primitives for
    different existing website fingerprinting countermeasures, and
    that can also be used to generate new ones.
    """

    def __init__(self):
        """Initialize a WFPadTransport object."""
        log.debug("[wfad] Initializing %s (id=%s)."
                  % (const.TRANSPORT_NAME, str(id(self))))
        super(WFPadTransport, self).__init__()

        # Initialize the protocol's state machine
        self._state = const.ST_WAIT

        # Buffer used to queue pending data messages
        self._buffer = Buffer()

        # Objects to extract and parse protocol messages
        self._msgFactory = message.WFPadMessageFactory()
        self._msgExtractor = message.WFPadMessageExtractor()

        # Default message iat and length
        self._period = 0.1
        self._length = const.MPU

        # Variables to keep track of past messages
        self._lastSndTimestamp = 0
        self._consecPaddingMsgs = 0
        self._numMessages = {'rcv': 0, 'snd': 0}

        # Initialize length distribution (don't pad by default)
        self._lengthDataProbdist = probdist.uniform(const.INF_LABEL)

        # Initialize delay distributions (for data and gap/burst padding)
        # By default we don't insert any dummy message and the delay for
        # data messages is always zero
        self._delayDataProbdist = probdist.uniform(0)
        self._burstHistoProbdist = {'rcv': probdist.uniform(const.INF_LABEL),
                                    'snd': probdist.uniform(const.INF_LABEL)}
        self._gapHistoProbdist = {'rcv': probdist.uniform(const.INF_LABEL),
                                  'snd': probdist.uniform(const.INF_LABEL)}

        # Initialize deferred events. The deferreds are called with the delay
        # sampled from the probability distributions above
        self._deferData = None
        self._deferBurst = {'rcv': None, 'snd': None}
        self._deferGap = {'rcv': None, 'snd': None}

        # Initialize deferred callbacks.
        self._deferBurstCallback = {'rcv': lambda d: None,
                                    'snd': lambda d: None}
        self._deferGapCallback = {'rcv': lambda d: None,
                                  'snd': lambda d: None}

        # This method is evaluated to decide when to stop padding
        self.stopCondition = lambda Self: False

        # Get the global shim object
        if self.weAreClient:
            if not socks_shim.get():
                socks_shim.new(*self.shim_ports)
            shim = socks_shim.get()
            self._sessionObserver = WFPadShimObserver(self)
            shim.registerObserver(self._sessionObserver)
        else:
            self._sessId = 0
            self._visiting = False

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
        """Parse arguments for the shim.

        It also validates the other arguments by calling the parent's method.
        """
        parentalApproval = super(
            WFPadTransport, cls).validate_external_mode_cli(args)

        if not parentalApproval:
            raise PluggableTransportError(
                "Pluggable Transport args invalid: %s" % args)

        cls.shim_ports = (const.SHIM_PORT, const.SOCKS_PORT)
        if args.shim:
            cls.shim_ports = map(int, args.shim.split(','))

    @classmethod
    def setup(cls, transportConfig):
        """Called once when obfsproxy starts."""
        log.info("\n\n"
                  "########################################################\n"
                  " WFPad isn't a Website Fingerprinting defense by itself.\n"
                  "########################################################\n")

        # Check whether this object is the client or the server
        cls.weAreClient = transportConfig.weAreClient
        cls.weAreServer = not cls.weAreClient

    def circuitDestroyed(self, reason, side):
        """Unregister the shim observer."""
        if self.weAreClient:
            shim = socks_shim.get()
            if shim.isRegistered(self._sessionObserver):
                shim.deregisterObserver(self._sessionObserver)

    def circuitConnected(self):
        """Initiate handshake.

        This method is only relevant for clients since servers never initiate
        handshakes. The handshake must be extended by the final countermeasure
        to initialize the histograms that govern the delay distributions at the
        server side, for example.
        """
        # Change state to ST_CONNECTED
        self._state = const.ST_CONNECTED
        log.debug("[wfpad] Connected with the other WFPad end.")

        # Once we are connected we can flush data accumulated in the buffer.
        if len(self._buffer) > 0:
            self.flushBuffer()

        if self.weAreClient:
            # To be implemented in the method that overrides `circuitConnected`
            # in the child class of the final countermeasure. We can use
            # primitives in this transport to initialize the probability
            # distributions to be used at the server.
            pass

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream.

        Whenever data from Tor arrives, push it if we are already
        connected, or buffer it meanwhile otherwise.
        """
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            self.pushData(d)
        else:
            self._buffer.write(d)
            log.debug("[wfad] Buffered %d bytes of outgoing data." %
                      len(self._buffer))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            if self._deferBurst['rcv'] and not self._deferBurst['rcv'].called:
                self._deferBurst['rcv'].cancel()
            if self._deferGap['rcv'] and not self._deferGap['rcv'].called:
                self._deferGap['rcv'].cancel()
                self._deferBurst['rcv'].Deferred()
            self.processMessages(d)

    def sendDownstream(self, data):
        """Sends `data` downstream over the wire."""
        if isinstance(data, str):
            self.circuit.downstream.write(data)
        elif isinstance(data, mes.WFPadMessage):
            self.circuit.downstream.write(str(data))
            self._numMessages['snd'] += 1
        elif isinstance(data, list):
            for listElement in data:
                self.sendDownstream(listElement)
        else:
            raise RuntimeError("Attempted to send non-string data.")

    def sendIgnore(self, paddingLength=None):
        """Send padding message.

        By default we send ignores at MTU size.
        """
        if not paddingLength:
            paddingLength = const.MPU
        log.debug("[wfpad] Sending ignore message.")
        self.sendDownstream(self._msgFactory.newIgnore(paddingLength))

    def sendDataMessage(self, payload="", paddingLen=0):
        """Send data message."""
        log.debug("[wfpad] Sending data message with %s bytes payload"
                  " and %s bytes padding" % (len(payload), paddingLen))
        self.sendDownstream(self._msgFactory.new(payload, paddingLen))

    def sendControlMessage(self, opcode, args):
        """Send control message."""
        if self.weAreServer:
            raise Exception("[wfpad ] Server cannot send control messages.")
        log.debug("[wfpad] Sending control message: opcode=%s, args=%s."
                  % (opcode, args))
        self.sendDownstream(self._msgFactory.newControl(opcode, args))

    def pushData(self, data):
        """Push `data` to the buffer or send it over the wire.

        Sample delay distribution for data messages. If we draw a 0 seconds
        delay, we encapsulate and send data directly. Otherwise, we push data
        to the buffer and make a delayed called to flush it. In case the
        padding deferreds are active, we cancel them and update the delay
        accordingly.
        """

        log.debug("[wfad] Pushing %d bytes of outgoing data." % len(data))

        # Cancel existing deferred calls to padding methods to prevent
        # callbacks that remove tokens from histograms
        deferCancelled = False
        if self._deferBurst['snd'] and not self._deferBurst['snd'].called:
            self._deferBurst['snd'].cancel()
            deferCancelled = True
        if self._deferGap['snd'] and not self._deferGap['snd'].called:
            self._deferGap['snd'].cancel()
            deferCancelled = True

        # Draw delay for data message
        delay = self._delayDataProbdist.randomSample()

        # Update delay according to elapsed time since last message
        # was sent. In case elapsed time is greater than current
        # delay, we sent the data message as soon as possible.
        if deferCancelled:
            elapsed = self.elapsedSinceLastMsg()
            newDelay = delay - elapsed
            delay = 0 if newDelay < 0 else newDelay
            log.debug("[wfpad] New delay is %s" % delay)

        if delay == 0:
            # Send data message over the wire
            self.sendDownstream(self._msgFactory.encapsulate(data))
            log.debug("[wfpad] Data message has been sent without delay.")

        else:
            # Push data message to data buffer
            self._buffer.write(data)
            log.debug("[wfad] Buffered %d bytes of outgoing data."
                      % len(self._buffer))

            # In case we the buffer is not currently being flushed,
            # make a delayed call to the flushing method
            if self._deferData.called:
                self._deferData = deferLater(delay, self.flushBuffer)
                log.debug("[wfad] Delay buffer flush %s sec." % delay)

    def elapsedSinceLastMsg(self):
        elapsed = reactor.seconds() - self._lastSndTimestamp
        log.debug("[wfpad] Cancel padding. Elapsed = %s sec" % elapsed)
        return elapsed

    def flushBuffer(self):
        """Encapsulate data from buffer in messages and send over the link.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. When buffer is empty we decide whether we
        start padding.
        """
        dataLen = len(self._buffer)
        assert(dataLen > 0)
        log.debug("[wfad] %s bytes of data found in buffer."
                  " Flushing buffer." % dataLen)

        payloadLen = self._lengthDataProbdist.randomSample()
        if payloadLen is const.INF_LABEL:
            payloadLen = const.MPU if dataLen > const.MPU else dataLen
        msgTotalLen = payloadLen + const.MIN_HDR_LEN

        self._consecPaddingMsgs = 0

        # If data in buffer fills the specified length, we just
        # encapsulate and send the message.
        if dataLen > payloadLen:
            self.sendDataMessage(self._buffer.read(payloadLen))
        # If data in buffer does not fill the message's payload,
        # pad so that it reaches the specified length.
        else:
            paddingLen = payloadLen - dataLen
            self.sendDataMessage(self._buffer.read(), paddingLen)
            log.debug("[wfad] Padding message to %d (adding %d)."
                      % (msgTotalLen, paddingLen))

        log.debug("[wfad] Sent data message of length %d." % msgTotalLen)

        self._lastSndTimestamp = reactor.seconds()  # @UndefinedVariable

        # If buffer is empty, generate padding messages.
        if len(self._buffer) > 0:
            dataDelay = self._delayDataProbdist.randomSample()
            self._deferData = deferLater(dataDelay, self.flushBuffer)
            log.debug("[wfpad]  data waiting in buffer, flushing again "
                      "after delay %s." % dataDelay)
        else:
            self.deferBurstPadding('snd')
            log.debug("[wfpad] buffer is empty, pad `snd` gap.")

    def processMessages(self, data):
        """Extract WFPad protocol messages.

        Data is written to the local application and padding messages are
        filtered out.
        """
        log.debug("[wfad] Parse protocol messages from data.")

        # Make sure there actually is data to be parsed
        if (data is None) or (len(data) == 0):
            return

        # Try to extract protocol messages
        msgs = []
        try:
            msgs = self._msgExtractor.extract(data)
        except Exception, e:
            log.exception("[wfpad] Exception extracting "
                          "messages from stream: %s" % str(e))

        for msg in msgs:
            if msg.flags == const.FLAG_CONTROL:
                # Process control messages
                args = None
                if msg.args:
                    log.debug("[wfad] Message with control data received.")
                    self._msgExtractor.totalArgs += msg.args
                    # We need to wait until we have all the args
                    if msg.totalArgsLen == len(self._msgExtractor.totalArgs):
                        args = json.loads(self._msgExtractor.totalArgs)
                        self._msgExtractor.totalArgs = ""
                self.circuit.upstream.write(msg.payload)
                self.receiveControlMessage(msg.opcode, args)

            else:
                self.deferBurstPadding('rcv')
                self._numMessages['rcv'] += 1
                # Forward data to the application.
                if msg.flags == const.FLAG_DATA:
                    log.debug("[wfad] Data flag detected, relaying upstream")
                    self.circuit.upstream.write(msg.payload)

                # Filter padding messages out.
                elif msg.flags == const.FLAG_PADDING:
                    log.debug("[wfad] Padding message ignored.")

                # Otherwise, flag not recognized
                else:
                    log.error("Invalid message flags: %d." % msg.flags)
        return msgs

    def deferBurstPadding(self, when):
        """Sample delay from corresponding distribution and wait for data.

        In case we have not received data after delay, we call the method
        `sendPaddingHisto` to send ignore packets and sample next delay.
        """
        burstDelay = self._burstHistoProbdist[when].randomSample()
        if burstDelay is not const.INF_LABEL:
            self._deferBurst[when] = deferLater(burstDelay,
                                         self.sendPaddingHisto,
                                         when=when,
                                         cbk=self._deferBurstCallback[when])

    def sendPaddingHisto(self, when):
        """Send ignore in response to up/downstream traffic and wait for data.

        We sample the delay to wait from the `when` gap prob distribution.
        We call this method again in case we don't receive data after the
        delay.
        """
        if self.stopCondition(self):
            return
        self.sendIgnore()
        if when is 'snd':
            self._consecPaddingMsgs += 1
            self._lastSndTimestamp = reactor.seconds()
        gapDelay = self._gapHistoProbdist[when].randomSample()
        if gapDelay is const.INF_LABEL:
            return
        log.debug("[wfpad]  Wait for data, pad snd gap otherwise.")
        self._deferGap[when] = deferLater(gapDelay,
                                                self.sendPaddingHisto,
                                                self._deferGapCallback[when])

    def constantRatePaddingDistrib(self, t):
        self._delayDataProbdist = probdist.uniform(t)
        self._burstHistoProbdist['snd'] = probdist.uniform(t)
        self._gapHistoProbdist['snd'] = probdist.uniform(t)

    def noPaddingDistrib(self):
        self._delayDataProbdist = probdist.uniform(0)
        self._burstHistoProbdist = {'rcv': probdist.uniform(const.INF_LABEL),
                                    'snd': probdist.uniform(const.INF_LABEL)}
        self._gapHistoProbdist = {'rcv': probdist.uniform(const.INF_LABEL),
                                  'snd': probdist.uniform(const.INF_LABEL)}

    def onSessionStarts(self, sessId):
        """Sens hint for session start.

        To be extended at child classes that implement
        final website fingerprinting countermeasures.
        """
        if self.weAreClient:
            self.sendControlMessage(const.OP_APP_HINT,
                                    [self.getSessId(), True])
        else:
            self._sessId = sessId
            self._visiting = True

    def onSessionEnds(self, sessId):
        """Send hint for session end.

        Interface to be extended at child classes that implement
        final website fingerprinting countermeasures.
        """
        if self.weAreClient:
            self.sendControlMessage(const.OP_APP_HINT,
                                [self.getSessId(), False])
        else:
            self._visiting = False

    def getSessId(self):
        """Return current session Id."""
        return self._sessId if self.weAreServer \
            else self._sessionObserver.getSessId()

    def isVisiting(self):
        """Return current session Id."""
        return self._visiting if self.weAreServer \
            else self._sessionObserver._visiting

    #==========================================================================
    # Deal with control messages
    #==========================================================================
    def receiveControlMessage(self, opcode, args=None):
        """Do operation indicated by the _opcode."""
        log.debug("Received control message with opcode %d and args: %s"
                  % (opcode, args))

        if self.weAreClient:
            raise Exception("Client cannot receive control messages.")

        # Generic primitives
        if opcode == const.OP_SEND_PADDING:
            self.relaySendPadding(*args)
        elif opcode == const.OP_APP_HINT:
            self.relayAppHint(*args)

        # Adaptive padding primitives
        elif opcode == const.OP_BURST_HISTO:
            self.relayBurstHistogram(*args)
        elif opcode == const.OP_GAP_HISTO:
            self.relayGapHistogram(*args)

        # CS-BuFLO primitives
        elif opcode == const.OP_TOTAL_PAD:
            self.relayTotalPad(*args)
        elif opcode == const.OP_PAYLOAD_PAD:
            self.relayPayloadPad()

        # Tamaraw primitives
        elif opcode == const.OP_BATCH_PAD:
            self.relayBatchPad(*args)
        else:
            log.error("[wfpad] - The received opcode is not recognized.")

    #==========================================================================
    # WFPadTools Primitives
    #==========================================================================

    def relaySendPadding(self, N, t):
        """Send the requested number of padding cells in response.

        Parameters
        ----------
        N : int
            Number of padding cells to send in response to this cell.
        t : int
            Number of microseconds delay before sending.
        """
        log.debug("[wfpad]  Sending %s padding cells after %s delay in "
                  "response to a %s control message."
                  % (N, t, mes.getOpcodeNames(const.OP_SEND_PADDING)))
        for _ in xrange(N):
            deferLater(t, self.sendIgnore)

    def relayAppHint(self, sessId, status):
        """A hint from the application layer for session start/end.

        Parameters
        ----------
        sessId : str
                 Identifies the session (e.g., keyed hash of URL bar domain).
        status : bool
                 True or False, indicating session start and end respectively.
        """
        log.debug("[wfpad]  Session %s will %s, "
                  "in response to a %s control message."
                  % (sessId,
                     "start" if status else "stop",
                     mes.getOpcodeNames(const.OP_APP_HINT)))
        self._visiting = status
        if status == True:
            self.onSessionStarts(sessId)
        else:
            self.onSessionEnds(sessId)

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
        self._deferBurstCallback[when] = self._burstHistoProbdist[when] \
                                                .removeToken()
        self._burstHistoProbdist[when] = probdist.new(histo=histo,
                                                      labels=labels,
                                                      interpolate=interpolate,
                                                      removeToks=removeToks)

    def relayGapHistogram(self, histo, labels, removeToks=False,
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
        self._deferGapCallback[when] = self._gapHistoProbdist[when] \
                                                .removeToken()
        self._gapHistoProbdist[when] = probdist.new(histo=histo,
                                                    labels=labels,
                                                    interpolate=interpolate,
                                                    removeToks=removeToks)

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
        self.constantRatePaddingDistrib(t)
        # Set the stop condition to satisfy that the number of messages
        # sent within the session is a power of 2 (otherwise it'll continue
        # padding until the closest one) and that the session has finished.
        self.stopCondition = lambda self: \
                (self._numMessages[0] & (self._numMessages[0] - 1)) == 0 \
                and not self._visiting

    def relayPayloadPad(self):
        """TODO: we don't have enough info about the spec to implement it."""
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
        self.constantRatePaddingDistrib(t)
        # Set the stop condition to satisfy that the number of messages
        # sent within the session is a multiple of parameter `L` and the
        # session has finished.
        self.stopCondition = lambda self: self._numMessages[0] % L == 0 \
                                    and not self._visiting


def deferLater(*args, **kargs):
    """Shortcut to twisted deferLater.

    It allows to call twisted deferLater and add callback and errback methods.
    """
    delay, fn = args[0], args[1]
    d = task.deferLater(reactor, delay, fn, args[2:], **kargs)
    if 'cbk' in kargs:
        d.addCallback(kargs['cbk'])

    def errbackCancel(e):
        if isinstance(e, CancelledError):
            log.debug("[wfpad] A deferred was cancelled.")
        else:
            raise e
    d.addErrback(errbackCancel)
    return d


class WFPadClient(WFPadTransport):

    def __init__(self):
        """Initialize a WFPadClient object."""
        WFPadTransport.__init__(self)


class WFPadServer(WFPadTransport):

    def __init__(self):
        """Initialize a WFPadServer object."""
        WFPadTransport.__init__(self)
