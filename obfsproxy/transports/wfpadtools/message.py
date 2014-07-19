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
    """Represents a WFPad protocol data unit.

    The basic structure of a WFPad message is:

   <-------------------------------  MTU  ------------------------------->
    2 Bytes  2 Bytes  1 Byte      1 Byte     Variable <--- Up to MPU ---->
  +--------+---------+-------+--------------+--------+----------+---------+
  | Total  | Payload | Flags |    Opcode    |  Args  |  Payload | Padding |
  | length | length  |       | (if CONTROL) |  (opt) |   (opt)  |  (opt)  |
  +--------+---------+-------+--------------+--------+----------+---------+
  <------- Min Header ------>
  <-------------------  Header  --------------------> <------ Body ------>

      - Total length: message body length (payload length + padding length)

      - Payload length: indicates the message payload's length.

      - Flags: three possible flags so far:
          - DATA:     body payload contains Tor SOCKS data + padding
          - PADDING:  body only contains padding
          - CONTROL:  body contains _opcode and arguments for control message
                      and piggybacks data in wfpad buffer that can be either
                      padding or Tor SOCKS data.

      - Opcode (mandatory if Flags=CONTROL): operation code that describes
                                             the wfpad primitive to the
                                             endpoint.

      - Args (optional): arguments for the wfpad primitive described by
                         _opcode. Only specified if Flags=CONTROL but it is
                         not mandatory.

      - Payload (optional): contains Tor SOCKS data.

      - Padding (optional): contains string of null chars (`\0`).


    Note 1: there are two kinds of padding:
        - At message level: padding is appended to the message's payload
        - At link level: the message itself is a padding message
    Note 2: all messages share the first three fields (min header) in the
                         header.
    """
    def __init__(self, payload='', paddingLen=0, flags=const.FLAG_DATA,
                        opcode=None, args=None):
        """Create a new instance of `WFPadMessage`.

        Parameters
        ----------
        payload : str
                  Message's payload which contains Tor data.
        paddingLen : int
                     Length of the padding added at the end of the payload.
        flags : int
                Flag indicating the type of message.
        _opcode : int
                 Code of the operation, in case it is a control message.
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
        self._opcode = opcode
        self.args = args

    def generatePadding(self):
        return (self.totalLen - self.payloadLen) * '\0'

    def __str__(self):
        """Return message as string."""
        opCodeStr = argsStr = ''

        totalLenStr = pack.htons(self.totalLen)
        payloadLenStr = pack.htons(self.payloadLen)
        flagsStr = chr(self.flags)
        paddingStr = self.generatePadding()

        if self._opcode:
            opCodeStr = chr(self._opcode)
        if self.args:
            argsStr = ''.join(map(str, self.args))

        header = totalLenStr + payloadLenStr + flagsStr + opCodeStr + argsStr

        return header + self.payload + paddingStr

    def __len__(self):
        """Return the length of this protocol message."""
        if self.flags is const.FLAG_CONTROL:
            argsLen = const.get_args_len(self._opcode)
            return const.CTRL_HDR_LEN + argsLen + self.totalLen
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
                           flags=const.FLAG_DATA, opcode=None, args=None):
        return WFPadMessage(payload, paddingLen, flags, opcode, args)

    def createWFPadMessages(self, data,
                            flags=const.FLAG_DATA, opcode=None, args=None):
        """Create protocol messages out of the given payload.

        The given `data` is turned into a list of protocol messages with the
        given `flags` set. The list is then returned.
        """
        messages = []
        while len(data) > 0:
            msgLen = self.lenDist.randomSample()
            dataLen = len(data)
            if dataLen > msgLen:
                messages.append(self.createWFPadMessage(data[:msgLen],
                                                        flags=flags,
                                                        opcode=opcode,
                                                        args=args))
                data = data[msgLen:]
            else:
                messages.append(self.createWFPadMessage(data[:dataLen],
                                             paddingLen=(msgLen - dataLen),
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
    """Return the _opcode encoded in the integer `_opcode` as string.

    This function is only useful for printing easy-to-read _opcode names in
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


def isOpCodeSane(opcode, args):
    """Verify the the extra control message fields are correct."""

    log.debug("Control fields: _opcode=%d, args=%d"
              % (opcode, args, getOpcodeNames(opcode)))

    validOpCodes = [
        const.OP_APP_HINT,
        const.OP_BATCH_PAD,
        const.OP_BURST_HISTO,
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
    depending on the flag we continue parsing the _opcode, args and
    payload.
    """
    def __init__(self):
        self.recvBuf = ""
        self.totalLen = None
        self.payloadLen = None
        self.flags = None

        self._opcode = None
        self.args = []
        self.ctrlHeaderLen = 0  #XZXZ Do we need this?

    def getMessageField(self, position, length):
        """Return chunk in the buffer corresponding to a field."""
        return self.recvBuf[position:position + length]

    def reset(self):
        """Reset class properties to their initial value.

        We call this function whenever a new message has been processed
        in order to reset the properties. We must store these values as
        class properties because we might not have the complete message
        in the buffer and we need to wait until we get more data.
        """
        # Remove part of the buffer that has already been processed
        self.recvBuf = self.recvBuf[const.MIN_HDR_LEN + self.totalLen:]

        # Set header fields to `None`
        self.totalLen = self.payloadLen = self.flags = self._opcode = None

        # Set args to empty list
        self.args = []
        self.ctrlHdrLen = 0

    def parseCommonHeaderFields(self):
        """Extract common header fields, if necessary."""
        if not self.totalLen == self.payloadLen == self.flags == None:
            return
        self.totalLen = pack.ntohs(self.getMessageField(
                                        const.TOTLENGTH_POS,
                                        const.TOTLENGTH_LEN))
        self.payloadLen = pack.ntohs(self.getMessageField(
                                        const.PAYLOAD_POS,
                                        const.PAYLOAD_LEN))
        self.flags = ord(self.getMessageField(
                                        const.FLAGS_POS,
                                        const.FLAGS_LEN))
        if not isSane(self.totalLen, self.payloadLen, self.flags):
            raise base.PluggableTransportError("Invalid header field.")

    def parseControlFields(self):
        """Extract control message fields."""
        log.error("Parsing control fields")
        if self._opcode == None:
            return
        log.error("Opcode: %s" % self._opcode)
        self._opcode = ord(self.getMessageField(const.CONTROL_POS,
                                         const.CONTROL_LEN))
        if not isOpCodeSane(self._opcode):
            raise base.PluggableTransportError("Invalid control "
                                               "message _opcode.")
        for arg in const.ARGS_DICT[self._opcode]:
            try:
                parsedArg = arg.type(self.getMessageField(
                                            const.ARGS_POS,
                                            len(arg)))
            except:
                raise base.PluggableTransportError("Invalid control message "
                                                    "argument.")
            self.args.append(parsedArg)
        self.ctrlHdrLen = const.CTRL_HDR_LEN + const.get_args_len(self._opcode)

    def filterPaddingOut(self):
        """Filter padding messages out and remove data messages from buffer."""
        if self.flags == const.FLAG_CONTROL:
            # If it's a control message, extract payload for piggybacking
            extracted = self.recvBuf[self.ctrlHdrLen:
                     (self.totalLen + self.ctrlHdrLen)][:self.payloadLen]
        else:
            extracted = self.recvBuf[const.MIN_HDR_LEN:
                     (self.totalLen + const.MIN_HDR_LEN)][:self.payloadLen]
        return extracted

    def extract(self, data):
        """Extracts WFPad protocol messages.

        The data is then returned as protocol messages. In case of
        invalid header fields an exception is raised.
        """
        self.recvBuf += data
        msgs = []

        log.error("WORKING!!")
        # Keep trying to unpack as long as there is at least a header.
        while len(self.recvBuf) >= const.MIN_HDR_LEN:
            # Parse common header fields
            self.parseCommonHeaderFields()

            # Parts of the message are still on the wire; waiting.
            if len(self.recvBuf) - const.MIN_HDR_LEN < self.totalLen:
                break

            if self.flags is const.FLAG_CONTROL:
                # Parse control message fields
                self.parseControlFields()
                if len(self.recvBuf) - self.ctrlHdrLen < self.totalLen:
                    break

            extracted = self.filterPaddingOut()
            msgs.append(WFPadMessage(payload=extracted,
                                     flags=self.flags,
                                     opcode=self._opcode,
                                     args=self.args))
            self.reset()
        return msgs
