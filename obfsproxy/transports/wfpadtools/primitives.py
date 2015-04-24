from twisted.internet import defer
from obfsproxy.transports.wfpadtools.common import deferLater
import obfsproxy.transports.wfpadtools.histo as hist
from obfsproxy.transports.wfpadtools.util.mathutil import closest_power_of_two, \
    closest_multiple

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class PaddingPrimitivesInterface(object):
    """Padding primitives that can be used by any PT transport.

    See:
    gitweb.torproject.org/user/mikeperry/torspec.git/blob/refs/heads/multihop-padding-primitives:/proposals/ideas/xxx-multihop-padding-primitives.txt
    """
    def relaySendPadding(self, N, t):
        """Send the requested number of padding cells in response.

        Parameters
        ----------
        N : int
            Number of padding cells to send in response to this cell.
        t : int
            Number of milliseconds delay before sending.
        """
        millisec = t
        deferreds = []
        for _ in xrange(N):
            deferreds.append(deferLater(millisec, self.sendIgnore))
        return defer.DeferredList(deferreds, consumeErrors=True)

    def relayAppHint(self, sessId, status):
        """A hint from the application layer for session start/end.

        Parameters
        ----------
        sessId : str
                 Identifies the session (e.g., keyed hash of URL bar domain).
        status : bool
                 True or False, indicating session start and end respectively.
        """
        if self.weAreServer:
            self._visiting = status
        if status:
            self.onSessionStarts(sessId)
        else:
            self.onSessionEnds(sessId)


    def relayBurstHistogram(self, histo, labels, removeToks=False,
                            interpolate=True, when="rcv"):
        """Specify histogram encoding the delay distribution.

        The delay distribution represents the probability of sending a single
        padding packet after a given delay in response to either an upstream
        cell, or a client-originating cell.

        Parameters
        ----------
        histo : list
            Contains delay distribution of sending an IGNORE cell after
            sending an IGNORE cell.
        labels : list
            Millisecond labels for the bins (with "infinity" bin to allow
            encoding the probability of not sending any padding packet in
            response to this packet).
        removeToks : bool
            If True, follow Adaptive Padding token removal rules.
            If False, histograms are immutable.
        interpolate : bool
            If True, randomize the delay uniformly between bin labels
            If False, use bin labels as exact delay values.
        when : str
            If set to "rcv", this histogram governs the probability of
            sending a padding packet after some delay in response to a packet
            originating from the other PT end. If set to "snd", this histogram
            governs padding packets that are transmitted after a packet
            arrives from upstream. In both cases, the padding packet is
            sent in the direction of the client.
        """
        self._burstHistoProbdist[when] = hist.new(histo, labels,
                                                  interpolate=bool(interpolate),
                                                  removeToks=bool(removeToks))
        self._deferBurstCallback[when] = self._burstHistoProbdist[when].removeToken


    def relayGapHistogram(self, histo, labels, removeToks=False,
                          interpolate=True, when="rcv"):
        """Specify histogram that encodes the delay distribution

        The delay distribution represents the probability of sending a
        single additional padding packet after a given delay following
        a padding packet that originated at this hop. In both cases, the
        padding packet is sent in the direction of the client.

        Parameters
        ----------
        histo : list
            Contains delay distribution of sending an IGNORE cell after
            sending an IGNORE cell.
        labels : list
            Millisecond labels for the bins (with "infinity" bin to allow
            encoding the probability of not sending any padding packet in
            response to this packet).
        removeToks : bool
            If True, follow Adaptive Padding token removal rules.
            If False, histograms are immutable.
        interpolate : bool
            If True, randomize the delay uniformly between bin labels
            If False, use bin labels as exact delay values.
        when : str
            If "rcv", this histogram applies to locally-inserted padding
            packets that were initially sent in response to client-originated
            data.  If "snd", this histogram applies to packets sent in response
            to locally-inserted padding packets sent in response to upstream
            data. Note that this means that implementations must maintain this
            metadata as internal state as the system transitions from
            BURST_HISTOGRAM initiated padding into GAP_HISTOGRAM initiated
            padding.
        """
        self._gapHistoProbdist[when] = hist.new(histo, labels,
                                                interpolate=bool(interpolate),
                                                removeToks=bool(removeToks))
        self._deferGapCallback[when] = self._gapHistoProbdist[when].removeToken


    def relayTotalPad(self, sessId, t, msg_level=True):
        """Pad all batches to nearest 2^K cells total.

        Set the stop condition to satisfy that the number of messages
        sent within the session is a power of 2 (otherwise it will continue
        padding until the closest one) and that the session has finished.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        msg_level : bool
            Sets whether the data to pad is at message level or at byte level.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)

        def stopConditionTotalPadding(self):
            to_pad = self.session.numMessages['snd'] if msg_level else self.session.totalBytes['snd']
            total_padding = closest_power_of_two(to_pad)
            log.debug("[wfpad %s] - Computed total padding: %s (to_pad is %s)",
                      self.end, total_padding, to_pad)
            return total_padding

        def stopConditionTotalPad(s):
            if s.isVisiting():
                log.debug("[wfpad %s] - False stop condition, still visiting...", self.end)
                return False
            to_pad = s.session.numMessages['snd'] \
                if msg_level else s.session.totalBytes['snd']
            stopCond = to_pad > 0 and to_pad >= self.session.totalPadding
            log.debug("[wfpad %s] - Total pad stop condition is %s."
                      "\n Visiting: %s, Total padding: %s, Num msgs: %s, Total Bytes: %s, "
                      "Num data msgs: %s, Data Bytes: %s, to_pad: %s"
                      % (self.end, stopCond, self.isVisiting(), self.session.totalPadding, self.session.numMessages,
                         self.session.totalBytes, self.session.dataMessages, self.session.dataBytes, to_pad))
            return stopCond

        self.stopCondition = stopConditionTotalPad
        self.calculateTotalPadding = stopConditionTotalPadding


    def relayPayloadPad(self, sessId, t, msg_level=True):
        """Pad until the total sent data is multiple of 2^int(log(TOTAL_PAYLOAD))

        Set the stop condition to satisfy the number of TOTAL messages (or
        bytes), both fake and real data, are a multiple of the closest power
        of two to the amount of real units (messages or bytes), and that the
        session has finished.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        msg_level : bool
            Sets whether the data to pad is at message level or at byte level.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)

        def stopConditionPayloadPadding(self):
            to_pad = self.session.numMessages['snd'] if msg_level else self.session.totalBytes['snd']
            divisor = self.session.dataMessages['snd'] if msg_level else self.session.dataBytes['snd']
            k = closest_power_of_two(divisor)
            total_padding = closest_multiple(to_pad, k)
            log.debug("[wfpad %s] - Computed payload padding: %s (to_pad is %s and divisor is %s)"
                      % (self.end, total_padding, to_pad, divisor))
            return total_padding

        def stopConditionPayloadPad(self):
            if self.isVisiting():
                log.debug("[wfpad %s] - False stop condition, still visiting...", self.end)
                return False
            to_pad = self.session.numMessages['snd'] if msg_level else self.session.totalBytes['snd']
            stopCond = to_pad > 0 and to_pad >= self.session.totalPadding
            log.debug("[wfpad %s] - Payload pad stop condition is %s."
                      "\n Visiting: %s, Total padding: %s, Num msgs: %s, Total Bytes: %s"
                      % (self.end, stopCond, self.isVisiting(), self.session.totalPadding, self.session.numMessages, self.session.totalBytes))
            return stopCond

        self.stopCondition = stopConditionPayloadPad
        self.calculateTotalPadding = stopConditionPayloadPadding


    def relayBatchPad(self, sessId, L, t, msg_level=True):
        """Pad all batches of cells to the nearest multiple of `L` cells/bytes total.

        Set the stop condition to satisfy the number of messages (or bytes)
        sent within the session is a multiple of the parameter `L` and that the
        session has finished. We count both padding and data messages.

        Parameters
        ----------
        sessId : str
            The session ID from relayAppHint().
        L : int
            The multiple of cells to pad to.
        t : int
            The number of milliseconds to wait between cells to consider them
            part of the same batch.
        msg_level : bool
            Sets whether the data to pad is at message level or at byte level.
        """
        self._sessId = sessId
        self.constantRatePaddingDistrib(t)

        def stopConditionBatchPadding(self):
            to_pad = self.session.numMessages['snd'] if msg_level else self.session.totalBytes['snd']
            total_padding = closest_multiple(to_pad, L)
            log.debug("[wfpad %s] - Computed batch padding: %s (to_pad is %s)"
                      % (self.end, total_padding, to_pad))
            return total_padding

        def stopConditionBatchPad(self):
            if self.isVisiting():
                log.debug("[wfpad %s] - False stop condition, still visiting...", self.end)
                return False
            to_pad = self.session.numMessages['snd'] if msg_level else self.session.totalBytes['snd']
            stopCond = to_pad > 0 and to_pad >= self.session.totalPadding
            log.debug("[wfpad %s] - Batch pad stop condition is %s."
                      "\n Visiting: %s, Total padding: %s, Num msgs: %s, Total Bytes: %s, L: %s"
                      % (
                self.end, stopCond, self.isVisiting(), self.session.totalPadding, self.session.numMessages, self.session.totalBytes, L))
            return stopCond

        self.stopCondition = stopConditionBatchPad
        self.calculateTotalPadding = stopConditionBatchPadding
