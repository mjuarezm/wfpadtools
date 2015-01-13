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

For further details on the protocol see /doc/wfpadtools/wfpadtools-spec.txt.

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
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message as mes
from obfsproxy.transports.wfpadtools import message, socks_shim
from obfsproxy.transports.wfpadtools import wfpad_shim
from twisted.internet import reactor, task
from twisted.internet.defer import CancelledError

import obfsproxy.common.log as logging
import obfsproxy.transports.wfpadtools.histo as hist
import obfsproxy.transports.wfpadtools.test_util as test_ut
import obfsproxy.transports.wfpadtools.const as const
import math
from time import time


log = logging.get_obfslogger()


class WFPadTransport(BaseTransport):
    """Implements the base class for the WFPadTools transport.

    This class provides the methods that implement primitives for
    different existing website fingerprinting countermeasures, and
    that can also be used to generate new ones.
    """

    enable_test = False
    dump_path = "/dev/null"

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

        # Variables to keep track of past messages
        self._lastSndTimestamp = 0
        self._consecPaddingMsgs = 0
        self._sentDataBytes = 0
        self._dataBytes = {'rcv': 0, 'snd': 0}
        self._totalBytes = {'rcv': 0, 'snd': 0}
        self._numMessages = {'rcv': 0, 'snd': 0}

        # Initialize length distribution
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
            _shim = socks_shim.get()
            self._sessionObserver = wfpad_shim.WFPadShimObserver(self)
            _shim.registerObserver(self._sessionObserver)
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
        subparser.add_argument("--test",
                               required=False,
                               type=str,
                               help="switch to enable test dumps.",
                               dest="test")
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
        if args.test:
            cls.enable_test = True
            cls.dump_path = args.test

    @classmethod
    def setup(cls, transportConfig):
        """Called once when obfsproxy starts."""
        if cls.__name__ is "WFPadTransport":
            log.info("\n\n"
                     "####################################################\n"
                     " WFPad alone isn't a Website Fingerprinting defense \n"
                     "####################################################\n")

        # Check whether this object is the client or the server
        cls.weAreClient = transportConfig.weAreClient
        cls.weAreServer = not cls.weAreClient

    def circuitDestroyed(self, reason, side):
        """Unregister the shim observer."""
        if self.weAreClient:
            _shim = socks_shim.get()
            if _shim.isRegistered(self._sessionObserver):
                _shim.deregisterObserver(self._sessionObserver)

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

    @test_ut.instrument_rcv_upstream
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

    @test_ut.instrument_class_method
    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            if self._deferBurst['rcv'] and not self._deferBurst['rcv'].called:
                self._deferBurst['rcv'].cancel()
            if self._deferGap['rcv'] and not self._deferGap['rcv'].called:
                self._deferGap['rcv'].cancel()
            return self.processMessages(d)

    def sendDownstream(self, data):
        """Sends `data` downstream over the wire."""
        if isinstance(data, str):
            self.circuit.downstream.write(data)
        elif isinstance(data, mes.WFPadMessage):
            data.sndTime = time()
            self.circuit.downstream.write(str(data))
            self._numMessages['snd'] += 1
            self._dataBytes['snd'] += len(data.payload)
            self._totalBytes['snd'] += data.totalLen
            return [data]
        elif isinstance(data, list):
            listMsgs = []
            for listElement in data:
                msg = self.sendDownstream(listElement)
                if msg:
                    listMsgs += msg
            return listMsgs
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
        self.sendDownstream(self._msgFactory.encapsulate("", opcode, args,
                                                         lenProbdist=self._lengthDataProbdist))

    def pushData(self, data):
        """Push `data` to the buffer or send it over the wire.

        Sample delay distribution for data messages. If we draw a 0 ms
        delay, we encapsulate and send data directly. Otherwise, we push data
        to the buffer and make a delayed called to flush it. In case the
        padding deferreds are active, we cancel them and update the delay
        accordingly.
        """
        log.debug("[wfad] Pushing %d bytes of outgoing data." % len(data))

        # Cancel existing deferred calls to padding methods to prevent
        # callbacks that remove tokens from histograms
        deferBurstCancelled = deferGapCancelled = False
        if self._deferBurst['snd'] and not self._deferBurst['snd'].called:
            self._deferBurst['snd'].cancel()
            deferBurstCancelled = True
        if self._deferGap['snd'] and not self._deferGap['snd'].called:
            self._deferGap['snd'].cancel()
            deferGapCancelled = True

        # Draw delay for data message
        delay = self._delayDataProbdist.randomSample()

        # Update delay according to elapsed time since last message
        # was sent. In case elapsed time is greater than current
        # delay, we sent the data message as soon as possible.
        if deferBurstCancelled or deferGapCancelled:
            elapsed = self.elapsedSinceLastMsg()
            newDelay = delay - elapsed
            delay = 0 if newDelay < 0 else newDelay
            log.debug("[wfpad] New delay is %s" % delay)

        if deferBurstCancelled and hasattr(self._burstHistoProbdist['snd'], "histo"):
            self._burstHistoProbdist['snd'].removeToken(elapsed)
        if deferGapCancelled and hasattr(self._gapHistoProbdist['snd'], "histo"):
            self._gapHistoProbdist['snd'].removeToken(elapsed)

        if delay == 0:
            # Send data message over the wire
            self.sendDownstream(self._msgFactory.encapsulate(data, lenProbdist=self._lengthDataProbdist))
            log.debug("[wfpad] Data message has been sent without delay.")

        else:
            # Push data message to data buffer
            self._buffer.write(data)
            log.debug("[wfad] Buffered %d bytes of outgoing data w/ delay %sms"
                      % (len(self._buffer), delay))

            # In case we the buffer is not currently being flushed,
            # make a delayed call to the flushing method
            if not self._deferData or (self._deferData and self._deferData.called):
                self._deferData = deferLater(delay, self.flushBuffer)
                log.debug("[wfad] Delay buffer flush %s ms delay" % delay)

    def elapsedSinceLastMsg(self):
        elap = reactor.seconds() - self._lastSndTimestamp  # @UndefinedVariable
        log.debug("[wfpad] Cancel padding. Elapsed = %s ms" % elap)
        return elap

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
            return None

        # Try to extract protocol messages
        msgs = []
        try:
            msgs = self._msgExtractor.extract(data)
        except Exception, e:
            log.exception("[wfpad] Exception extracting "
                          "messages from stream: %s" % str(e))

        for msg in msgs:
            msg.rcvTime = time()
            if msg.flags & const.FLAG_CONTROL:
                # Process control messages
                self.circuit.upstream.write(msg.payload)
                self.receiveControlMessage(msg.opcode, msg.args)
            else:
                self.deferBurstPadding('rcv')
                self._numMessages['rcv'] += 1
                self._totalBytes['rcv'] += msg.totalLen
                # Forward data to the application.
                if not msg.flags & const.FLAG_PADDING:
                    log.debug("[wfad] Data flag detected, relaying upstream")
                    self._dataBytes['rcv'] += len(msg.payload)
                    self.circuit.upstream.write(msg.payload)

                # Filter padding messages out.
                elif msg.flags & const.FLAG_PADDING:
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
            self._lastSndTimestamp = reactor.seconds()  # @UndefinedVariable
        delay = self._gapHistoProbdist[when].randomSample()
        if delay is const.INF_LABEL:
            return
        log.debug("[wfpad]  Wait for data, pad snd gap otherwise.")
        self._deferGap[when] = deferLater(delay,
                                          self.sendPaddingHisto,
                                          when=when,
                                          cbk=self._deferGapCallback[when])
        return delay

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

    def onSessionEnds(self, sessId):
        """Send hint for session end.

        Interface to be extended at child classes that implement
        final website fingerprinting countermeasures.
        """
        if self.weAreClient:
            self.sendControlMessage(const.OP_APP_HINT,
                                    [self.getSessId(), False])

    def getSessId(self):
        """Return current session Id."""
        return self._sessId if self.weAreServer \
            else self._sessionObserver.getSessId()

    def isVisiting(self):
        """Return current session Id."""
        return self._visiting if self.weAreServer \
            else self._sessionObserver._visiting

    # ==========================================================================
    # Deal with control messages
    # ==========================================================================
    def receiveControlMessage(self, opcode, args=None):
        """Do operation indicated by the _opcode."""
        log.debug("Received control message with opcode %s and args: %s"
                  % (mes.getOpcodeNames(const.OP_SEND_PADDING), args))

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
            self.relayPayloadPad(*args)

        # Tamaraw primitives
        elif opcode == const.OP_BATCH_PAD:
            self.relayBatchPad(*args)
        else:
            log.error("[wfpad] - The received opcode is not recognized.")

    # ==========================================================================
    # WFPadTools Primitives
    # ==========================================================================

    def relaySendPadding(self, N, t):
        """Send the requested number of padding cells in response.

        Parameters
        ----------
        N : int
            Number of padding cells to send in response to this cell.
        t : int
            Number of milliseconds delay before sending.
        """
        millisec = t / const.SCALE
        for _ in xrange(N):
            deferLater(millisec, self.sendIgnore)

    def relayAppHint(self, sessId, status):
        """A hint from the application layer for session start/end.

        Parameters
        ----------
        sessId : str
                 Identifies the session (e.g., keyed hash of URL bar domain).
        status : bool
                 True or False, indicating session start and end respectively.
        """
        if self.weAreServer:
            self._visiting = status
        if status:
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
        self._burstHistoProbdist[when] = hist.new(histo, labels,
                                                  interpolate=interpolate,
                                                  removeToks=removeToks)
        self._deferBurstCallback[when] = self._burstHistoProbdist[when].removeToken

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
        self._gapHistoProbdist[when] = hist.new(histo, labels,
                                                interpolate=interpolate,
                                                removeToks=removeToks)
        self._deferGapCallback[when] = self._gapHistoProbdist[when].removeToken

    def relayTotalPad(self, sessId, t, msg_level=True):
        """Pad all batches to nearest 2^K cells total.

        Set the stop condition to satisfy that the number of messages
        sent within the session is a power of 2 (otherwise it will continue
        padding until the closest one) and that the session has finished.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        msg_level : bool
            Sets whether the data to pad is at message level or at byte level.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)
        to_pad = self._numMessages['snd'] \
            if msg_level else self._totalBytes['snd']

        def stopConditionTotalPad(s):
            if self.isVisiting():
                log.debug("[wfpad] - False stop condition, still visiting...")
                return False
            stopCond = to_pad > 0 and (to_pad & (to_pad - 1)) == 0
            log.debug("[wfpad] - Total pad stop condition is %s."
                      "\n Visiting: %s, Num snd msgs: %s"
                      % (stopCond, self.isVisiting(), self._numMessages))
            return stopCond
        self.stopCondition = stopConditionTotalPad

    def relayPayloadPad(self, sessId, t, msg_level=True):
        """Pad until the total sent data is multiple of 2^int(log(TOTAL_PAYLOAD))

        Set the stop condition to satisfy the number of messages (or bytes)
        sent within the session is a multiple of the parameter `L` and that the
        session has finished.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        msg_level : bool
            Sets whether the data to pad is at message level or at byte level.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)
        to_pad = self._numMessages['snd'] \
            if msg_level else self._totalBytes['snd']

        def stopConditionBatchPad(s):
            if self.isVisiting():
                log.debug("[wfpad] - False stop condition, still visiting...")
                return False
            L = math.pow(2, math.ceil(math.log(self._dataBytes['snd'], 2)))
            stopCond = to_pad > 0 and to_pad % L == 0
            log.debug("[wfpad] - Payload pad stop condition is %s."
                      "\n Visiting: %s, Num snd msgs: %s, L: %s"
                      % (stopCond, self.isVisiting(), self._numMessages, L))
            return stopCond
        self.stopCondition = stopConditionBatchPad

    def relayBatchPad(self, sessId, L, t, msg_level=True):
        """Pad all batches of cells to the nearest multiple of `L` cells/bytes total.

        Set the stop condition to satisfy the number of messages (or bytes)
        sent within the session is a multiple of the parameter `L` and that the
        session has finished.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        L : int
            The multiple of cells to pad to.
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        msg_level : bool
            Sets whether the data to pad is at message level or at byte level.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)
        to_pad = self._numMessages['snd'] \
            if msg_level else self._totalBytes['snd']

        def stopConditionBatchPad(s):
            if self.isVisiting():
                log.debug("[wfpad] - False stop condition, still visiting...")
                return False
            stopCond = to_pad > 0 and to_pad % L == 0
            log.debug("[wfpad] - Batch pad stop condition is %s."
                      "\n Visiting: %s, Num snd msgs: %s, L: %s"
                      % (stopCond, self.isVisiting(), self._numMessages, L))
            return stopCond
        self.stopCondition = stopConditionBatchPad


def deferLater(*args, **kargs):
    """Shortcut to twisted deferLater.

    It allows to call twisted deferLater and add callback and errback methods.
    """
    delay, fn = args[0], args[1]
    callback = None
    if 'cbk' in kargs:
        callback = kargs['cbk']
        del kargs['cbk']
    delayMiliseconds = delay / const.SCALE
    d = task.deferLater(reactor, delayMiliseconds, fn, *args[2:], **kargs)
    log.debug("[wfpad] - Defer call to %s after %sms delay."
              % (fn.__name__, delayMiliseconds))
    if callback:
        d.addCallback(callback)

    def errbackCancel(f):
        if f.check(CancelledError):
            log.debug("[wfpad] A deferred was cancelled.")
        else:
            raise f.raiseException()
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
