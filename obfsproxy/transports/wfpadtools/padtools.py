from twisted.internet import reactor
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut
import obfsproxy.common.log as logging

log = logging.get_obfslogger()


class ControlMessageReceiver(object):

    def receiveControlMessage(self, opcode, args=None):
        """Do operation indicated by the _opcode."""
        log.error("Received control message with opcode %d and args: %s"
                  % (opcode, args))
#         if opcode == const.OP_START:  # Generic primitives
#             self.startPadding()
#         elif opcode == const.OP_STOP:
#             self.stopPadding()
        if opcode == const.OP_IGNORE:
            self.sendIgnore()
        elif opcode == const.OP_SEND_PADDING:
            self.sendPadding(*args)
        elif opcode == const.OP_APP_HINT:
            self.appHint(*args)
        elif opcode == const.OP_BURST_HISTO:  # Adaptive padding primitives
            self.burstHistogram(*args)
        elif opcode == const.OP_GAP_HISTO:
            self.gapHistogram(*args)
        elif opcode == const.OP_INJECT_HISTO:
            self.injectHistogram(*args)
        elif opcode == const.OP_TOTAL_PAD:  # CS-BuFLO primitives
            self.totalPad(*args)
        elif opcode == const.OP_PAYLOAD_PAD:
            self.payloadPad(*args)
        elif opcode == const.OP_BATCH_PAD:  # Tamaraw primitives
            self.batchPad(*args)
        else:
            log.error("The received operation code is not recognized.")

    def sendIgnore(self, N=1):
        """Reply with a padding message."""
        for _ in xrange(N):
            reactor.callLater(0, self.encapsulateBufferData)

    def sendPadding(self, N, t):
        """Reply with `N` padding messages delayed `t` ms."""
        reactor.callLater(t, self.sendIgnore, N)

    def appHint(self, sessId, status):
        """Provides information to the server about the current session.

        Limitation: we assume the user is browsing in a single tab.
        """
        self._visiting = status

    def burstHistogram(self, histo, labels, remove_toks=False):
        """Replies to a burst_histo request.

        Parameters
        ----------
        histo : list
                contains delay distribution of sending an IGNORE packet after
                sending an *real* packet (with "Infinity" bin to indicate run
                termination probability).
        labels_ms : list
                    millisecond labels for the bins
        remove_toks : bool
                      if true, follow Adaptive Padding token removal rules.
                      If false, histograms are immutable.
        """
        pass

    def gapHistogram(self, histo, labels, remove_toks=False):
        """Replies to a gap_histo request.

        Parameters
        ----------
        histo : list
                contains delay distribution of sending an IGNORE packet after
                sending an IGNORE packet (with "Infinity" bin to indicate run
                termination probability).
        labels_ms : list
                    millisecond labels for the bins
        remove_toks : bool
                      if true, follow Adaptive Padding token removal rules.
                      If false, histograms are immutable.
        """
        pass

    def injectHistogram(self, histo, labels):
        """Replies to an inject_histogram request.

        Parameters
        ----------
        histo : list
                contains probability distribution of sending an IGNORE packet
                if the wire was completely silent for that amount of time.
        labels_ms : list
                    millisecond labels for the bins

        Note: This is not an Adaptive Padding primitive, but it seems
        useful to model push-based protocols (like XMPP).
        """
        pass

    def totalPad(self):
        pass

    def payloadPad(self, sess_id, t):
        """Pad all batches to 2^K cells total.

        Pad all batches to 2^K cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    def batchPad(self, sess_id, L, t):
        """Pad all batches to L cells total.

        Pad all batches to `L` cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass


class ControlMessageSender(object):

    def sendControlMessage(self, encapsulateBufferData, opcode, args=None, delay=0):
        """Send a message with a specific _opcode field."""
        reactor.callLater(delay,
                          encapsulateBufferData,
                          opcode=opcode,
                          args=args)

    def sendStartPaddingRequest(self):
        """Send a start padding as control message."""
        self.sendControlMessage(const.OP_START)

    def sendStopPaddingRequest(self):
        """Send a start padding as control message."""
        self.sendControlMessage(const.OP_STOP)

    def sendIgnoreRequest(self):
        """Send an ignore request as control message."""
        self.sendControlMessage(const.OP_IGNORE)

    def sendPaddingCellsRequest(self, N, t):
        """Send an ignore request as control message."""
        self.sendControlMessage(const.OP_SEND_PADDING,
                                args=[N, t])

    def sendAppHintRequest(self, sessNumber, status=True):
        """Send an app hint request as control message.

        We hash the session number, the PT object id and a timestamp
        in order to get a unique identifier.

        Parameters
        ----------
        sessNumber : int
        status : boolean
                indicates whether a session starts (True) or ends (False).
        """
        sessId = ut.hash_text(str(sessNumber)
                               + str(id(self))
                               + str(ut.timestamp()))
        self.sendControlMessage(const.OP_APP_HINT, args=[sessId, status])

    def sendBurstHistogram(self, histo, labels, remove_toks=False):
        self.sendControlMessage(const.OP_BURST_HISTO,
                                args=[histo, labels, remove_toks])

    def sendGapHistogram(self, histo, labels, remove_toks=False):
        self.sendControlMessage(const.OP_GAP_HISTO,
                                args=[histo, labels, remove_toks])

    def sendInjectHistogram(self, histo, labels):
        self.sendControlMessage(const.OP_INJECT_HISTO, args=[histo, labels])

    def sendTotalPadRequest(self):
        pass

    def sendPayloadPadRequest(self, sess_id, t):
        """Pad all batches to 2^K cells total.

        Pad all batches to 2^K cells total within `t` microseconds,
        or until APP_HINT(session_id, stop).
        """
        pass

    def sendBatchPadRequest(self, sess_id, L, t):
        pass
