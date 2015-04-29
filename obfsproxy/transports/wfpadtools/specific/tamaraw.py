"""
The module implements Tamaraw WF countermeasure proposed by Wang and Goldberg.
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools import histo


log = logging.get_obfslogger()


class TamarawTransport(WFPadTransport):
    """Implementation of the Tamaraw countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self):
        super(TamarawTransport, self).__init__()
        # Set constant length for messages
        self._lengthDataProbdist = histo.uniform(self._length)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for Tamaraw parameters."""
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
        subparser.add_argument("--batch",
                               required=False,
                               type=int,
                               help="Number of messages that define the min."
                                    " length of a batch"
                                    " (Default: 20).",
                               dest="batch")
        super(TamarawTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables."""
        # Defaults for BuFLO specifications.
        cls._period = 10
        cls._length = const.MPU
        cls._batch = 20

        super(TamarawTransport, cls).validate_external_mode_cli(args)

        if args.period:
            cls._period = args.period
        if args.psize:
            cls._length = args.psize
        if args.batch:
            cls._batch = args.batch

    def onSessionStarts(self, sessId):
        WFPadTransport.onSessionStarts(self, sessId)
        self.constantRatePaddingDistrib(self._period)
        self.relayBatchPad(sessId, self._batch, self._period)


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
