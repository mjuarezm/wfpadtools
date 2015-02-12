"""
This module implements the CS-CSBuFLO countermeasure proposed by Cai et al.
"""
import obfsproxy.common.log as logging
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport
from obfsproxy.transports.wfpadtools.util import apply_consecutive_elements,\
    flatten_list
import math
import numpy
from random import uniform


log = logging.get_obfslogger()


class CSBuFLOTransport(WFPadTransport):
    """Implementation of the CSBuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self):
        super(CSBuFLOTransport, self).__init__()

        self._rho_stats = [[]]
        self._rho_star = const.INIT_RHO

        # Set constant length for messages
        self._lengthDataProbdist = probdist.uniform(self._length)

    @classmethod
    def register_external_mode_cli(cls, subparser):
        """Register CLI arguments for CSBuFLO parameters."""
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
        subparser.add_argument("--padding",
                               required=False,
                               type=str,
                               help="Padding mode for this endpoint. There"
                                    " are two possible values: \n"
                                    "- payload: pads to the closest multiple "
                                    "of 2^N for N st 2^N closest power of two"
                                    " greater than the payload size.\n"
                                    "- total: pads to closest power of two.\n"
                                    "(Default: total).",
                               dest="padding")

        super(CSBuFLOTransport, cls).register_external_mode_cli(subparser)

    @classmethod
    def validate_external_mode_cli(cls, args):
        """Assign the given command line arguments to local variables."""
        # Defaults for BuFLO specifications.
        cls._period = 10
        cls._length = const.MPU
        cls._padding_mode = const.TOTAL_PADDING

        super(CSBuFLOTransport, cls).validate_external_mode_cli(args)

        if args.period:
            cls._period = args.period
        if args.psize:
            cls._length = args.psize
        if args.padding:
            cls._padding_mode = args.padding

    def onSessionStarts(self, sessId):
        # Initialize rho stats
        WFPadTransport.onSessionStarts(self, sessId)
        self.constantRatePaddingDistrib(self._period)
        if self._padding_mode is const.TOTAL_PADDING:
            self.relayTotalPad(sessId, self._period, False)
        elif self._padding_mode is const.PAYLOAD_PADDING:
            self.relayPayloadPad(sessId, self._period, False)
        else:
            raise RuntimeError("Value passed for padding mode is not valid")

    def onSessionEnds(self, sessId):
        super(CSBuFLOTransport, self).onSessionEnds(sessId)

        # Reset rho stats
        self._rho_stats = [[]]
        self._rho_star = const.INIT_RHO

    def whenReceivedUpstream(self):
        self._rho_stats += []
        self.whenReceived()

    def whenReceivedDownstream(self):
        self.whenReceived()

    def whenReceived(self):
        if self._rho_star == 0:
            self._rho_star = const.INIT_RHO
        else:
            self._rho_star = self.estimate_rho(self._rho_star)

    def crossed_threshold(self, total_sent_bytes):
        """Return boolean whether we need to update the transmission rate

        total_sent_bytes: amount of bytes sent downstream, namely,
        junk bytes + real data bytes.
        """
        return math.log(total_sent_bytes - const.MTU, 2) < math.log(total_sent_bytes, 2)

    def sendDataMessage(self, payload="", paddingLen=0):
        """Send data message."""
        super(CSBuFLOTransport, self).sendDataMessage(payload, paddingLen)
        self._rho_stats[-1].append(reactor.seconds())
        self.update_transmission_rate()

    def estimate_rho(self, rho_star):
        """Estimate new value of rho based on past network performance."""
        time_intervals = flatten_list([apply_consecutive_elements(burst_list,
                                                                  lambda x, y: y - x)
                                       for burst_list in self._rho_stats])
        if len(time_intervals) == 0:
            return rho_star
        else:
            return math.pow(2, math.floor(math.log(numpy.median(time_intervals), 2)))

    def update_transmission_rate(self):
        self._period = uniform(0, 2 * self._rho_star)
        self.constantRatePaddingDistrib(self._period)

    def relayBatchPad(self, sessId, L, t, msg_level=True):
        """Pad all batches of cells to the nearest multiple of `L` cells/bytes total.

        Set the stop condition to satisfy the number of messages (or bytes)
        sent within the session is a multiple of the parameter `L` and that the
        session has finished.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        L : int
            The multiple of cells to pad to.
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)
        to_pad = self._numMessages['snd'] if msg_level else self._dataBytes['snd']

        def stopConditionBatchPad(s):
            stopCond = to_pad > 0 and to_pad % L == 0 and not self.isVisiting()
            log.debug("[wfpad] - Batch pad stop condition is %s."
                      "\n Visiting: %s, Num snd msgs: %s, L: %s"
                      % (stopCond, self.isVisiting(), self._numMessages, L))
            return stopCond
        self.stopCondition = stopConditionBatchPad


class CSBuFLOClient(CSBuFLOTransport):
    """Extend the CSBuFLOTransport class."""

    def __init__(self):
        """Initialize a CSBuFLOClient object."""
        CSBuFLOTransport.__init__(self)


class CSBuFLOServer(CSBuFLOTransport):
    """Extend the CSBuFLOTransport class."""

    def __init__(self):
        """Initialize a CSBuFLOServer object."""
        CSBuFLOTransport.__init__(self)
