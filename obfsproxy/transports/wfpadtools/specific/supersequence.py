"""
The module implements the supersequence-based countermeasure in USENIX paper
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class SupersequenceTransport(WFPadTransport):
    """Implementation of the Supersequence countermeasure.


    """
    def __init__(self):
        super(SupersequenceTransport, self).__init__()

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments."""
        super(SupersequenceTransport, cls)\
            .register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables.


        """
        super(SupersequenceTransport, cls).validate_external_mode_cli(args)


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
