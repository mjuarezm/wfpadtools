"""
The wfpad module implements the Tor WF framework to develop WF countermeasures.
"""
import obfsproxy.common.log as logging
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.wfpad import WFPadTransport


log = logging.get_obfslogger()


class BuFLOTransport(WFPadTransport):
    """Implementation of the BuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self, mintime=20, period=1, psize=1000):
        """Initialize the BuFLO padding scheme.

        BuFLO pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        log.debug("Using BuFLO specification.")
        self._mintime = mintime
        super(BuFLOTransport, self).__init__(
                                    time_probdist=probdist.new(lambda: period),
                                    size_probdist=probdist.new(lambda: psize))

    def stop_condition(self):
        """Returns evaluation of passing stop padding.

        BuFLO stops padding if the visit has finished and the elapsed time has
        exceeded the minimum padding time.
        """
        return self._timer.elapsed() > self._mintime \
            and self._state is const.ST_PADDING


class BuFLOClient(BuFLOTransport):
    """Extend the BuFLOTransport class."""

    def __init__(self):
        """Initialize a BuFLOClient object."""
        BuFLOTransport.__init__(self)


class BuFLOServer(BuFLOTransport):
    """Extend the BuFLOTransport class."""

    def __init__(self):
        """Initialize a BuFLOServer object."""
        BuFLOTransport.__init__(self)
