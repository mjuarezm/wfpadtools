"""
The wfpad module implements the Tor WF framework to develop WF countermeasures.
"""
import obfsproxy.common.log as logging
from obfsproxy.transports.base import BaseTransport
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.filter import PadFilter
from obfsproxy.transports.wfpadtools.padutils import BuFLO


log = logging.get_obfslogger()


class WFPadTransport(BaseTransport):
    """Implements the Tor WF framework to develop WF countermeasures.

    This class implements methods which implement primitives and protocols
    specifications to further develop WF countermeasures.
    """

    def __init__(self):
        """Initialise a WFPadTransport object."""
        log.debug("Initialising %s." % const.TRANSPORT_NAME)
        self.linkpadder = BuFLO(1, 2, 500)
        self.padfilter = PadFilter()
        super(WFPadTransport, self).__init__()

    @classmethod
    def setup(cls, transportConfig):
        """
        Called once when obfsproxy starts.
        """
        log.error("\n\n#########################################################\n"
                  " WFPad isn't a Website Fingerprinting defense by itself.\n"
                  "#########################################################\n")

        cls.weAreClient = transportConfig.weAreClient
        cls.weAreServer = not cls.weAreClient
        cls.weAreExternal = transportConfig.weAreExternal

    def circuitConnected(self):
        """Initiate handshake.

        This method is only relevant for clients since servers never initiate
        handshakes.
        """
        # Start link padder
        self.linkpadder.start()

    def receivedDownstream(self, data):
        """Got data from downstream; relay them upstream."""
        log.debug(str(self.__class__.__name__) + ": down")
        # Filter padding and send to remote
        filtered_data = self.padfilter.filter(data.read())
        if filtered_data:
            self.circuit.upstream.write(filtered_data)

    def receivedUpstream(self, data):
        """Got data from upstream; relay them downstream."""
        log.debug(str(self.__class__.__name__) + ": up")

        # Push data to buffer
        self.linkpadder.push_to_buffer(data.read())


class WFPadClient(WFPadTransport):
    """Extend the WFPad class."""

    def __init__(self):
        """Initialise a WFPadClient object."""
        WFPadTransport.__init__(self)


class WFPadServer(WFPadTransport):
    """Extend the WFPad class."""

    def __init__(self):
        """Initialise a WFPadServer object."""
        WFPadTransport.__init__(self)
