"""
The module implements Tamaraw WF countermeasure proposed by Wang and Goldberg.
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class TamarawTransport(WFPadTransport):
    """Implementation of the Tamaraw countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self):
        self._mintime = 1
        super(TamarawTransport, self).__init__()

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
        super(TamarawTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.

        Tamaraw pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        super(TamarawTransport, cls).validate_external_mode_cli(args)
        # Defaults for Tamaraw specifications.
        mintime = -1
        if args.mintime:
            mintime = int(args.mintime)
        # Initialize minimum time for padding at each visit to a web page.
        cls._mintime = mintime

    def stop_condition(self):
        """Returns the evaluation of the condition to stop padding.

        Tamaraw stops padding if the visit has finished and the elapsed time has
        exceeded the minimum padding time.
        """
        return self.get_elapsed() > self._mintime \
                and self._state is const.ST_PADDING


class TamarawClient(TamarawTransport):
    """Extend the TamarawTransport class."""

    def __init__(self):
        """Initialize a TamarawClient object."""
        TamarawTransport.__init__(self)


class TamarawServer(TamarawTransport):
    """Extend the TamarawTransport class."""

    def __init__(self):
        """Initialize a TamarawServer object."""
        TamarawTransport.__init__(self)
