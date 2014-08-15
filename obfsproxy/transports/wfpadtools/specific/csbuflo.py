"""
This module implements the CS-CSBuFLO countermeasure proposed by Cai et al.
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools.specific.buflo import BuFLOTransport
from obfsproxy.transports.scramblesuit import probdist


log = logging.get_obfslogger()


class CSBuFLOTransport(WFPadTransport):
    """Implementation of the CSBuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self):
        super(BuFLOTransport, self).__init__()
        # Set constant length for messages
        self._lengthDataProbdist = probdist.uniform(self._length)

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

        super(CSBuFLOTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.

        BuFLO pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        # Defaults for BuFLO specifications.
        cls._period = 1
        cls._length = const.MPU

        super(BuFLOTransport, cls).validate_external_mode_cli(args)

        if args.period:
            cls._period = args.period
        if args.psize:
            cls._length = args.psize

    def onSessionStarts(self, sessId):
        WFPadTransport.onSessionStarts(self, sessId)
        self.constantRatePaddingDistrib(self._period)
        self.sendControlMessage(const.OP_TOTAL_PAD, [sessId, self._period])


class CSBuFLOClient(CSBuFLOTransport):
    """Extend the CSBuFLOTransport class."""

    def __init__(self):
        """Initialize a CSBuFLOClient object."""
        CSBuFLOTransport.__init__(self)


class CSBuFLOServer(CSBuFLOTransport):
    """Extend the CSBuFLOTransport class."""

    def __init__(self):
        """Initialize a CSBuFLOServer object."""
        CSBuFLOTransport.__init__(self)
