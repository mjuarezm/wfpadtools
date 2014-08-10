"""The wfpad module implements the WFPadTools pluggable transport.

This module implements WFPadTools, a framework to develop link-padding-based
website fingerprinting countermeasures in Tor. It implements a faming layer for
the Tor protocol that allows to introduce cover traffic and provides a set of
primitives that can be used to implement more specific anti-website
fingerprinting strategies.

To use this framework, developers can extend the WFPadTransport, WFPadClient
and WFPadServer classes and use their methods to develop the pluggable
transport that implements their specific countermeasure.

In addition to a protocol to insert dummy messages in a stream of Tor data,
WFPadTools implements a set of primitives proposed by Mike Perry that have
been proposed in:

gitweb.torproject.org/user/mikeperry/torspec.git/blob/refs/heads/multihop-
padding-primitives:/proposals/ideas/xxx-multihop-padding-primitives.txt

These primitives have been extracted from existing website fingerprinting
designs within the research community, such as Tamaraw, CS-BuFLO and Adaptive
Padding. They have been generalized in order to allow for a larger set of
possible strategies.

Important features of the WFPadTools design:

- Since each end runs a transport itself, it allows to implement strategies
  that treat incoming and outgoing traffic independently.

- It allows to pad each specific message to a specified length or to specify
  a probability distribution to draw a value for the length each time.

- It allows to specify the following probability distributions for the delays
  after data messages and the delays after padding messages.

- It allows for constant-rate padding or to specify a distribution to draw
  values from it for each individual message.

- It allows to add padding as to traffic coming upstream (e.g., web server
  or Tor) and/or as a response to downstream traffic (coming from the other
  end). Distributions governing these can be specified independently.

Important note: this framework is intended for research purposes and it has the
following limitations:

- This module does not provide encryption. That is why it must be always
  combined with another transport that does provide it. For example, the
  transport that implements the final countermeasure by extending
  WFPadTransport might take care of this.

- It only pads until the bridge but in the typical website fingerprinting
  scenario, the adversary might be sitting on the entry guard. Any final
  website fingerprinting countermeasure should run padding until the middle
  node in order to protect against this threat model.

- For now we assume the user is browsing using a single tab. Right now the
  SOCKS shim proxy (socks_shim.py module) cannot distinguish SOCKS requests
  coming from different pages. In the future, in case these primitives are
  implemented in Tor, there might be easier ways to get this sort of
  application-level information.

- It provides tools for padding-based countermeasures. It cannot be used
  for other type of strategies.

- Right now it cannot be used stand-alone (to obfuscate applications other
  than Tor, for instance).

- This implementation might be vulnerable to timing attacks (exploit timing
  timing differences between padding messages vs data messages. Although
  there is a small random component (e.g., state of the network and use of
  resources), a final implementation should take care of that.

"""
import json
import random
from twisted.internet import reactor, task

import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport, PluggableTransportError
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message as mes
from obfsproxy.transports.wfpadtools import message, socks_shim
from obfsproxy.transports.wfpadtools import util as ut
import obfsproxy.transports.wfpadtools.const as const


log = logging.get_obfslogger()


class WFPadShimObserver(object):
    """Observer class for the SOCKS's shim.

    This class provides methods to signal the start and end of web sessions.
    It observes events from the proxy shim that indicate SOCKS requests from
    FF, and it counts the alive connections to infer the life of a session.
    """
    def __init__(self, instanceWFPadTransport):
        """Instantiates a new `WFPadShimObserver` object."""
        self.wfpad = instanceWFPadTransport
        self._connections = []
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
        log.debug("[wfad] Session %s begins." % self._sessId)
        self.wfpad._visiting = True
        self.wfpad._numMessages = {'rcv': 0, 'snd': 0}
        self.wfpad.onSessionStarts(self._sessId)

    def onSessionEnds(self):
        """Sets wfpad's `_visiting` flag to `False`."""
        log.debug("[wfad] Session %s ends." % self._sessId)
        self.wfpad._visiting = False
        self.wfpad.onSessionEnds(self._sessId)

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
    _lastMsgTimestamp = 0
    _consecPaddingMsgs = 0
    _visiting = False
    _numMessages = {'rcv': 0, 'snd': 0}
    _currentArgs = ""  # Arguments of the current control message.

    def __init__(self):
        """Initialize a WFPadTransport object."""
        log.debug("[wfad] Initializing %s (id=%s)."
                  % (const.TRANSPORT_NAME, str(id(self))))
        super(WFPadTransport, self).__init__()

        # Initialize the protocol's state machine
        self._state = const.ST_WAIT

        # Buffer used to queue pending data messages
        self._dataBuffer = Buffer()

        # Objects to extract and parse protocol messages
        self._msgFactory = message.WFPadMessageFactory()
        self._msgExtractor = message.WFPadMessageExtractor()

        # Default message iat and length
        self._period = 0.1
        self._length = const.MPU

        # Initialize deferred events
        self._deferData = None
        self._deferBurst = {'rcv': None, 'snd': None}
        self._deferGap = {'rcv': None, 'snd': None}

        # Initialize callbacks
        self._deferBurstCallback = {'rcv': lambda d: None,
                                    'snd': lambda d: None}
        self._deferGapCallback = {'rcv': lambda d: None,
                                  'snd': lambda d: None}

        # Initialize distributions to not pad
        self.setPaddingDisabled()

        # By default we don't pad message lengths
        self._lengthDataProbdist = probdist.uniform(const.INF_LABEL)

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
        if len(self._dataBuffer) > 0:
            self.flushDataBuffer()

        if self.weAreClient:
            # To be implemented in the method that overrides `circuitConnected`
            # in the child class of the final countermeasure.
            pass

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
            raise RuntimeError("Attempted to send non-string"
                               " data over the wire.")

    def sendIgnore(self, paddingLength=const.MPU):
        """Send padding message.

        By default we send ignores at MTU size.
        """
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
        """Push `data` forward either to buffer or to the other end.

        If we draw a 0 time delay, we encapsulate and send data directly.
        Otherwise, we push data to data buffer and start flushing it.
        """
        log.debug("[wfad] Pushing %d bytes of outgoing data." % len(data))

        dataDelay = self._delayDataProbdist.randomSample()

        if dataDelay == 0:
            log.debug("[wfpad] Data message is not delayed.")
            self.sendDownstream(self._msgFactory.encapsulate(data))
        else:
            self._dataBuffer.write(data)
            log.debug("[wfad] Buffered %d bytes of outgoing data." %
                      len(self._dataBuffer))

            # Cancel existing deferred calls to padding this would also
            # cancel callbacks associated to these deferred objects
            if ut.isDeferActive(self._deferBurst['snd']) \
                            or ut.isDeferActive(self._deferGap['snd']):
                ut.cancelDefer(self._deferBurst['snd'])
                ut.cancelDefer(self._deferGap['snd'])
                reactorTime = reactor.seconds()  # @UndefinedVariable
                dataDelay -= reactorTime - self._lastMsgTimestamp
                log.debug("[wfpad] The deferred padding was cancelled. "
                          " started at %s and now is %s, so we dataDelay "
                          "msg %s sec." % (self._lastMsgTimestamp,
                                           reactorTime,
                                           dataDelay))

            if dataDelay < 0:
                dataDelay = 0
                log.warning("[wfpad] Delaying msg %ssec."
                           " Padding delays cannot be"
                           " shorter than data delays." % dataDelay)

            log.debug("[wfad] Flushing buffer after delay %s." % dataDelay)

            if not ut.isDeferActive(self._deferData):
                self._deferData = task.deferLater(reactor,
                                                     dataDelay,
                                                     self.flushDataBuffer)

    def flushDataBuffer(self):
        """Encapsulate data from buffer in messages and send over the link.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. When buffer is empty we decide whether we
        start padding.
        """
        dataLen = len(self._dataBuffer)
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
            self.sendDataMessage(self._dataBuffer.read(payloadLen))
        # If data in buffer does not fill the message's payload,
        # pad so that it reaches the specified length.
        else:
            paddingLen = payloadLen - dataLen
            self.sendDataMessage(self._dataBuffer.read(), paddingLen)
            log.debug("[wfad] Padding message to %d (adding %d)."
                      % (msgTotalLen, paddingLen))

        log.debug("[wfad] Sent data message of length %d." % msgTotalLen)

        self._lastMsgTimestamp = reactor.seconds()  # @UndefinedVariable

        # If buffer is empty, generate padding messages.
        if len(self._dataBuffer) > 0:
            dataDelay = self._delayDataProbdist.randomSample()
            self._deferData = self.deferLater(dataDelay, self.flushDataBuffer)
            log.debug("[wfpad]  data waiting in buffer, flushing again "
                      "after delay %s." % dataDelay)
        else:
            burstDelay = self._burstHistoProbdist['snd'].randomSample()
            self._deferBurst['snd'] = self.deferLater(burstDelay,
                                        self.sendPaddingSndHisto,
                                        self._deferBurstCallback['snd'])
            log.debug("[wfpad] buffer is empty, pad `snd` gap "
                      "after delay %s." % burstDelay)

    def deferLater(self, delay, fn, callback=None):
        if delay is not const.INF_LABEL:
            d = task.deferLater(reactor, delay, fn)
            if callback:
                d.addCallback(callback)
            return d

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
            print str(e)
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
                burstDelay = self._burstHistoProbdist['rcv'].randomSample()
                self._deferBurst['rcv'] = self.deferLater(burstDelay,
                                            self.sendPaddingRcvHisto,
                                            self._deferBurstCallback['rcv'])

                self._numMessages['rcv'] += 1
                # Forward data to the application.
                if msg.flags == const.FLAG_DATA:
                    log.debug("[wfad] Data flag detected, relaying upstream")
                    self.circuit.upstream.write(msg.payload)

                # Filter padding messages out.
                elif msg.flags == const.FLAG_PADDING:
                    log.debug("[wfad] Padding message ignored.")
                    pass

                # Otherwise, flag not recognized
                else:
                    log.error("Invalid message flags: %d." % msg.flags)

        return msgs

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
        if self.weAreClient:
            return self._sessionObserver.getSessId()
        else:
            return self._sessId

    def setConstantRatePadding(self, t):
        self._delayDataProbdist = probdist.uniform(t)
        self._burstHistoProbdist['snd'] = probdist.uniform(t)
        self._gapHistoProbdist['snd'] = probdist.uniform(t)

    def setPaddingDisabled(self):
        self._delayDataProbdist = probdist.uniform(0)
        self._burstHistoProbdist = {'rcv': probdist.uniform(const.INF_LABEL),
                                    'snd': probdist.uniform(const.INF_LABEL)}
        self._gapHistoProbdist = {'rcv': probdist.uniform(const.INF_LABEL),
                                  'snd': probdist.uniform(const.INF_LABEL)}

    def sendPaddingSndHisto(self):
        if self.stopCondition(self):
            return
        self.sendIgnore()
        self._consecPaddingMsgs += 1
        log.debug("[wfpad]  Sent ignore to pad snd burst.")
        gapDelay = self._gapHistoProbdist['snd'].randomSample()
        log.debug("[wfpad]  Wait for data, pad snd gap otherwise.")
        self._deferGap['snd'] = self.deferLater(gapDelay,
                                                self.sendPaddingSndHisto,
                                                self._deferGapCallback['snd'])

    def sendPaddingRcvHisto(self):
        if self.stopCondition(self):
            return
        self.sendIgnore()
        log.debug("[wfpad]  Sent ignore to pad rcv burst.")
        gapDelay = self._gapHistoProbdist['rcv'].randomSample()
        log.debug("[wfpad]  Wait for data, pad rcv gap otherwise.")
        self._deferGap['rcv'] = self.deferLater(gapDelay,
                                                self.sendPaddingRcvHisto,
                                                self._deferGapCallback['rcv'])

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream.

        Whenever data from Tor arrives, push it if we are already
        connected, or buffer it meanwhile otherwise.
        """
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            self.pushData(d)
        else:
            self._dataBuffer.write(d)
            log.debug("[wfad] Buffered %d bytes of outgoing data." %
                      len(self._dataBuffer))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            ut.cancelDefer(self._deferBurst['rcv'])
            ut.cancelDefer(self._deferGap['rcv'])
            self.processMessages(d)

    #==========================================================================
    # Methods to deal with control messages
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
            log.error("The received operation code is not recognized.")

#==============================================================================
# WFPad Primitives proposed by Mike Perry
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
        log.debug("[wfpad]  Sending %s padding cells after %s delay in "
                  "response to a %s control message."
                  % (N, t, mes.getOpcodeNames(const.OP_SEND_PADDING)))
        for _ in xrange(N):
            task.deferLater(reactor, t, self.sendIgnore)

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
        self._deferBurstCallback[when] = self._burstHistoProbdist[when]\
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
        self._deferGapCallback[when] = self._gapHistoProbdist[when]\
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
        self.setConstantRatePadding(t)
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
        self.setConstantRatePadding(t)
        # Set the stop condition to satisfy that the number of messages
        # sent within the session is a multiple of parameter `L` and the
        # session has finished.
        self.stopCondition = lambda self: self._numMessages[0] % L == 0 \
                                    and not self._visiting


class WFPadClient(WFPadTransport):

    def __init__(self):
        """Initialize a WFPadClient object."""
        WFPadTransport.__init__(self)


class WFPadServer(WFPadTransport):

    def __init__(self):
        """Initialize a WFPadServer object."""
        WFPadTransport.__init__(self)
