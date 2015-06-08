"""
This module implements the Adaptive Padding countermeasure proposed
by Shmatikov and Wang.
"""
import operator
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
            if self.weAreClient:
                hist_dict_incoming = self.getHistoFromDistrParams("weibull", 0.432052048, scale=0.004555816)  # estimated from real web traffic
                hist_dict_outgoing = self.getHistoFromDistrParams("beta", (0.1899451, 60.4645585))  # estimated from real web traffic
                low_bins_inc, high_bins_inc = self.divideHistogram(hist_dict_incoming)
                low_bins_out, high_bins_out = self.divideHistogram(hist_dict_outgoing)
                self.relayBurstHistogram(low_bins_inc, "rcv")
                self.relayBurstHistogram(low_bins_inc, "snd")
                self.relayGapHistogram(high_bins_inc, "rcv")
                self.relayGapHistogram(high_bins_inc, "snd")
                self.sendControlMessage(const.OP_BURST_HISTO, [low_bins_out, True, True, "rcv"])
                self.sendControlMessage(const.OP_BURST_HISTO, [low_bins_out, True, True, "snd"])
                self.sendControlMessage(const.OP_GAP_HISTO, [high_bins_out, True, True, "rcv"])
                self.sendControlMessage(const.OP_GAP_HISTO, [high_bins_out, True, True, "snd"])

        WFPadTransport.onSessionStarts(self, sessId)

    @classmethod
    def divideHistogram(self, histogram, divide_by=None):
        if divide_by == None:
            divide_by = max(histogram.iteritems(), key=operator.itemgetter(1))[0]
        high_bins = {k: v for k, v in histogram.iteritems()  if k >= divide_by}
        low_bins = {k: v for k, v in histogram.iteritems() if k <= divide_by}
        low_bins.update({"inf": 0})
        high_bins.update({divide_by: 0})
        return low_bins, high_bins

    @classmethod
    def getHistoFromDistrParams(self, name, params, samples=1000, scale=1.0):
        import numpy as np
        counts, bins = [], []
        if name == "weibull":
            shape = params
            counts, bins = np.histogram(np.random.weibull(shape, samples) * scale)

        elif name == "beta":
            a, b = params
            counts, bins = np.histogram(np.random.beta(a, b, samples) * scale)

        elif name == "gamma":
            pass

        else:
            raise ValueError("Unknown probability distribution.")

        return dict(zip(list(bins) + ["inf"], [0] + list(counts) + [0]))

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
