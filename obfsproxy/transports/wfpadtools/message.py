"""This module provides methods to handle WFPad protocol messages.

The exported classes and functions provide interfaces to handle protocol
messages, check message headers for validity and create protocol messages out
of application data.

This module is basically the same as ScrambleSuit's message but modified to
our protocol specification.
"""
import json
import math
from obfsproxy.transports.wfpadtools import const

import obfsproxy.common.log as logging
import obfsproxy.common.serialize as pack
import obfsproxy.transports.base as base


log = logging.get_obfslogger()


class WFPadMessage(object):
    """Represents a WFPad protocol data unit."""

    def __init__(self, payload='', paddingLen=0,
                        flags=const.FLAG_DATA, opcode=None, args=""):
        """Create a new instance of `WFPadMessage`."""
        self.payload = payload
        self.payloadLen = len(self.payload)
        self.totalLen = self.payloadLen + paddingLen

        if (self.totalLen) > const.MPU:
            raise base.PluggableTransportError("No overly long messages.")

        self.flags = flags
        self.opcode = opcode
        self.argsLen = len(args)
        self.args = args

    def generatePadding(self):
        return (self.totalLen - self.payloadLen) * '\0'

    def __str__(self):
        """Return string representation of the message."""
        opCodeStr = argsLenStr = ""
        totalLenStr = pack.htons(self.totalLen)
        payloadLenStr = pack.htons(self.payloadLen)
        flagsStr = chr(self.flags)

        headerStr = totalLenStr + payloadLenStr + flagsStr
        if self.opcode:
            opCodeStr = chr(self.opcode)
            argsLenStr = pack.htons(self.argsLen)
            headerStr += opCodeStr + argsLenStr

        paddingStr = self.generatePadding()
        payloadStr = self.args + self.payload + paddingStr
        return headerStr + payloadStr

    def __len__(self):
        """Return the length of this protocol message."""
        headerLen = const.HDR_CTRL_LEN if self.flags is const.FLAG_CONTROL \
                    else const.MIN_HDR_LEN
        msgLen = headerLen + self.totalLen
        if self.args:
            msgLen += self.argsLen
        return msgLen


class WFPadMessageFactory(object):
    """Creates WFPad's protocol messages."""

    def new(self, payload="", paddingLen=0,
                    flags=const.FLAG_DATA, opcode=None, args=""):
        """Create a new WFPad message."""
        return WFPadMessage(payload, paddingLen, flags, opcode, args)

    def newIgnore(self, paddingLen):
        """Shortcut to create a new dummy message."""
        return self.new("", paddingLen, const.FLAG_PADDING)

    def newControl(self, opcode, args="", payload="", paddingLen=0):
        """Shortcut to create a single control message."""
        if len(args) > const.MPU:
            raise base.PluggableTransportError("Args are too long.")
        return self.new(payload, paddingLen, const.FLAG_CONTROL, opcode, args)

    def getSamplePayloadLength(self, probDist, flags=const.FLAG_DATA):
        """Return payload length sampling from probability distribution."""
        if probDist:
            payloadLen = probDist.randomSample()
            if payloadLen is not const.INF_LABEL:
                return payloadLen
        return const.MPU_CTRL if flags is const.FLAG_CONTROL else const.MPU

    def encapsulate(self, data="", opcode=None, args=None, lenProbdist=None):
        """Wrap data into WFPad protocol messages."""
        assert(data or opcode)

        messages = []
        if data:
            messages = self._encapsulateData(data, lenProbdist)
        else:
            messages = self._encapsulateCtrl(opcode, args, data, lenProbdist)

        log.debug("[wfpad] Created %d protocol messages." % len(messages))
        return messages

    def _encapsulateData(self, data, lenProbdist=None):
        """Wrap data into WFPad data messages."""
        messages = []
        while len(data) > 0:
            payloadLen = self.getSamplePayloadLength(lenProbdist)
            dataLen = len(data)
            if dataLen > payloadLen:
                messages.append(self.new(data[:payloadLen]))
                data = data[payloadLen:]
            else:
                paddingLen = payloadLen - dataLen
                messages.append(self.new(data[:dataLen], paddingLen))
                data = data[dataLen:]
        return messages

    def _encapsulateCtrl(self, opcode, args=None, data="", lenProbdist=None):
        """Wrap data into WFPad control messages."""
        messages = []
        strArgs = json.dumps(args)

        while len(strArgs) > 0:
            payloadLen = self.getSamplePayloadLength(lenProbdist,
                                                     const.FLAG_CONTROL)
            argsLen = len(strArgs)

            if argsLen > payloadLen:
                messages.append(self.newControl(opcode, strArgs[:payloadLen],
                                                "", 0))
            else:
                pbckLen = const.MPU_CTRL - argsLen
                dataLen = len(data)
                pbckData = data[:pbckLen] if dataLen > 0 else ""
                paddingLen = dataLen - pbckLen if pbckLen < dataLen else 0
                messages.append(self.newControl(opcode, strArgs[:payloadLen],
                                                pbckData, paddingLen))
                data = data[pbckLen:]
            strArgs = strArgs[payloadLen:]

        if len(data) > 0:
            messages += self.encapsulate(data, lenProbdist)

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
    elif flags == const.FLAG_CONTROL:
        return "CONTROL"
    else:
        return "Undefined"


def getOpcodeNames(opcode):
    """Return the opcode encoded in the integer `opcode` as string.

    This function is only useful for printing easy-to-read opcode names in
    debug log messages.
    """
    if opcode == const.OP_SEND_PADDING:
        return "RELAY SEND_PADDING"
    elif opcode == const.OP_APP_HINT:
        return "RELAY APP_HINT"
    elif opcode == const.OP_BURST_HISTO:
        return "RELAY BURST_HISTOGRAM"
    elif opcode == const.OP_GAP_HISTO:
        return "RELAY GAP_HISTOGRAM"
    elif opcode == const.OP_TOTAL_PAD:
        return "RELAY TOTAL_PAD"
    elif opcode == const.OP_PAYLOAD_PAD:
        return "RELAY PAYLOAD_PAD"
    elif opcode == const.OP_BATCH_PAD:
        return "RELAY BATCH_PAD"
    else:
        return "Undefined"


def isSane(totalLen, payloadLen, flags):
    """Verify whether the given header fields are correct.

    The values of the fields `totalLen`, `payloadLen` and `flags` are
    checked for their sanity.  If they are in the expected range, `True` is
    returned. If any of these fields has an invalid value, return `False`.
    """
    def isFine(length):
        """Check if the given length is fine."""
        return True if (0 <= length <= const.MPU) else False

    log.debug("[wfpad] Message header: totalLen=%d, payloadLen=%d, flags"
              "=%s" % (totalLen, payloadLen, getFlagNames(flags)))

    validFlags = [
        const.FLAG_DATA,
        const.FLAG_PADDING,
        const.FLAG_CONTROL,
        const.FLAG_CONTROL + const.FLAG_DATA,
        const.FLAG_CONTROL + const.FLAG_PADDING
    ]

    return isFine(totalLen) and isFine(payloadLen) and \
           totalLen >= payloadLen and (flags in validFlags)


def isOpCodeSane(opcode):
    """Verify the the extra control message fields are correct."""

    log.debug("[wfpad] Opcode: value=%s, name=%s"
              % (opcode, getOpcodeNames(opcode)))

    validOpCodes = [
        const.OP_APP_HINT,
        const.OP_BATCH_PAD,
        const.OP_BURST_HISTO,
        const.OP_GAP_HISTO,
        const.OP_INJECT_HISTO,
        const.OP_PAYLOAD_PAD,
        const.OP_SEND_PADDING,
        const.OP_TOTAL_PAD
    ]

    return (opcode in validOpCodes)


class WFPadMessageExtractor(object):
    """Extracts WFPad protocol messages out of the stream.

    We first parse all the fields up to the `flags` field. Then,
    depending on the flag we continue parsing the `opcode`, `args`
    and `payload` fields.
    """

    def __init__(self):
        """Create a new WFPadMessageExtractor object."""
        self.totalLen = self.payloadLen = self.flags = self.opcode = None
        self.argsLen = self.argsParseLen = 0
        self.recvBuf = self.args = ""

    def getHeaderLen(self):
        if self.flags:
            return const.HDR_CTRL_LEN if self.flags is const.FLAG_CONTROL \
                    else const.MIN_HDR_LEN
        return 0

    def getNumMsgsFromSize(self, size, mpu):
        """Return number of WFPad messages required for `size` bytes."""
        return int(math.ceil(size / float(mpu)))

    def getParseLength(self, size, mpu):
        """Return the length of the arguments in the last control message."""
        return size - (self.getNumMsgsFromSize(size, mpu) - 1) * mpu

    def getMessageField(self, position, length):
        """Return chunk of `length` starting at `position` in the buffer."""
        return self.recvBuf[position:position + length]

    def getFlags(self):
        """Return `flags` field from buffer."""
        return ord(self.getMessageField(const.FLAGS_POS,
                                        const.FLAGS_LEN))

    def getPayloadLen(self):
        """Return `payloadLen` field from buffer."""
        return pack.ntohs(self.getMessageField(const.PAYLOAD_POS,
                                               const.PAYLOAD_LEN))

    def getTotalLen(self):
        """Return `totalLen` field from buffer."""
        return pack.ntohs(self.getMessageField(const.TOTLENGTH_POS,
                                               const.TOTLENGTH_LEN))

    def getOpCode(self):
        """Return `opcode` field from buffer."""
        return ord(self.getMessageField(const.CONTROL_POS,
                                        const.CONTROL_LEN))

    def getargsLen(self):
        """Return `argsLen` field from buffer."""
        return pack.ntohs(self.getMessageField(const.ARGS_TOTAL_LENGTH_POS,
                                               const.ARGS_TOTAL_LENGTH_LEN))

    def getPayload(self, start):
        """Return `payload` from buffer."""
        totalPayload = self.getMessageField(start, self.totalLen)
        return totalPayload[:self.payloadLen]  # Strip padding

    def dumpState(self, toLog=False):
        """Dumps state to a file or to stdout."""
        state = "WFPad extractor state: " + "\n" \
                + "Total length: " + str(self.totalLen) + "\n" \
                + "Payload length: " + str(self.payloadLen) + "\n" \
                + "Flags: " + str(self.flags) + "\n" \
                + "Opcode: " + str(self.opcode) + "\n" \
                + "Args length: " + str(self.argsLen) + "\n" \
                + "Parsed args length: " + str(self.argsParseLen) + "\n" \
                + "Args: " + self.args + "\n" \
                + "Rcv buffer: " + self.recvBuf

        if toLog:
            log.debug(state)
        else:
            print state

    def reset(self):
        """Reset class properties to their initial value.

        We call this function whenever a new message has been processed
        in order to reset its properties. We must store these values as
        class properties because we might not have the complete message
        in the buffer and we need to wait until we get more data.
        """
        # Remove the part of the buffer that has already been processed
        headerLen = self.getHeaderLen()
        readLen = headerLen + self.totalLen
        if self.flags == const.FLAG_CONTROL:
            readLen += self.argsParseLen
        self.recvBuf = self.recvBuf[readLen:]

        self.totalLen = self.payloadLen = self.flags = self.opcode = None
        self.argsLen = self.ctrlId = self.argsParseLen = 0
        self.args = self.totalArgs = ""

    def parseMinHeaderFields(self):
        """Extract common header fields, if necessary."""
        if not self.totalLen == self.payloadLen == self.flags == None:
            return

        # Parse common header fields
        self.totalLen = self.getTotalLen()
        self.payloadLen = self.getPayloadLen()
        self.flags = self.getFlags()

        # Sanity check of the fields
        if not isSane(self.totalLen, self.payloadLen, self.flags):
            raise base.PluggableTransportError("Invalid header field.")

    def parseControlFields(self):
        """Extract control message fields."""
        # Parse `opcode`
        if self.opcode == None:
            self.opcode = self.getOpCode()
        # Sanity check of the opcode
        if not isOpCodeSane(self.opcode):
            raise base.PluggableTransportError("Invalid control opcode: %s"
                                               % self.opcode)

        # Parse args length
        self.argsLen = self.getargsLen()

        # If the opcode requires args
        if self.argsLen > 0:
            argsInitLen = const.MPU_CTRL - self.totalLen
            if argsInitLen < self.argsLen:
                self.argsParseLen = const.MPU_CTRL
            else:
                self.argsParseLen = self.getParseLength(self.argsLen,
                                                        const.MPU_CTRL)
            self.args = self.getMessageField(const.ARGS_POS, self.argsParseLen)

    def filterPaddingOut(self):
        """Filter padding messages out and remove data messages from buffer."""
        headerLen = self.getHeaderLen()
        start = headerLen
        if self.flags is const.FLAG_CONTROL:
            start += self.argsParseLen
        return self.getPayload(start)

    def extract(self, data):
        """Extracts WFPad protocol messages.

        The data is then returned as protocol messages. In case of invalid
        header fields an exception is raised.
        """
        self.recvBuf += data
        msgs = []

        # Keep trying to unpack as long as there is at least a header.
        while len(self.recvBuf) >= const.MIN_HDR_LEN:

            # Parse common header fields
            self.parseMinHeaderFields()

            # Parts of the message are still on the wire; waiting.
            if len(self.recvBuf) - const.MIN_HDR_LEN < self.totalLen:
                break

            if self.flags is const.FLAG_CONTROL:
                # Parse control message fields
                self.parseControlFields()

                if len(self.recvBuf) - const.HDR_CTRL_LEN < self.totalLen:
                    break

            # Extract data
            extracted = self.filterPaddingOut()

            # Create WFPadMessage
            msgs.append(WFPadMessage(payload=extracted,
                                     flags=self.flags,
                                     opcode=self.opcode,
                                     args=self.args))

            # Reset extractor attributes
            self.reset()

        return msgs
