"""
The module implements the supersequence-based countermeasure in USENIX paper
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class SupersequenceTransport(WFPadTransport):
    """Implementation of the Supersequence countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self):
        self._mintime = 1
        super(SupersequenceTransport, self).__init__()

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
        super(SupersequenceTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.

        Supersequence pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        super(SupersequenceTransport, cls).validate_external_mode_cli(args)
        # Defaults for Supersequence specifications.
        mintime = -1
        if args.mintime:
            mintime = int(args.mintime)
        # Initialize minimum time for padding at each visit to a web page.
        cls._mintime = mintime

    def stopCondition(self):
        """Returns the evaluation of the condition to stop padding.

        Supersequence stops padding if the visit has finished and the elapsed time has
        exceeded the minimum padding time.
        """
        return self.getElapsed() > self._mintime \
                and self._state is const.ST_PADDING


class SupersequenceClient(SupersequenceTransport):
    """Extend the SupersequenceTransport class."""

    def __init__(self):
        """Initialize a SupersequenceClient object."""
        SupersequenceTransport.__init__(self)


class SupersequenceServer(SupersequenceTransport):
    """Extend the SupersequenceTransport class."""

    def __init__(self):
        """Initialize a SupersequenceServer object."""
        SupersequenceTransport.__init__(self)
