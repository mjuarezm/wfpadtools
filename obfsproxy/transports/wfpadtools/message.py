"""This module provides code to handle WFPad protocol messages.

The exported classes and functions provide interfaces to handle protocol
messages, check message headers for validity and create protocol messages out
of application data. It also filters padding messages out of the stream.

This module is basically the same as ScrambleSuit's but modified to our
protocol specification.
"""
import obfsproxy.common.log as logging
import obfsproxy.common.serialize as pack
import obfsproxy.transports.base as base
from obfsproxy.transports.wfpadtools import const


log = logging.get_obfslogger()


def createWFPadMessages(data, flags=const.FLAG_DATA):
    """Create protocol messages out of the given payload.

    The given `data` is turned into a list of protocol messages with the given
    `flags` set.  The list is then returned.
    """
    messages = []

    while len(data) > const.MPU:
        messages.append(WFPadMessage(data[:const.MPU], flags=flags))
        data = data[const.MPU:]

    messages.append(WFPadMessage(data, flags=flags))

    log.debug("Created %d protocol messages." % len(messages))

    return messages


def getFlagNames(flags):
    """Return the flag name encoded in the integer `flags` as string.

    This function is only useful for printing easy-to-read flag names in debug
    log messages.
    """
    if flags == const.FLAG_DATA:
        return "DATA"
    elif flags == const.FLAG_PADDING:
        return "PADDING"
    else:
        return "Undefined"


def isSane(totalLen, payloadLen, flags):
    """Verifies whether the given header fields are sane.

    The values of the fields `totalLen`, `payloadLen` and `flags` are checked
    for their sanity.  If they are in the expected range, `True` is returned.
    If any of these fields has an invalid value, `False` is returned.
    """
    def isFine(length):
        """Check if the given length is fine."""
        return True if (0 <= length <= const.MPU) else False

    log.debug("Message header: totalLen=%d, payloadLen=%d, flags"
              "=%s" % (totalLen, payloadLen, getFlagNames(flags)))

    validFlags = [
        const.FLAG_DATA,
        const.FLAG_PADDING
    ]

    return isFine(totalLen) and \
           isFine(payloadLen) and \
           totalLen >= payloadLen and \
           (flags in validFlags)


class WFPadMessage(object):
    """Represents a WFPad protocol message.

    This class provides methods to deal with protocol messages.
    """
    def __init__(self, payload="", paddingLen=0, flags=const.FLAG_DATA):
        payloadLen = len(payload)
        if (payloadLen + paddingLen) > const.MPU:
            raise base.PluggableTransportError("No overly long messages.")

        self.totalLen = payloadLen + paddingLen
        self.payloadLen = payloadLen
        self.payload = payload
        self.flags = flags

    def __str__(self):
        """Return message as string."""
        return pack.htons(self.totalLen) + \
                    pack.htons(self.payloadLen) + \
                    chr(self.flags) + self.payload + \
                    (self.totalLen - self.payloadLen) * '\0'

    def __len__(self):
        """Return the length of this protocol message."""
        return const.HDR_LENGTH + self.totalLen


class WFPadMessageExtractor(object):
    """Extracts WFPad protocol messages out of the stream."""
    def __init__(self):
        self.recvBuf = ""
        self.totalLen = None
        self.payloadLen = None
        self.flags = None

    def get_field(self, position, length):
        return self.recvBuf[position:position + length]

    def extract(self, data):
        """Extracts WFPad protocol messages.

        The data is then returned as protocol messages. In case of
        invalid headers an exception is raised.
        """
        self.recvBuf += data
        msgs = []

        # Keep trying to unpack as long as there is at least a header.
        while len(self.recvBuf) >= const.HDR_LENGTH:

            # If necessary, extract the header fields.
            if self.totalLen == self.payloadLen == self.flags == None:
                self.totalLen = pack.ntohs(self.get_field(const.TOTLENGTH_POS,
                                                          const.TOTLENGTH_LEN))
                self.payloadLen = pack.ntohs(self.get_field(const.PAYLOAD_POS,
                                                            const.PAYLOAD_LEN))
                self.flags = ord(self.get_field(const.FLAGS_POS,
                                                const.FLAGS_LEN))

                if not isSane(self.totalLen, self.payloadLen, self.flags):
                    raise base.PluggableTransportError("Invalid header.")

            # Parts of the message are still on the wire; waiting.
            if (len(self.recvBuf) - const.HDR_LENGTH) < self.totalLen:
                break

            # Filter padding messages out and remove data messages the buffer.
            extracted = self.recvBuf[const.HDR_LENGTH:
                         (self.totalLen + const.HDR_LENGTH)][:self.payloadLen]
            msgs.append(WFPadMessage(payload=extracted, flags=self.flags))
            self.recvBuf = self.recvBuf[const.HDR_LENGTH + self.totalLen:]

            # Protocol message processed; now reset length fields.
            self.totalLen = self.payloadLen = self.flags = None

        return msgs
