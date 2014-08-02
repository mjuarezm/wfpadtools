"""
This module implements the BuFLO countermeasure proposed by Dyer et al.
"""
import obfsproxy.common.log as logging
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import const, socks_shim
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport
from obfsproxy.transports.wfpadtools.wfpad import WFPadShimObserver

log = logging.get_obfslogger()


class BuFLOShimObserver(WFPadShimObserver):

    def onSessionStarts(self, connId):
        """Do operations to be done when session starts."""
        super(BuFLOShimObserver, self).onSessionStarts(connId)
        self.wfpad.startPadding()
        self.wfpad.sendAppHintRequest(self._sessId)


class BuFLOTransport(WFPadTransport):
    """Implementation of the BuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    # Defaults for BuFLO specifications.
    _period = 0.01
    _psize = const.MTU
    _mintime = -1

    def __init__(self):
        print "XXX INIT buflo ", id(self)
        log.debug("[wfad] Initializing %s (id=%s)." % (const.TRANSPORT_NAME,
                                                       str(id(self))))
        super(BuFLOTransport, self).__init__()

        # Initialize minimum time for padding at each visit to a web page.
        self._delayProbdist = probdist.new(lambda: self._period,
                                          lambda i, n, c: 1)
        self._lengthProbdist = probdist.new(lambda: self._psize,
                                           lambda i, n, c: 1)

        # The stop condition in BuFLO:
        # BuFLO stops padding if the visit has finished and the
        # elapsed time has exceeded the minimum padding time.
        self.stopCondition = lambda s: self.getElapsed() > self._mintime \
                                                    and not self._visiting

        # Register observer for shim events
        if self.weAreClient:
            shim = socks_shim.get()
            self.sessionObserver = BuFLOShimObserver(self)
            shim.registerObserver(self.sessionObserver)

    @classmethod
    def setup(cls, transportConfig):
        """Called once when obfsproxy starts."""
        cls.weAreClient = transportConfig.weAreClient
        cls.weAreServer = not cls.weAreClient
        cls.weAreExternal = transportConfig.weAreExternal

    def circuitDestroyed(self, reason, side):
        """Unregister shim observers."""
        if self.weAreClient:
            shim = socks_shim.get()
            if shim.isRegistered(self.sessionObserver):
                shim.deregisterObserver(self.sessionObserver)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for BuFLO parameters."""
        subparser.add_argument("--period",
                               required=False,
                               type=float,
                               help="Time rate at which transport sends "
                                    "messages (Default: 1ms).",
                               dest="period")
        subparser.add_argument("--psize",
                               required=False,
                               type=int,
                               help="Length of messages to be transmitted"
                                    " (Default: MTU).",
                               dest="psize")
        subparser.add_argument("--mintime",
                               required=False,
                               type=int,
                               help="Minimum padding time per visit.",
                               dest="mintime")

        super(BuFLOTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.

        BuFLO pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        super(BuFLOTransport, cls).validate_external_mode_cli(args)

        if args.mintime:
            cls._mintime = int(args.mintime)
        if args.period:
            cls._period = args.period
        if args.psize:
            cls._psize = args.psize


class BuFLOClient(BuFLOTransport):
    """Extend the BuFLOTransport class."""

    def __init__(self):
        """Initialize a BuFLOClient object."""
        BuFLOTransport.__init__(self)


class BuFLOServer(BuFLOTransport):
    """Extend the BuFLOTransport class."""

    def __init__(self):
        """Initialize a BuFLOServer object."""
        BuFLOTransport.__init__(self)
