"""
This module implements the Adaptive Padding countermeasure proposed
by Shmatikov and Wang.
"""
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport
from obfsproxy.transports.wfpadtools import histo
from obfsproxy.transports.wfpadtools.util import dumputil as du
import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class AdaptiveTransport(WFPadTransport):
    """Implementation of the Adaptive Padding countermeasure.

    Adaptive padding is parametrized using histograms that govern the
    delay probabilities in response to dummy and data messages coming from
    upstream and downstream directions.
    """
    _histograms = None

    def __init__(self):
        super(AdaptiveTransport, self).__init__()
        # Set constant length for messages
        self._lengthDataProbdist = histo.uniform(self._length)
        # The stop condition in Adaptive:
        # Adaptive stops padding if the visit has finished and the
        # elapsed time has exceeded the minimum padding time.
        def stopConditionHandler(s):
            elapsed = s.getElapsed()
            log.debug("[adaptive {}] - elapsed = {}, mintime = {}, visiting = {}"
                      .format(self.end, elapsed, 120, s.isVisiting()))
            return elapsed % 120 and not s.isVisiting()
        self.stopCondition = stopConditionHandler

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for Adaptive Padding parameters."""
        subparser.add_argument("--psize",
                               required=False,
                               type=int,
                               help="Length of messages to be transmitted"
                                    " (Default: MTU).",
                               dest="psize")
        subparser.add_argument("--histo-file",
                               required=True,
                               type=str,
                               help="Fail containing histograms governing "
                                    "padding. (Default: uniform histograms).",
                               dest="histo_file")

        super(AdaptiveTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables."""
        # Defaults for Adaptive Padding specifications.
        cls._length = const.MPU

        super(AdaptiveTransport, cls).validate_external_mode_cli(args)

        if args.psize:
            cls._length = args.psize
        if args.histo_file:
            cls._histograms = du.load_json(args.histo_file)

    def onSessionStarts(self, sessId):
        self._delayDataProbdist = histo.uniform(const.INF_LABEL)
        if self._histograms:
            self.relayBurstHistogram(
                **dict(self._histograms["burst"]["snd"], **{"when": "snd"}))
            self.relayBurstHistogram(
                **dict(self._histograms["burst"]["rcv"], **{"when": "rcv"}))
            self.relayGapHistogram(
                **dict(self._histograms["gap"]["snd"], **{"when": "snd"}))
            self.relayGapHistogram(
                **dict(self._histograms["gap"]["rcv"], **{"when": "rcv"}))
        else:
            hist_dict = self.getHistoFromDistrParams("weibull", 0.432052048, scale=0.004555816)  # estimated from real web traffic
            low_bins, high_bins = self.divideHistogram(hist_dict)
            self.relayBurstHistogram(low_bins, "rcv")
            self.relayBurstHistogram(low_bins, "snd")
            self.relayGapHistogram(high_bins, "rcv")
            self.relayGapHistogram(high_bins, "snd")
        WFPadTransport.onSessionStarts(self, sessId)

    def divideHistogram(self, histogram, divide_by=None):
        if divide_by == None:
            divide_by = max(histogram.iteritems(), key=operator.itemgetter(1))[0]
        sorted_histo = sorted(histogram.items(), key=operator.itemgetter(1))
        high_bins = {k: v for k, v in sorted_histo if v > divide_by}
        low_bins = {k: v for k, v in sorted_histo if v <= divide_by}
        return low_bins, high_bins

    def getHistoFromDistrParams(self, name, params, samples=1000, scale=1.0):
        import numpy as np
        if name == "weibull":
            shape = params
            counts, bins = np.histogram(np.random.weibull(shape, samples) * scale)
            return histo.Histogram(dict(zip([0] + list(counts), bins)))
        elif name == "gamma":
            pass
        else:
            raise ValueError("Unknown probability distribution.")


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
