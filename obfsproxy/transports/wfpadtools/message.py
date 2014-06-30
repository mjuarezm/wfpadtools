"""This module provides methods to handle WFPad protocol messages.

The exported classes and functions provide interfaces to handle protocol
messages, check message headers for validity and create protocol messages out
of application data.

This module is basically the same as ScrambleSuit's message but modified to
our protocol specification.
"""
import random

import obfsproxy.transports.base as base
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import const

import obfsproxy.common.log as logging
import obfsproxy.common.serialize as pack

log = logging.get_obfslogger()


class WFPadMessage(object):
    """Represents a WFPad protocol message.

    This class provides methods to deal with WFPad protocol messages.
    """
    def __init__(self, payload="", paddingLen=0, flags=const.FLAG_DATA,
                        opcode=None):
        payloadLen = len(payload)
        if (payloadLen + paddingLen) > const.MPU:
            raise base.PluggableTransportError("No overly long messages.")
        self.totalLen = payloadLen + paddingLen
        self.payloadLen = payloadLen
        self.payload = payload
        self.flags = flags
        self.opcode = opcode

    def __str__(self):
        """Return message as string."""
        str_opcode = '' if self.opcode is None else chr(self.opcode)
        return pack.htons(self.totalLen) + \
                    pack.htons(self.payloadLen) + \
                    chr(self.flags) + str_opcode + \
                    self.payload + \
                    (self.totalLen - self.payloadLen) * '\0'

    def __len__(self):
        """Return the length of this protocol message."""
        if self.opcode:
            return const.HDR_CTRL_LENGTH + self.totalLen
        else:
            return const.HDR_LENGTH + self.totalLen


class WFPadMessageFactory(object):
    """Creates WFPad's protocol messages."""

    def __init__(self, len_dist=None):
        """Initialize the WFPadMessageFactory with the distribution `len_dist`.

        If `len_dist` is `None`, a new discrete probability distribution is
        generated randomly.
        """
        if len_dist:
            self.len_dist = len_dist
        else:
            self.len_dist = probdist.new(lambda: random.randint(
                                                const.HDR_LENGTH,
                                                const.MTU),
                                         lambda i, n, c: 1)

    def set_len_distribution(self, new_len_dist):
        """Set a new length probability distribution."""
        self.len_dist = new_len_dist

    def createWFPadMessage(self, payload="", paddingLen=0,
                           flags=const.FLAG_DATA, opcode=None):
        return WFPadMessage(payload, paddingLen, flags, opcode)

    def createWFPadMessages(self, data, flags=const.FLAG_DATA):
        """Create protocol messages out of the given payload.

        The given `data` is turned into a list of protocol messages with the
        given `flags` set. The list is then returned.
        """
        messages = []
        while len(data) > 0:
            msg_len = self.len_dist.randomSample()
            data_len = len(data)
            if data_len > msg_len:
                messages.append(self.createWFPadMessage(data[:msg_len]))
                data = data[msg_len:]
            else:
                messages.append(self.createWFPadMessage(data[:data_len],
                                             paddingLen=msg_len - data_len))
                data = data[data_len:]
        log.debug("Created %d protocol messages." % len(messages))
        return messages


def getFlagNames(flags):
    """Return the flag name encoded in the integer `flags` as string.

    This function is only useful for printing easy-to-read flag names in
    debug log messages.
    """
    if flags == const.FLAG_DATA:
        return "DATA"
    elif flags == const.FLAG_PADDING:
        return "PADDING"
    elif flags == const.FLAG_CONTROl:
        return "CONTROL"
    else:
        return "Undefined"


def isSane(totalLen, payloadLen, flags):
    """Verifies whether the given header fields are sane.

    The values of the fields `totalLen`, `payloadLen` and `flags` are
    checked for their sanity.  If they are in the expected range, `True` is
    returned. If any of these fields has an invalid value, return `False`.
    """
    def isFine(length):
        """Check if the given length is fine."""
        return True if (0 <= length <= const.MPU) else False

    log.debug("Message header: totalLen=%d, payloadLen=%d, flags"
              "=%s" % (totalLen, payloadLen, getFlagNames(flags)))

    validFlags = [
        const.FLAG_DATA,
        const.FLAG_PADDING,
        const.FLAG_CONTROl
    ]

    return isFine(totalLen) and \
           isFine(payloadLen) and \
           totalLen >= payloadLen and \
           (flags in validFlags)


class WFPadMessageExtractor(object):
    """Extracts WFPad protocol messages out of the stream."""
    def __init__(self):
        self.recvBuf = ""
        self.totalLen = None
        self.payloadLen = None
        self.flags = None
        self.opcode = None

    def get_field(self, position, length):
        return self.recvBuf[position:position + length]

    def parse(self):
        """Extract header fields, if necessary."""
        if self.totalLen == self.payloadLen == self.flags == None:
            self.totalLen = pack.ntohs(self.get_field(const.TOTLENGTH_POS,
                                                      const.TOTLENGTH_LEN))
            self.payloadLen = pack.ntohs(self.get_field(const.PAYLOAD_POS,
                                                        const.PAYLOAD_LEN))
            self.flags = ord(self.get_field(const.FLAGS_POS,
                                            const.FLAGS_LEN))

            if not isSane(self.totalLen, self.payloadLen, self.flags):
                raise base.PluggableTransportError("Invalid header.")

            if self.flags == const.FLAG_CONTROl:
                self.opcode = ord(self.get_field(const.CONTROL_POS,
                                                 const.CONTROL_LEN))

    def filter(self):
        """Filter padding messages out and remove data messages from buffer."""
        if self.flags == const.FLAG_CONTROl:
            # If it's a control message, extract payload for piggybacking
            extracted = self.recvBuf[const.HDR_CTRL_LENGTH:
                     (self.totalLen + const.HDR_CTRL_LENGTH)][:self.payloadLen]
        else:
            extracted = self.recvBuf[const.HDR_LENGTH:
                     (self.totalLen + const.HDR_LENGTH)][:self.payloadLen]
        return extracted

    def reset(self):
        # Protocol message processed; now reset length fields.
        self.recvBuf = self.recvBuf[const.HDR_LENGTH + self.totalLen:]
        self.totalLen = self.payloadLen = self.flags = self.opcode = None

    def extract(self, data):
        """Extracts WFPad protocol messages.

        The data is then returned as protocol messages. In case of
        invalid headers an exception is raised.
        """
        self.recvBuf += data
        msgs = []

        # Keep trying to unpack as long as there is at least a header.
        while len(self.recvBuf) >= const.HDR_LENGTH:
            self.parse()
            # Parts of the message are still on the wire; waiting.
            if (len(self.recvBuf) - const.HDR_LENGTH) < self.totalLen:
                break
            extracted = self.filter()
            msgs.append(WFPadMessage(payload=extracted,
                                     flags=self.flags,
                                     opcode=self.opcode))
            self.reset()
        return msgs
