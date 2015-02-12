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
        super(AdaptiveTransport, self).__init__()

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

        # Parameters governing padding
        # Burst padding
        # Sending
        subparser.add_argument("--burst-histo-snd",
                               required=False,
                               type=list,
                               help="Histogram for burst padding (snd)."
                                    " (Default: uniform).", default=[1],
                               dest="burst_histo_snd")
        subparser.add_argument("--burst-histo-snd-labels",
                               required=False,
                               type=list,
                               help="Labels for the burst padding histo (snd)."
                                    " (Default: --period).",
                               dest="burst_histo_snd_labels")
        subparser.add_argument("--burst-removetoks-snd",
                               required=False,
                               type=list,
                               help="Remove tokens from distribution (snd)."
                                    " (Default: False).", default=False,
                               dest="burst_removetoks_snd")

        # Receiving
        subparser.add_argument("--burst-histo-rcv",
                               required=False,
                               type=list,
                               help="Histogram for burst padding (rcv)."
                                    " (Default: uniform).", default=[1],
                               dest="burst_histo_rcv")
        subparser.add_argument("--burst-histo-rcv-labels",
                               required=False,
                               type=list,
                               help="Labels for the burst padding histo (rcv)."
                                    " (Default: --period).",
                               dest="burst_histo_rcv_labels")
        subparser.add_argument("--burst-removetoks-rcv",
                               required=False,
                               type=list,
                               help="Remove tokens from distribution (rcv)."
                                    " (Default: False).", default=False,
                               dest="burst_removetoks_rcv")

        # Gap padding
        # Sending
        subparser.add_argument("--gap-histo-snd",
                               required=False,
                               type=list,
                               help="Histogram for gap padding (snd)."
                                    " (Default: uniform).", default=[1],
                               dest="gap_histo_snd")
        subparser.add_argument("--gap-histo-snd-labels",
                               required=False,
                               type=list,
                               help="Labels for the gap padding histo (snd)."
                                    " (Default: --period).",
                               dest="gap_histo_snd_labels")
        subparser.add_argument("--gap-removetoks-snd",
                               required=False,
                               type=list,
                               help="Remove tokens from distribution (snd)."
                                    " (Default: False).", default=False,
                               dest="gap_removetoks_snd")

        # Receiving
        subparser.add_argument("--gap-histo-rcv",
                               required=False,
                               type=list,
                               help="Histogram for gap padding (rcv)."
                                    " (Default: uniform).", default=[1],
                               dest="gap_histo_rcv")
        subparser.add_argument("--gap-histo-rcv-labels",
                               required=False,
                               type=list,
                               help="Labels for the gap padding histo (rcv)."
                                    " (Default: --period).",
                               dest="gap_histo_rcv_labels")
        subparser.add_argument("--gap-removetoks-rcv",
                               required=False,
                               type=list,
                               help="Remove tokens from distribution (rcv)."
                                    " (Default: False).", default=False,
                               dest="gap_removetoks_rcv")

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

        # Padding parameters
        cls.burst_histo_snd = args.burst_histo_snd
        cls.burst_removetoks_snd = args.burst_removetoks_snd
        if args.burst_histo_snd_labels:
            cls.burst_histo_snd_labels = args.burst_histo_snd_labels
        else:
            cls.burst_histo_snd_labels = [cls._period]

        cls.burst_histo_rcv = args.burst_histo_rcv
        cls.burst_removetoks_rcv = args.burst_removetoks_rcv
        if args.burst_histo_rcv_labels:
            cls.burst_histo_rcv_labels = args.burst_histo_rcv_labels
        else:
            cls.burst_histo_rcv_labels = [cls._period]

        cls.gap_histo_snd = args.gap_histo_snd
        cls.gap_removetoks_snd = args.gap_removetoks_snd
        if args.gap_histo_snd_labels:
            cls.gap_histo_snd_labels = args.gap_histo_snd_labels
        else:
            cls.gap_histo_snd_labels = [cls._period]

        cls.gap_histo_rcv = args.gap_histo_rcv
        cls.gap_removetoks_rcv = args.gap_removetoks_rcv
        if args.gap_histo_rcv_labels:
            cls.gap_histo_rcv_labels = args.gap_histo_rcv_labels
        else:
            cls.gap_histo_rcv_labels = [cls._period]

    def onSessionStarts(self, sessId):
        WFPadTransport.onSessionStarts(self, sessId)
        self.constantRatePaddingDistrib(self._period)

        # i-th position in histogram is the number of tokens for the
        # probability of sampling a delay within [labels(i-1), labels(i)),
        # except:
        #     i=0 -> [0, labels(0)]
        #     i=len(histo)-1 -> delay=infinite
        #     i=len(histo)-2 -> [labels(len(histo)-2), MAX_DELAY]
        interpolate = True
        self.relayBurstHistogram(self.burst_histo_snd,
                                 self.burst_histo_snd_labels,
                                 self.burst_removetoks_snd,
                                 interpolate, "snd")
        self.relayBurstHistogram(self.burst_histo_rcv,
                                 self.burst_histo_rcv_labels,
                                 self.burst_removetoks_rcv,
                                 interpolate, "rcv")
        self.relayGapHistogram(self.gap_histo_snd,
                               self.gap_histo_snd_labels,
                               self.gap_removetoks_snd,
                               interpolate, "snd")
        self.relayGapHistogram(self.gap_histo_rcv,
                               self.gap_histo_rcv_labels,
                               self.gap_removetoks_rcv,
                               interpolate, "rcv")


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
