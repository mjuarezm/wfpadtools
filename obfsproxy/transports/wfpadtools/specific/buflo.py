"""
This module implements the BuFLO countermeasure proposed by Dyer et al.
"""
import time

import obfsproxy.common.log as logging
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport


log = logging.get_obfslogger()


class BuFLOTransport(WFPadTransport):
    """Implementation of the BuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    # Defaults for BuFLO specifications.
    _mintime = -1
    _startTime = time.time()
    _period = 0.01
    _psize = const.MTU

    def __init__(self):
        super(BuFLOTransport, self).__init__()
        # The stop condition in BuFLO:
        # BuFLO stops padding if the visit has finished and the
        # elapsed time has exceeded the minimum padding time.
        self.stopCondition = lambda s: self.getElapsed() > self._mintime and \
                                            not self._visiting

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

    def getElapsed(self):
        """Returns time elapsed since the beginning of the session.

        If a session has not yet started, it returns time since __init__.
        """
        elapsed = time.time() - self._startTime
        log.debug("[buflo] Return elapsed time "
                  "since start of session %d." % elapsed)
        return elapsed

    def onSessionStarts(self, sessId):
        WFPadTransport.onSessionStarts(self, sessId)
        self._startTime = time.time()
        self._lengthDataProbdist = probdist.uniform(self._psize)
        self.setConstantRatePadding(self._period)


class BuFLOClient(BuFLOTransport):

    def __init__(self):
        """Initialize a BuFLOClient object."""
        BuFLOTransport.__init__(self)


class BuFLOServer(BuFLOTransport):

    def __init__(self):
        """Initialize a BuFLOServer object."""
        BuFLOTransport.__init__(self)
