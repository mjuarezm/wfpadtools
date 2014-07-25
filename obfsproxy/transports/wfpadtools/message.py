"""This module provides methods to handle WFPad protocol messages.

The exported classes and functions provide interfaces to handle protocol
messages, check message headers for validity and create protocol messages out
of application data.

This module is basically the same as ScrambleSuit's message but modified to
our protocol specification.
"""
import random
import json

import obfsproxy.transports.base as base
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.wfpadtools import const

import obfsproxy.common.log as logging
import obfsproxy.common.serialize as pack


log = logging.get_obfslogger()


class WFPadMessage(object):
    """Represents a WFPad protocol data unit.

    The basic structure of a WFPad message is:

   <--------------------------------------  MTU  ------------------------------------->
    2 Bytes  2 Bytes  1 Byte      1 Byte        2 Bytes   Variable <--- Up to MPU ---->
  +--------+---------+-------+--------------+-------------+-------+----------+---------+
  | Total  | Payload | Flags |    Opcode    | Args length | Args  |  Payload | Padding |
  | length | length  |       | (if CONTROL) |    (opt)    | (opt) |   (opt)  |  (opt)  |
  +--------+---------+-------+--------------+-------------+-------+----------+---------+
  <------- Min Header ------>
  <-------------------  Header  -------------------------> <---------- Body ---------->

      - Total length: message body length (payload length + padding length)

      - Payload length: indicates the message payload's length.

      - Flags: three possible flags so far:
          - DATA:     body payload contains Tor SOCKS data + padding
          - PADDING:  body only contains padding
          - CONTROL:  body contains opcode and arguments for control message
                      and piggybacks data in wfpad buffer that can be either
                      padding or Tor SOCKS data.

      - Opcode (mandatory if Flags=CONTROL): operation code that describes
                                             the wfpad primitive to the
                                             endpoint.

      - Args length (optional): length of the `Args` field. This is required
                                for the message extractor to parse the args.
                                It is optional, but must be specified if the
                                `Args` field is not empty.
      - Args (optional): arguments for the wfpad primitive described by
                         opcode. Only specified if Flags=CONTROL but it is
                         not mandatory. Before each arg, we specify the length
                         of it necessary for the parsing.

      - Payload (optional): contains Tor SOCKS data.

      - Padding (optional): contains string of null chars (`\0`).


    Note 1: there are two kinds of padding:
        - At message level: padding is appended to the message's payload
        - At link level: the message itself is a padding message
    Note 2: all messages share the first three fields (min header) in the
                         header.
    """
    def __init__(self, payload='', paddingLen=0, flags=const.FLAG_DATA,
                        opcode=None, argsLen=0, args=""):
        """Create a new instance of `WFPadMessage`.

        Parameters
        ----------
        payload : str
                  Message's payload which contains Tor data.
        paddingLen : int
                     Length of the padding added at the end of the payload.
        flags : int
                Flag indicating the type of message.
        opcode : int
                 Code of the operation, in case it is a control message.
        argsTotalLen : int
                  length of of all the arguments.
        args : list
               list that contains the arguments for the operations, in case
               it is a control message.
        """
        payloadLen = len(payload)

        if (payloadLen + paddingLen) > const.MPU:
            raise base.PluggableTransportError("No overly long messages.")

        self.totalLen = payloadLen + paddingLen
        self.payloadLen = payloadLen
        self.payload = payload
        self.flags = flags
        self.opcode = opcode
        self.args = args
        self.argsTotalLen = argsLen
        self.argsLen = 0 if not args else len(self.args)

    def generatePadding(self):
        return (self.totalLen - self.payloadLen) * '\0'

    def __str__(self):
        """Return message as string."""
        opCodeStr = argsLen = ""

        totalLenStr = pack.htons(self.totalLen)
        payloadLenStr = pack.htons(self.payloadLen)
        flagsStr = chr(self.flags)
        paddingStr = self.generatePadding()

        header = totalLenStr + payloadLenStr + flagsStr
        if self.opcode:  # it's a control message
            opCodeStr = chr(self.opcode)
            header += opCodeStr
            if self.args:
                argsLen = pack.htons(self.argsTotalLen)
                header += argsLen + self.args

        return header + self.payload + paddingStr

    def __len__(self):
        """Return the length of this protocol message."""
        if self.flags is const.FLAG_CONTROL:
            return const.CTRL_HDR_LEN + self.argsLen + self.totalLen
        else:
            return const.MIN_HDR_LEN + self.totalLen


class WFPadMessageFactory(object):
    """Creates WFPad's protocol messages."""

    def __init__(self, len_dist=None):
        """Initialize the WFPadMessageFactory with the distribution `lenDist`.

        If `lenDist` is `None`, a new discrete probability distribution is
        generated randomly.
        """
        if len_dist:
            self.lenDist = len_dist
        else:
            self.lenDist = probdist.new(lambda: random.randint(
                                                const.MIN_HDR_LEN,
                                                const.MTU),
                                         lambda i, n, c: 1)

    def setLenDistribution(self, newLenDist):
        """Set a new length probability distribution."""
        self.lenDist = newLenDist

    def createWFPadMessage(self, payload="", paddingLen=0,
                           flags=const.FLAG_DATA, opcode=None,
                           argsLen=0, args=None):
        return WFPadMessage(payload, paddingLen, flags, opcode,
                            argsLen, args)

    def createWFPadControlMessages(self, opcode, args=None):
        if not args:
            return [self.createWFPadMessage(flags=const.FLAG_CONTROL,
                                            opcode=opcode)]
        messages = []
        strArgs = json.dumps(args)
        while len(strArgs) > 0:
            argsLen = len(strArgs)
            payloadLen = const.MPU_CTRL
            # TODO: implement piggybacking
            messages.append(self.createWFPadMessage(flags=const.FLAG_CONTROL,
                                                    opcode=opcode,
                                                    argsLen=argsLen,
                                                    args=strArgs[:payloadLen]))
            strArgs = strArgs[payloadLen:]
        return messages

    def createWFPadMessages(self, data,
                            flags=const.FLAG_DATA, opcode=None, args=None):
        """Create protocol messages out of the given payload.

        The given `data` is turned into a list of protocol messages with the
        given `flags` set. The list is then returned.
        """
        messages = []
        while len(data) > 0:
            payloadLen = const.MPU
            dataLen = len(data)
            if dataLen > payloadLen:
                messages.append(self.createWFPadMessage(data[:payloadLen],
                                                        flags=flags,
                                                        opcode=opcode,
                                                        args=args))
                data = data[payloadLen:]
            else:
                messages.append(self.createWFPadMessage(data[:dataLen],
                                             paddingLen=(payloadLen - dataLen),
                                             flags=flags,
                                             opcode=opcode,
                                             args=args))
                data = data[dataLen:]
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
    elif flags == const.FLAG_CONTROL:
        return "CONTROL"
    else:
        return "Undefined"


def getOpcodeNames(opcode):
    """Return the opcode encoded in the integer `opcode` as string.

    This function is only useful for printing easy-to-read opcode names in
    debug log messages.
    """
    if opcode == const.OP_START:
        return "START PADDING"
    elif opcode == const.OP_STOP:
        return "STOP PADDING"
    elif opcode == const.OP_IGNORE:
        return "ONE PADDING MESSAGE REQUEST"
    elif opcode == const.OP_SEND_PADDING:
        return "PADDING REQUEST"
    elif opcode == const.OP_APP_HINT:
        return "APPLICATION HINT"
    elif opcode == const.OP_BURST_HISTO:
        return "BURST HISTOGRAM"
    elif opcode == const.OP_INJECT_HISTO:
        return "INJECT HISTOGRAM"
    elif opcode == const.OP_TOTAL_PAD:
        return "TOTAL PADDING"
    elif opcode == const.OP_PAYLOAD_PAD:
        return "PAYLOAD PADDING"
    elif opcode == const.OP_BATCH_PAD:
        return "BATCH PADDING"
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

    log.debug("Message header: totalLen=%d, payloadLen=%d, flags"
              "=%s" % (totalLen, payloadLen, getFlagNames(flags)))

    validFlags = [
        const.FLAG_DATA,
        const.FLAG_PADDING,
        const.FLAG_CONTROL
    ]

    return isFine(totalLen) and \
           isFine(payloadLen) and \
           totalLen >= payloadLen and \
           (flags in validFlags)


def isOpCodeSane(opcode):
    """Verify the the extra control message fields are correct."""

    log.debug("Opcode: value=%s, name=%s"
              % (opcode, getOpcodeNames(opcode)))

    validOpCodes = [
        const.OP_APP_HINT,
        const.OP_BATCH_PAD,
        const.OP_BURST_HISTO,
        const.OP_GAP_HISTO,
        const.OP_IGNORE,
        const.OP_INJECT_HISTO,
        const.OP_PAYLOAD_PAD,
        const.OP_SEND_PADDING,
        const.OP_START,
        const.OP_STOP,
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
        # Buffer data in stream
        self.recvBuf    = ""

        # Fields of WFPad message
        self.totalLen       = None
        self.payloadLen     = None
        self.flags          = None
        self.opcode         = None
        self.argsTotalLen   = 0
        self.ctrlHdrLen     = 0
        self.argsParseLen   = 0
        self.args           = ""

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

    def getArgsLen(self):
        """Return `argsTotalLen` field from buffer."""
        return pack.ntohs(self.getMessageField(const.ARGSLENGTH_POS,
                                               const.ARGSLENGTH_LEN))

    def getPayload(self, start):
        """Return `payload` from buffer."""
        totalPayload = self.getMessageField(start, self.totalLen)
        return totalPayload[:self.payloadLen]  # Strip padding

    def reset(self):
        """Reset class properties to their initial value.

        We call this function whenever a new message has been processed
        in order to reset its properties. We must store these values as
        class properties because we might not have the complete message
        in the buffer and we need to wait until we get more data.
        """
        # Remove part of the buffer that has already been processed
        if self.flags is const.FLAG_CONTROL:
            self.recvBuf = self.recvBuf[const.CTRL_HDR_LEN + self.argsParseLen + self.totalLen:]
        else:
            self.recvBuf = self.recvBuf[const.MIN_HDR_LEN + self.totalLen:]

        # Set header fields to `None`
        self.totalLen = self.payloadLen = self.flags = self.opcode = None

        # Set `args` to empty list
        self.args = ""
        self.argsTotalLen = 0
        self.ctrlHdrLen = 0
        self.argsParseLen = 0

    def parseCommonHeaderFields(self):
        """Extract common header fields, if necessary."""
        # Return if some of the fields has been already parsed
        if not self.totalLen == self.payloadLen == self.flags == None:
            return

        # Parse common header fields
        self.totalLen   = self.getTotalLen()
        self.payloadLen = self.getPayloadLen()
        self.flags      = self.getFlags()

        # Sanity check of the fields
        if not isSane(self.totalLen, self.payloadLen, self.flags):
            raise base.PluggableTransportError("Invalid header field.")

    def parseControlFields(self):
        """Extract control message fields."""
        # Parse `opcode`
        if self.opcode == None:
            self.opcode = self.getOpCode()

        print "XX", self.opcode

        # Sanity check of the opcode
        if not isOpCodeSane(self.opcode):
            raise base.PluggableTransportError("Invalid control "
                                               "message opcode.")

        self.ctrlHdrLen = const.CTRL_HDR_LEN

        # If the opcode requires args
        if const.ARGS_DICT[self.opcode][0] > 0:
            self.argsTotalLen = self.getArgsLen()

            self.argsParseLen = const.MPU_CTRL \
                                    if self.argsTotalLen > const.MPU_CTRL\
                                    else self.argsTotalLen
            self.args = self.getMessageField(const.ARGS_POS, self.argsParseLen)
            self.ctrlHdrLen += self.argsTotalLen

    def filterPaddingOut(self):
        """Filter padding messages out and remove data messages from buffer."""
        # If it's a control message, extract payload for piggybacking
        start = self.ctrlHdrLen if self.flags is const.FLAG_CONTROL \
                else const.MIN_HDR_LEN
        extracted = self.getPayload(start)
        return extracted

    def extract(self, data):
        """Extracts WFPad protocol messages.

        The data is then returned as protocol messages. In case of
        invalid header fields an exception is raised.
        """
        self.recvBuf += data
        msgs = []

        # Keep trying to unpack as long as there is at least a header.
        while len(self.recvBuf) >= const.MIN_HDR_LEN:

            # Parse common header fields
            self.parseCommonHeaderFields()

            # Parts of the message are still on the wire; waiting.
            if len(self.recvBuf) - const.MIN_HDR_LEN < self.totalLen:
                break
            print "XXX EXTRACT", self.flags

            if self.flags is const.FLAG_CONTROL:
                print "XXX HI"
                # Parse control message fields
                self.parseControlFields()

                print "XXX EXTRACT", self.opcode
                print "XXX DATA:",  self.totalLen, self.argsParseLen, self.flags, self.opcode, self.args, self.argsTotalLen
                print "XXX BREAK", const.CTRL_HDR_LEN, len(self.recvBuf), self.ctrlHdrLen, self.totalLen
                if len(self.recvBuf) - self.ctrlHdrLen < self.totalLen:
                    break

            # Extract data
            extracted = self.filterPaddingOut()

            # Create WFPadMessage
            msgs.append(WFPadMessage(payload=extracted,
                                     flags=self.flags,
                                     opcode=self.opcode,
                                     argsLen=self.argsTotalLen,
                                     args=self.args))

            print "XXX OK", msgs, self.flags, self.opcode, self.argsTotalLen, self.args
            # Reset extractor attributes
            self.reset()
        print "XXXXXX", msgs
        return msgs
