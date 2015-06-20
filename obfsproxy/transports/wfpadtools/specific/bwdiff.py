"""
This module implements the BW differentials adaptive countermeasure.
"""
import time

# WFPadTools imports
import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools import common as cm
from obfsproxy.transports.wfpadtools import histo as hs
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport
from obfsproxy.transports.wfpadtools.util import genutil as gu
from obfsproxy.transports.wfpadtools.util import mathutil as mu


# Logging
log = logging.get_obfslogger()


class BWDiffTransport(WFPadTransport):
    """Implementation of the CSBuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for CSBuFLO parameters."""
        subparser.add_argument("--period",
                               required=False,
                               type=float,
                               help="Period for sampling bandwidth differentials. "
                                    "(Default: 100msec).",
                               dest="period")
        subparser.add_argument("--threshold",
                               required=False,
                               type=float,
                               help="Threshold for the bandwidth differential.",
                               dest="threshold")
        subparser.add_argument("--window-size",
                               required=False,
                               type=float,
                               help="Window size to estimate the bandwidth.",
                               dest="window_size")
        subparser.add_argument("--psize",
                               required=False,
                               type=int,
                               help="Length of messages to be transmitted"
                                    " (Default: MPU).",
                               dest="psize")
        subparser.add_argument("--early",
                               required=False,
                               type=bool,
                               help="Whether the client will notify the server"
                                    " that has ended padding, so that the server "
                                    "saves on padding by skipping the long tail.",
                               default=False)
        subparser.add_argument("--padding",
                               required=False,
                               type=str,
                               help="Padding mode for this endpoint. There"
                                    " are two possible values: \n"
                                    "- payload (CPSP): pads to the closest multiple "
                                    "of 2^N for N st 2^N closest power of two"
                                    " greater than the payload size.\n"
                                    "- total (CTSP): pads to closest power of two.\n"
                                    "(Default: CPSP).",
                               dest="padding")

        super(BWDiffTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables."""
        # Defaults for BuFLO specifications.
        cls._threshold = 1
        cls._period = 100
        cls._length = const.MPU
        cls._padding_mode = const.PAYLOAD_PADDING
        cls._early_termination = False

        super(BWDiffTransport, cls).validate_external_mode_cli(args)

        if args.period:
            cls._period = args.period
        if args.threshold:
            cls._threshold = args.threshold
        if args.psize:
            cls._length = args.psize
        if args.padding:
            cls._padding_mode = args.padding
        if args.early:
            cls._early_termination = args.early

    def getBwDifferential(self):
        self.iat_length_tuples = [l for l in self.iat_length_tuples if len(l) > 0]
        if time.time() - self.session.startTime > 0.2 and len(self.iat_length_tuples) > 1:
            lengths0 = [t[1] for t in self.iat_length_tuples[-2]]
            lengths1 = [t[1] for t in self.iat_length_tuples[-1]]
            bw0 = sum(lengths0) / self._period
            bw1 = sum(lengths1) / self._period
            bw_diff = (bw1 - bw0) / self._period
            self.session.bw_diffs.append(bw_diff)
            log.debug("[bwdiff %s] - bw diffs: %s", self.end, self.session.bw_diffs)
            log.debug("[bwdiff %s] -  abs bwdiff (%s) > threshold (%s)",
                      self.end, abs(bw_diff), self._threshold)
            if abs(bw_diff) > self._threshold:
                # we should sample uniformly from the passed iats
                # convert self.iat_length_tuples to distribution
                # and pass it to wfpad iat distribution as dict.
                iats = gu.get_iats([t[0] for t in gu.flatten_list(self.iat_length_tuples)])
                h = {iat: 1 for iat in iats}
                self._burstHistoProbdist['snd'] = hs.new(h)
                self._gapHistoProbdist['snd'] = hs.new(h)
            else:
                self._burstHistoProbdist['snd'] = hs.uniform(const.INF_LABEL)
                self._gapHistoProbdist['snd'] = hs.uniform(const.INF_LABEL)
        self.iat_length_tuples.append([])
        log.debug("[bwdiff %s] A period has passed: %s", self.end, self.iat_length_tuples[-3:-1])
        if self.isVisiting():
            log.debug("[bwdiff %s] Calling next period (visiting = %s, padding = %s)",
                      self.end, self.isVisiting(), self.session.is_padding)
            cm.deferLater(self._period, self.getBwDifferential)
            
    def onSessionStarts(self, sessId):
        self._lengthDataProbdist = hs.uniform(self._length)
        self._delayDataProbdist = hs.uniform(0)
        WFPadTransport.onSessionStarts(self, sessId)
#         if self._padding_mode == const.TOTAL_PADDING:
#             self.relayTotalPad(sessId, self._period, False)
#         elif self._padding_mode == const.PAYLOAD_PADDING:
#             self.relayPayloadPad(sessId, self._period, False)
#         else:
#             raise RuntimeError("Value passed for padding mode is not valid: %s" % self._padding_mode)
        if self._early_termination and self.weAreServer:
            stopCond = self.stopCondition
            def earlyTermination(self):
                return not self.session.is_peer_padding or stopCond()
            self.stopCondition = earlyTermination
        self.iat_length_tuples = [[]]
        self.getBwDifferential()

    def getAverageTs(self):
        avg_ts = mu.median(gu.get_iats([t[0] for t in gu.flatten_list(self.iat_length_tuples)]))
        log.debug("[bwdiff - %s] Average ts in the session is: %s.",
                  self.end, avg_ts)
        return avg_ts

#     def onSessionEnds(self, sessId):
#         WFPadTransport.onSessionEnds(self, sessId)
#         avg_ts = self.getAverageTs()
#         self.constantRatePaddingDistrib(avg_ts)
#         if not self._deferData or (self._deferData and self._deferData.called):
#             self._deferData = cm.deferLater(0, self.flushBuffer)

    def onEndPadding(self):
        WFPadTransport.onEndPadding(self)
        if self._early_termination and self.weAreClient:
            self.sendControlMessage(const.OP_END_PADDING)
            log.info("[bwdiff - client] - Padding stopped! Will notify server.")

    def whenReceivedUpstream(self, data):
        self.iat_length_tuples[-1].append((time.time(), const.MTU))


class BWDiffClient(BWDiffTransport):
    """Extend the BWDiffTransport class."""

    def __init__(self):
        """Initialize a BWDiffClient object."""
        BWDiffTransport.__init__(self)


class BWDiffServer(BWDiffTransport):
    """Extend the BWDiffTransport class."""

    def __init__(self):
        """Initialize a BWDiffServer object."""
        BWDiffTransport.__init__(self)
