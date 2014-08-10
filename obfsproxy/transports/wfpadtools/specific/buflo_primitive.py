"""
This module implements the BuFLO countermeasure proposed by Dyer et al.
"""
from obfsproxy.transports.scramblesuit import probdist
import obfsproxy.common.log as logging

from obfsproxy.transports.wfpadtools import const, socks_shim
from obfsproxy.transports.wfpadtools.wfpad import WFPadShimObserver
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport


log = logging.get_obfslogger()


class BuFLOShimObserver(WFPadShimObserver):

    def onSessionStarts(self):
        """Do operations to be done when session starts."""
        super(BuFLOShimObserver, self).onSessionStarts()
        self.wfpad.onSessionStart()


class BuFLOTransport(WFPadTransport):
    """Implementation of the BuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    # Defaults for BuFLO specifications.
    _period = 0.01
    _length = const.MTU
    _mintime = -1

    def __init__(self):
        super(BuFLOTransport, self).__init__()

        # Initialize minimum time for padding at each visit to a web page.
        self._delayDataProbdist = probdist.new(lambda i, n, c: self._period,
                                          lambda i, n, c: 1)
        self._lengthDataProbdist = probdist.new(lambda i, n, c: self._length,
                                           lambda i, n, c: 1)

        # Register observer for shim events
        if self.weAreClient:
            shim = socks_shim.get()
            self._sessionObserver = BuFLOShimObserver(self)
            shim.registerObserver(self._sessionObserver)

    def circuitConnected(self):
        """Initiate handshake.

        This method is only relevant for clients since servers never initiate
        handshakes.
        """
        self._state = const.ST_CONNECTED
        self.flushSendBuffer()

    def circuitDestroyed(self, reason, side):
        """Unregister shim observers."""
        if self.weAreClient:
            shim = socks_shim.get()
            if shim.isRegistered(self._sessionObserver):
                shim.deregisterObserver(self._sessionObserver)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments."""
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
        if args._period:
            cls._period = args._period
        if args._length:
            cls._length = args._length

    def stopCondition(self):
        """Returns the evaluation of the condition to stop padding.

        BuFLO stops padding if the visit has finished and the elapsed time has
        exceeded the minimum padding time.
        """
        return self.getElapsed() > self._mintime \
                and self._state is self._visiting


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
