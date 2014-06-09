"""
The wfpad module implements the Tor WF framework to develop WF countermeasures.
"""
from twisted.internet import reactor

import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import message
import obfsproxy.transports.wfpadtools.const as const
import obfsproxy.transports.wfpadtools.util as ut


log = logging.get_obfslogger()


class WFPadTransport(BaseTransport):
    """Implements the Tor WF framework to develop WF countermeasures.

    This class implements methods which implement primitives and protocols
    specifications to further develop WF countermeasures.
    """
    def __init__(self, time_probdist=probdist.new(lambda: 0.001),
                       size_probdist=probdist.new(lambda: const.MTU)):
        """Initialize a WFPadTransport object."""
        log.debug("Initializing %s." % const.TRANSPORT_NAME)

        super(WFPadTransport, self).__init__()

        # Initialize the protocol's state machine.
        self._state = const.ST_WAIT

        # Buffer for outgoing data.
        self.sendBuf = ""

        # Buffer used for padding.
        self.padding_buffer = Buffer()

        # Used to extract protocol messages from encrypted data.
        self.msg_extractor = message.WFPadMessageExtractor()

        # Initialize probability distributions.
        # TODO: pass these as argument:
        self._time_probdist = time_probdist
        self._size_probdist = size_probdist

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
        # Start padding link
        self._state = const.ST_CONNECTED
        self.flushSendBuffer()
        self.flushPieces()

    def encapsulate(self, data, flags=const.FLAG_DATA):
        """Return protocol messages containing data as string.

        Data is chopped in chunks. Each chunk is appended to a header
        as payload. Then, we convert the stream of messages to string.
        """
        # Wrap the application's data in WFPad protocol messages.
        messages = message.createWFPadMessages(data, flags=flags)

        blurb = "".join([str(msg) for msg in messages])
        return blurb

    def sendRemote(self, data, flags=const.FLAG_DATA):
        """Send data to the remote end once the connection is established.

        The given `data` is first encapsulated in protocol messages.  Then, the
        protocol message(s) are sent over the wire.  The argument `flags'
        specifies the protocol message flags.
        """
        log.debug("Processing %d bytes of outgoing data." % len(data))

        if self._state is const.ST_CONNECTED:
            self.padding_buffer.write(self.encapsulate(data, flags))

    def flushPieces(self):
        """Write the application data in chunks to the wire.

        In case the buffer is not empty, the buffer is flushed and we send
        these data over the wire. Otherwise, we generate random padding
        and we send it over the wire in chunks. After every write call,
        control is given back to the Twisted reactor. The function is called
        again after a certain delay, which is sampled from the time
        probability distribution.
        """
        if self.stop_condition():
            self._timer.stop()
            return
        if len(self.padding_buffer) > 0:
            if len(self.padding_buffer) > const.MTU:
                data = self.padding_buffer \
                    .read(self._size_probdist.randomSample())
                log.debug("Flush buffer")
                self.circuit.downstream.write(data)
            else:
                data = self.padding_buffer.read()
                log.debug("Flush buffer")
                self.circuit.downstream.write(data)
        else:
            log.debug("Generate padding")
            data = self.encapsulate(self.generate_padding(),
                                    flags=const.FLAG_PADDING)
            self.circuit.downstream.write(data)

        reactor.callLater(self._time_probdist.randomSample(), self.flushPieces)

    def processMessages(self, data):
        """Acts on extracted protocol messages based on header flags.

        Data is written to the local application and padding messages are
        filtered out from the stream.
        """
        log.debug("I'm going to parse protocol messages from data.")
        if (data is None) or (len(data) == 0):
            return

        # Try to extract protocol messages.
        msgs = self.msg_extractor.extract(data)
        for msg in msgs:
            if (msgs is None) or (len(msgs) == 0):
                return
            for msg in msgs:
                # Forward data to the application.
                if msg.flags == const.FLAG_DATA:
                    log.debug("Fata flag detected, relaying tor data stream")
                    self.circuit.upstream.write(msg.payload)

                # Filter padding messages out.
                elif msg.flags == const.FLAG_PADDING:
                    log.debug("Padding message ignored.")
                else:
                    log.warning("Invalid message flags: %d." % msg.flags)

    def stop_condition(self):
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

    def generate_padding(self):
        """Return padding data.

        The length of the padding is sampled from the packet length probability
        distribution `size_probdist`, passed as a parameter in the init.
        """
        return ut.rand_str(self._size_probdist.randomSample())

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream."""
        if self._state == const.ST_CONNECTED:
            self.sendRemote(data.read())

        # Buffer data we are not ready to transmit yet.
        else:
            self.sendBuf += data.read()
            log.debug("Buffered %d bytes of outgoing data." %
                      len(self.sendBuf))

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        if self._state is const.ST_CONNECTED:
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
        """Initialize a WFPadServer object."""
        WFPadTransport.__init__(self)
