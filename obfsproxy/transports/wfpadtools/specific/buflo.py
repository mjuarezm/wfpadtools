"""
This module implements the BuFLO countermeasure proposed by Dyer et al.
"""
import time

import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools import histo
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport


log = logging.get_obfslogger()


class BuFLOTransport(WFPadTransport):
    """Implementation of the BuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """

    def __init__(self):
        super(BuFLOTransport, self).__init__()
        # Set constant length for messages
        self._lengthDataProbdist = histo.uniform(self._length)
        # The stop condition in BuFLO:
        # BuFLO stops padding if the visit has finished and the
        # elapsed time has exceeded the minimum padding time.
        def stopConditionHandler(s):
            elapsed = s.getElapsed()
            log.debug("[buflo {}] - elapsed = {}, mintime = {}, visiting = {}"
                      .format(self.end, elapsed, s._mintime, s.isVisiting()))
            return elapsed > s._mintime and not s.isVisiting()
        self.stopCondition = stopConditionHandler

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
        # Defaults for BuFLO specifications.
        cls._mintime = -1
        cls._period = 1
        cls._length = const.MPU

        super(BuFLOTransport, cls).validate_external_mode_cli(args)

        if args.mintime:
            cls._mintime = int(args.mintime)
        if args.period:
            cls._period = args.period
        if args.psize:
            cls._length = args.psize

    def onSessionStarts(self, sessId):
        WFPadTransport.onSessionStarts(self, sessId)
        log.debug("[buflo {}] - params: mintime={}, period={}, psize={}"
                  .format(self.end, self._mintime, self._period, self._length))
        self.constantRatePaddingDistrib(self._period)


class BuFLOClient(BuFLOTransport):

    def __init__(self):
        """Initialize a BuFLOClient object."""
        BuFLOTransport.__init__(self)


class BuFLOServer(BuFLOTransport):

    def __init__(self):
        """Initialize a BuFLOServer object."""
        BuFLOTransport.__init__(self)
