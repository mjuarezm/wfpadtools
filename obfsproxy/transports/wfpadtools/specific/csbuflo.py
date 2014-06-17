"""
This module implements the CS-CSBuFLO countermeasure proposed by Cai et al.
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class CSBuFLOTransport(WFPadTransport):
    """Implementation of the CSBuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self):
        self._mintime = 1
        super(CSBuFLOTransport, self).__init__()

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments."""
        subparser.add_argument("--mintime",
                               required=False,
                               type=int,
                               help="Minimum padding time per visit. For"
                                    " negative values the padding is constant"
                                    " (Default: -1)",
                               dest="mintime")
        super(CSBuFLOTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.

        CSBuFLO pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        super(CSBuFLOTransport, cls).validate_external_mode_cli(args)
        # Defaults for CSBuFLO specifications.
        mintime = -1
        if args.mintime:
            mintime = int(args.mintime)
        # Initialize minimum time for padding at each visit to a web page.
        cls._mintime = mintime

    def stop_condition(self):
        """Returns the evaluation of the condition to stop padding.

        CSBuFLO stops padding if the visit has finished and the elapsed time has
        exceeded the minimum padding time.
        """
        return self.get_elapsed() > self._mintime \
                and self._state is const.ST_PADDING


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
