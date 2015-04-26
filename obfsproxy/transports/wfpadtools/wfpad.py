"""The wfpad module implements the WFPadTools Tor pluggable transport.

This module implements WFPadTools, a framework to develop link-padding-based
website fingerprinting countermeasures in Tor. It implements a framing layer
for the Tor protocol that allows to add cover traffic and provides a set of
primitives that can be used to implement more specific anti-website
fingerprinting strategies.

To use this framework, developers can extend the WFPadTransport, WFPadClient
and WFPadServer classes included in this module and use their methods to
develop the pluggable transport that implements the specific countermeasure.

In addition to a protocol to insert dummy messages in a stream of Tor data,
WFPadTools implements a set of primitives that have been proposed by Mike
Perry in:

gitweb.torproject.org/user/mikeperry/torspec.git/blob/refs/heads/multihop-padding-primitives:/proposals/ideas/xxx-multihop-padding-primitives.txt

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
import os
from os.path import isfile, join
import socket
import time

import psutil
from twisted.internet import reactor

from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools.common import deferLater
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.primitives import PaddingPrimitivesInterface
from obfsproxy.transports.wfpadtools.session import Session
from obfsproxy.transports.wfpadtools.util import fileutil
import obfsproxy.transports.wfpadtools.util.testutil as test_ut
from obfsproxy.transports.wfpadtools import message as mes
from obfsproxy.transports.wfpadtools import message, socks_shim
from obfsproxy.transports.wfpadtools import wfpad_shim
from obfsproxy.transports.wfpadtools.kist import estimate_write_capacity
from obfsproxy.transports.base import BaseTransport, PluggableTransportError


log = logging.get_obfslogger()


class WFPadTransport(BaseTransport, PaddingPrimitivesInterface):
    """Implements the base class for the WFPadTools transport.

    This class provides the methods that implement primitives for
    different existing website fingerprinting countermeasures, and
    that can also be used to generate new ones.
    """

    _session_logs = None

    enable_test = False
    dump_path = "/dev/null"

    shim_ports = None

    def __init__(self):
        """Initialize a WFPadTransport object."""
        super(WFPadTransport, self).__init__()

        # which end are we?
        self.end = "client" if self.weAreClient else "server"
        log.debug("[wfpad - %s] Initializing %s (id=%s).",
                  self.end, const.TRANSPORT_NAME, str(id(self)))

        # Initialize the protocol's state machine
        self._state = const.ST_WAIT

        # Buffer used to queue pending data messages
        self._buffer = Buffer()

        # Objects to extract and parse protocol messages
        self._msgFactory = message.WFPadMessageFactory()
        self._msgExtractor = message.WFPadMessageExtractor()

        # Get pid and process
        self.pid = os.getpid()
        self.process = psutil.Process(self.pid)
        self.connections = []
        self.downstreamSocket = None

        # Get the global shim object
        self._shim = None
        if self.weAreClient:
            self._sessionObserver = False

            if not socks_shim.get():
                if self.shim_ports:
                    socks_shim.new(*self.shim_ports)
                else:
                    socks_shim.new(const.SHIM_PORT, -1)
            self._shim = socks_shim.get()
            self._sessionObserver = wfpad_shim.WFPadShimObserver(self)
            self._shim.registerObserver(self._sessionObserver)
            if self.shim_ports:
                self._shim.listen()
        else:
            self._sessId = const.DEFAULT_SESSION
            self._visiting = False

        self._initialize_state()


    def _initialize_state(self):
        # Initialize session
        self.session = Session()

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

        # method to calculate total padding
        self.calculateTotalPadding = lambda Self: None


    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for the SOCKS shim."""
        subparser.add_argument('--socks-shim',
                               action='store',
                               dest='shim',
                               help='wfpad SOCKS shim (shim_port,socks_port)')
        subparser.add_argument("--test",
                               required=False,
                               type=str,
                               help="switch to enable test dumps.",
                               dest="test")
        subparser.add_argument("--session-logs",
                               required=False,
                               type=str,
                               help="switch to enable logs for session.",
                               dest="session_logs")
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

        cls.dest = args.dest if args.dest else None

        # By default, shim doesn't connect to socks
        if args.shim:
            cls.shim_ports = map(int, args.shim.split(','))
            log.debug("[wfpad] Shim ports: %s", cls.shim_ports)
        if args.test:
            cls.enable_test = True
            cls.dump_path = args.test
        if args.session_logs:
            cls._session_logs = args.session_logs

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
        if self.weAreClient and self._sessionObserver:
            _shim = socks_shim.get()
            if _shim.isRegistered(self._sessionObserver):
                _shim.deregisterObserver(self._sessionObserver)

    def circuitConnected(self):
        """Initiate handshake.

        The handshake must be extended by the final countermeasure to initialize the
        histograms that govern the delay distributions at the server side, for example.
        """
        # Change state to ST_CONNECTED
        self._state = const.ST_CONNECTED
        log.debug("[wfpad - %s] Connected with the other WFPad end.", self.end)

        # Once we are connected we can flush data accumulated in the buffer.
        if len(self._buffer) > 0:
            self.flushBuffer()

        # Get peer address
        self.peer_addr = self.circuit.downstream.peer_addr

        # Load sockets
        self.connections = self.process.get_connections()
        for pconn in self.connections:
            if pconn.status == 'ESTABLISHED' and pconn.raddr[1] == self.peer_addr.port:
                self.downstreamSocket = socket.fromfd(pconn.fd, pconn.family, pconn.type)
                break

    @test_ut.instrument_rcv_upstream
    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream.

        Whenever data from Tor arrives, push it if we are already
        connected, or buffer it meanwhile otherwise.
        """
        d = data.read()
        self.session.lastRcvUpstreamTs = reactor.seconds()

        if self._state >= const.ST_CONNECTED:
            self.pushData(d)
            self.whenReceivedUpstream()

        else:
            self._buffer.write(d)
            log.debug("[wfpad - %s] Buffered %d bytes of outgoing data.",
                      self.end, len(self._buffer))

    def whenReceivedUpstream(self):
        """Template method for child WF defense transport."""
        pass

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        d = data.read()
        if self._state >= const.ST_CONNECTED:
            self.whenReceivedDownstream()
            self.cancelDeferrers('rcv')
            return self.processMessages(d)

    def whenReceivedDownstream(self):
        """Template method for child WF defense transport."""
        pass

    def sendDownstream(self, data):
        """Sends `data` downstream over the wire."""
        if isinstance(data, str):
            self.circuit.downstream.write(data)
        elif isinstance(data, mes.WFPadMessage):
            data.sndTime = time.clock()
            self.circuit.downstream.write(str(data))
            log.debug("[wfpad - %s] A new message (flag=%s) sent!", self.end, data.flags)
            if not data.flags & const.FLAG_CONTROL:
                self.session.numMessages['snd'] += 1
                self.session.totalBytes['snd'] += data.totalLen
                if data.flags & const.FLAG_DATA:
                    self.session.dataMessages['snd'] += 1
                    self.session.dataBytes['snd'] += len(data.payload)
            if self._session_logs:
                self.session.history.append((reactor.seconds(), message.getFlagNames(data.flags), data.totalLen))
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

        By default we send ignores at MTU size. We also check whether
        the link is congested due to insufficient send socket buffer
        space, the TCP congestion window being full. In either case, we
        don't send the padding message.
        """
        if not paddingLength:
            paddingLength = self._lengthDataProbdist.randomSample()
            if paddingLength == const.INF_LABEL:
                paddingLength = const.MPU
        if self.downstreamSocket:
            cap = estimate_write_capacity(self.downstreamSocket)
            if cap < paddingLength:
                log.debug("[wfpad - %s] We skipped sending padding because the"
                          " link was congested. The free space is %s", self.end, cap)
                return
        log.debug("[wfpad - %s] Sending ignore message.", self.end)
        self.sendDownstream(self._msgFactory.newIgnore(paddingLength))

    def sendDataMessage(self, payload="", paddingLen=0):
        """Send data message."""
        log.debug("[wfpad - %s] Sending data message with %s bytes payload"
                  " and %s bytes padding", self.end, len(payload), paddingLen)
        self.sendDownstream(self._msgFactory.new(payload, paddingLen))

    def sendControlMessage(self, opcode, args):
        """Send control message."""
        if self.weAreServer:
            raise Exception("[wfpad - %s] Server cannot send control messages.", self.end)
        log.debug("[wfpad - %s] Sending control message: opcode=%s, args=%s."
                  % (self.end, opcode, args))
        self.sendDownstream(self._msgFactory.encapsulate("", opcode, args,
                                                         lenProbdist=self._lengthDataProbdist))

    def pushData(self, data):
        """Push `data` to the buffer or send it over the wire.

        Sample delay distribution for data messages. If we draw a 0 ms
        delay, we encapsulate and send data directly. Otherwise, we push data
        to the buffer and make a delayed called to flush it. In case the
        padding deferrers are active, we cancel them and update the delay
        accordingly.
        """
        log.debug("[wfpad - %s] Pushing %d bytes of outgoing data.", self.end, len(data))

        # Cancel existing deferred calls to padding methods to prevent
        # callbacks that remove tokens from histograms
        deferBurstCancelled, deferGapCancelled = self.cancelDeferrers('snd')

        # Draw delay for data message
        delay = self._delayDataProbdist.randomSample()

        # Update delay according to elapsed time since last message
        # was sent. In case elapsed time is greater than current
        # delay, we sent the data message as soon as possible.
        if deferBurstCancelled or deferGapCancelled:
            elapsed = self.elapsedSinceLastMsg()
            newDelay = delay - elapsed
            delay = 0 if newDelay < 0 else newDelay
            log.debug("[wfpad - %s] New delay is %s", self.end, delay)

        if deferBurstCancelled and hasattr(self._burstHistoProbdist['snd'], "histo"):
            self._burstHistoProbdist['snd'].removeToken(elapsed)
        if deferGapCancelled and hasattr(self._gapHistoProbdist['snd'], "histo"):
            self._gapHistoProbdist['snd'].removeToken(elapsed)

        # Push data message to data buffer
        self._buffer.write(data)
        log.debug("[wfpad - %s] Buffered %d bytes of outgoing data w/ delay %sms", self.end, len(self._buffer), delay)

        # In case there is no scheduled flush of the buffer,
        # make a delayed call to the flushing method.
        if not self._deferData or (self._deferData and self._deferData.called):
            self._deferData = deferLater(delay, self.flushBuffer)
            log.debug("[wfpad - %s] Delay buffer flush %s ms delay", self.end, delay)

    def elapsedSinceLastMsg(self):
        elap = reactor.seconds() - self.session.lastSndDownstreamTs  # @UndefinedVariable
        log.debug("[wfpad - %s] Cancel padding. Elapsed = %s ms", self.end, elap)
        return elap

    def flushBuffer(self):
        """Encapsulate data from buffer in messages and send over the link.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. When buffer is empty we decide whether we
        start padding.
        """
        dataLen = len(self._buffer)
        if dataLen < 0:
            self.deferBurstPadding('snd')
            log.debug("[wfpad - %s] buffer is empty, pad `snd` burst.", self.end)
            return
        log.debug("[wfpad - %s] %s bytes of data found in buffer."
                  " Flushing buffer.", self.end, dataLen)

        payloadLen = self._lengthDataProbdist.randomSample()
        # INF_LABEL = -1 means we don't pad packets (can be done in crypto layer)
        if payloadLen is const.INF_LABEL:
            payloadLen = const.MPU if dataLen > const.MPU else dataLen
        msgTotalLen = payloadLen + const.MIN_HDR_LEN

        self.session.consecPaddingMsgs = 0

        # If data in buffer fills the specified length, we just
        # encapsulate and send the message.
        if dataLen > payloadLen:
            self.sendDataMessage(self._buffer.read(payloadLen))

        # If data in buffer does not fill the message's payload,
        # pad so that it reaches the specified length.
        else:
            paddingLen = payloadLen - dataLen
            self.sendDataMessage(self._buffer.read(), paddingLen)
            log.debug("[wfpad - %s] Padding message to %d (adding %d).", self.end, msgTotalLen, paddingLen)

        log.debug("[wfpad - %s] Sent data message of length %d.", self.end, msgTotalLen)

        self.session.lastSndDataDownstreamTs = self.session.lastSndDownstreamTs = reactor.seconds()  # @UndefinedVariable

        # If buffer is empty, generate padding messages.
        if len(self._buffer) > 0:
            dataDelay = self._delayDataProbdist.randomSample()
            self._deferData = deferLater(dataDelay, self.flushBuffer)
            log.debug("[wfpad - %s] data waiting in buffer, flushing again "
                      "after delay of %s ms.", self.end, dataDelay)
        else:
            self.deferBurstPadding('snd')
            log.debug("[wfpad - %s] buffer is empty, pad `snd` burst.", self.end)

    @test_ut.instrument_dump
    def processMessages(self, data):
        """Extract WFPad protocol messages.

        Data is written to the local application and padding messages are
        filtered out.
        """
        log.debug("[wfpad - %s] Parse protocol messages from stream.", self.end)

        # Make sure there actually is data to be parsed
        if (data is None) or (len(data) == 0):
            return None

        # Try to extract protocol messages
        msgs = []
        try:
            msgs = self._msgExtractor.extract(data)
        except Exception, e:
            log.exception("[wfpad - %s] Exception extracting "
                          "messages from stream: %s", self.end, str(e))

        self.session.lastRcvDownstreamTs = reactor.seconds()
        for msg in msgs:
            log.debug("[wfpad - %s] A new message has been parsed!", self.end)
            msg.rcvTime = time.clock()
            if self._session_logs:
                self.session.history.append((reactor.seconds(), message.getFlagNames(msg.flags), -1 * msg.totalLen))
            if msg.flags & const.FLAG_CONTROL:
                # Process control messages
                payload = msg.payload
                if len(payload) > 0:
                    self.circuit.upstream.write(payload)
                self.receiveControlMessage(msg.opcode, msg.args)
            else:
                self.deferBurstPadding('rcv')
                self.session.numMessages['rcv'] += 1
                self.session.totalBytes['rcv'] += msg.totalLen
                log.debug("total bytes and total len of message: %s" % msg.totalLen)

                # Filter padding messages out.
                if msg.flags & const.FLAG_PADDING:
                    log.debug("[wfpad - %s] Padding message ignored.", self.end)

                # Forward data to the application.
                elif msg.flags & const.FLAG_DATA:
                    log.debug("[wfpad - %s] Data flag detected, relaying upstream", self.end)
                    self.session.dataBytes['rcv'] += len(msg.payload)
                    self.session.dataMessages['rcv'] += 1
                    self.circuit.upstream.write(msg.payload)
                    self.session.lastRcvDataDownstreamTs = reactor.seconds()

                # Otherwise, flag not recognized
                else:
                    log.error("[wfpad - %s] Invalid message flags: %d.", self.end, msg.flags)
        return msgs

    def deferBurstPadding(self, when):
        """Sample delay from corresponding distribution and wait for data.

        In case we have not received data after delay, we call the method
        `timeout` to send ignore packets and sample next delay.
        """
        burstDelay = self._burstHistoProbdist[when].randomSample()
        log.debug("[wfpad - %s] - Delay %sms sampled from burst distribution.", self.end, burstDelay)
        if burstDelay is not const.INF_LABEL:
            self._deferBurst[when] = deferLater(burstDelay,
                                                self.timeout,
                                                when=when,
                                                cbk=self._deferBurstCallback[when])

    def is_channel_idle(self):
        """Return boolean on whether there has passed too much time without communication."""
        is_idle_up = reactor.seconds() - self.session.lastSndDataDownstreamTs > const.MAX_LAST_DATA_TIME
        is_idle_down = reactor.seconds() - self.session.lastSndDataDownstreamTs > const.MAX_LAST_DATA_TIME
        return is_idle_up and is_idle_down

    def timeout(self, when):
        """Send ignore in response to up/downstream traffic and wait for data.

        We sample the delay to wait from the `when` gap prob distribution.
        We call this method again in case we don't receive data after the
        delay.
        """
        # if self.weAreClient:
        #     if self.is_channel_idle():
        #         log.info("[wfpad - %s] - Channel has been idle more than %s ms,"
        #                  "flag end of session", self.end, const.MAX_LAST_DATA_TIME)
        #         self.sendControlMessage(const.OP_APP_HINT,
        #                                 [self.getSessId(), False])
        #         return
        if self.session.is_padding and self.stopCondition(self):
            log.debug("[wfpad - %s] -  Padding was stopped!!", self.end)
            self.onEndPadding()
            return
        self.sendIgnore()
        if when is 'snd':
            self.session.consecPaddingMsgs += 1
            self.session.lastSndDownstreamTs = reactor.seconds()  # @UndefinedVariable
        delay = self._gapHistoProbdist[when].randomSample()
        if delay is const.INF_LABEL:
            return
        log.debug("[wfpad - %s]  Wait for data, pad snd gap otherwise.", self.end)
        self._deferGap[when] = deferLater(delay,
                                          self.timeout,
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

    def cancelDeferrer(self, d):
        """Cancel padding deferrer."""
        if d and not d.called:
            log.debug("[wfpad - %s] - Attempting to cancel a deferrer.", self.end)
            d.cancel()
            return True
        return False

    def cancelBurst(self, when):
        log.debug("[wfpad - %s] - Burst (%s) deferrer was cancelled.", self.end, when)
        return self.cancelDeferrer(self._deferBurst[when])

    def cancelGap(self, when):
        log.debug("[wfpad - %s] - Gap (%s) deferrer was cancelled.", self.end, when)
        return self.cancelDeferrer(self._deferGap[when])

    def cancelDeferrers(self, when):
        return self.cancelBurst(when), self.cancelGap(when)

    def onSessionStarts(self, sessId):
        """Sens hint for session start.

        To be extended at child classes that implement
        final website fingerprinting countermeasures.
        """
        self.session = Session()
        if self.weAreClient:
            self.sendControlMessage(const.OP_APP_HINT,
                                    [self.getSessId(), True])
        else:
            self._sessId = sessId
            self._visiting = True
        log.info("[wfpad - %s] - Session has started!(sessid = %s)", self.end, sessId)

    def dump_session_history(self, sessId):
        # dump history TODO: remove!!
        csv_file = join(self._session_logs, "{}.csv".format(sessId))
        if isfile(csv_file):
            fileutil.removefile(csv_file)
        with open(csv_file, "w+") as f:
            for p in self.session.history:
                f.write(";".join(map(str, p)) + "\n")
        self.session.history = []

    def onSessionEnds(self, sessId):
        """Send hint for session end.

        Interface to be extended at child classes that implement
        final website fingerprinting countermeasures.
        """
        if self.weAreClient:
            self.sendControlMessage(const.OP_APP_HINT,
                                    [self.getSessId(), False])
            if self._session_logs:
                self.dump_session_history(sessId)
            if self._shim:
                self.session.is_padding = True
                self._shim.notifyStartPadding()  # padding the tail of the page
        else:
            self._visiting = False
        log.info("[wfpad - %s] - Session has ended! (sessid = %s)", self.end, sessId)

    def onEndPadding(self):
        self.session.is_padding = False
        # Notify shim observers
        if self.weAreClient and self._shim:
            log.info("[wfpad - %s] - Padding stopped!", self.end)
            self._shim.notifyEndPadding()
        # Cancel deferers
        self.cancelDeferrers('snd')
        self.cancelDeferrers('rcv')
        self.session.totalPadding = self.calculateTotalPadding(self)
        log.info("[wfpad - %s] - Total padding: %s", self.end, self.session.totalPadding)

    def getSessId(self):
        """Return current session Id."""
        if self.weAreServer:
            return self._sessId
        if self._sessionObserver:
            return self._sessionObserver.getSessId()
        return const.DEFAULT_SESSION

    def isVisiting(self):
        """Return a bool indicating if we're in the middle of a session."""
        if self.weAreClient:
            return self._sessionObserver._visiting
        elif self.weAreServer:
            return self._visiting

    # ==========================================================================
    # Deal with control messages
    # ==========================================================================
    def receiveControlMessage(self, opcode, args=None):
        """Do operation indicated by the _opcode."""
        log.debug("[wfpad - %s] Received control message with opcode %s and args: %s",
                  self.end, mes.getOpcodeNames(opcode), args)

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
            log.error("[wfpad - %s] - The received opcode is not recognized.", self.end)


class WFPadClient(WFPadTransport):
    def __init__(self):
        """Initialize a WFPadClient object."""
        WFPadTransport.__init__(self)


class WFPadServer(WFPadTransport):
    def __init__(self):
        """Initialize a WFPadServer object."""
        WFPadTransport.__init__(self)
