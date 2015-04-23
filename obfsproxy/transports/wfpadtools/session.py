

class Session(object):
    """Contains state and variables for the current session.

    A session is defines as a visit to a web page.
    """
    def __init__(self):
        # Flag padding
        self._is_padding = False

        # Statistics to keep track of past messages
        # Used for debugging
        self._history = []

        # Used for congestion sensitivity
        self._lastSndDownstreamTs = 0
        self._lastSndDataDownstreamTs = 0

        self._lastRcvDownstreamTs = 0
        self._lastRcvDataDownstreamTs = 0

        self._lastRcvUpstreamTs = 0
        self._consecPaddingMsgs = 0
        self._sentDataBytes = 0

        self._dataBytes = {'rcv': 0, 'snd': 0}
        self._totalBytes = {'rcv': 0, 'snd': 0}
        self._numMessages = {'rcv': 0, 'snd': 0}
        self._dataMessages = {'rcv': 0, 'snd': 0}

        # Padding after end of session
        self.totalPadding = 0
        self.calculateTotalPadding = lambda Self: None