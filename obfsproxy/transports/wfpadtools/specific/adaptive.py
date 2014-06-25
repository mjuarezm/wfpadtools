"""
The module implements the adaptive-padding countermeasure.
"""
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class AdaptiveTransport(WFPadTransport):
    """Implementation of the Adaptive countermeasure.


    """
    def __init__(self):
        self._mintime = 1
        super(AdaptiveTransport, self).__init__()

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments."""
        super(AdaptiveTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.


        """
        super(AdaptiveTransport, cls).validate_external_mode_cli(args)


class AdaptiveClient(AdaptiveTransport):
    """Extend the AdaptiveTransport class."""

    def __init__(self):
        """Initialize a AdaptiveClient object."""
        AdaptiveTransport.__init__(self)


class AdaptiveServer(AdaptiveTransport):
    """Extend the AdaptiveTransport class."""

    def __init__(self):
        """Initialize a AdaptiveServer object."""
        AdaptiveTransport.__init__(self)
