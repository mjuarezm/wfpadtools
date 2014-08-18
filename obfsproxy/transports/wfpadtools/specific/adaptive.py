"""
This module implements the Adaptive Padding countermeasure proposed
by Shmatikov and Wang.
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport

import obfsproxy.common.log as logging
from obfsproxy.transports.scramblesuit import probdist


log = logging.get_obfslogger()


class AdaptiveTransport(WFPadTransport):
    """Implementation of the Adaptive Padding countermeasure.

    Adaptive padding is parametrized using histograms that govern the
    delay probabilities in response to dummy and data messages coming from
    upstream and downstream directions.
    """
    def __init__(self):
        super(AdaptiveTransport, self).__init__(self._period, self._length)
        # Set constant length for messages
        self._lengthDataProbdist = probdist.uniform(self._length)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for Adaptive Padding parameters."""
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

        super(AdaptiveTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables."""
        # Defaults for Adaptive Padding specifications.
        cls._period = 10
        cls._length = const.MPU

        super(AdaptiveTransport, cls).validate_external_mode_cli(args)

        if args.period:
            cls._period = args.period
        if args.psize:
            cls._length = args.psize

    def onSessionStarts(self, sessId):
        WFPadTransport.onSessionStarts(self, sessId)
        self.constantRatePaddingDistrib(self._period)

        # i-th position in histogram is the number of tokens for the
        # probability of sampling a delay within [labels(i-1), labels(i)),
        # except:
        #     i=0 -> [0, labels(0)]
        #     i=len(histo)-1 -> delay=infinite
        #     i=len(histo)-2 -> [labels(len(histo)-2), MAX_DELAY]
        histo = [23, 10, 9, 7, 9, 8, 3, 7, 3, 10, 5, 2, 1, 2, 0, 1, 0, 0, 0]
        labels = [2, 4, 8, 16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192,
                  16384, 32768, 65536, 131072, 131072, -1]
        removeToks = True
        interpolate = True
        self.relayBurstHistogram(histo, labels, removeToks, interpolate, "rcv")
        self.relayBurstHistogram(histo, labels, removeToks, interpolate, "snd")
        self.relayGapHistogram(histo, labels, removeToks, interpolate, "snd")
        self.relayGapHistogram(histo, labels, removeToks, interpolate, "rcv")


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
