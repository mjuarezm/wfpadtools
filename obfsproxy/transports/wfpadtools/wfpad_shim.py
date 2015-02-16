from sets import Set

import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools.util import genutil as gu


log = logging.get_obfslogger()


class WFPadShimObserver(object):
    """Observer class for the SOCKS's shim.

    This class provides methods to signal the start and end of web sessions.
    It observes events from the proxy shim that indicate SOCKS requests from
    FF, and it counts the alive connections to infer the life of a session.
    """

    def __init__(self, instanceWFPadTransport):
        """Instantiates a new `WFPadShimObserver` object."""
        log.debug("[wfpad - shim obs] New instance of the shim observer.")
        self._wfpad = instanceWFPadTransport
        self._sessions = {}
        self._visiting = False
        self._sessId = 0

    def getNumConnections(self, sessId):
        """Return the number of open connections for session `sessId`."""
        if sessId not in self._sessions:
            return 0
        return len(self._sessions[sessId])

    def onConnect(self, connId):
        """Add id of new connection to the set of open connections."""
        if self.getNumConnections(self._sessId) == 0:
            self._sessId += 1
            self.onSessionStarts(connId)
        if self._sessId in self._sessions:
            self._sessions[self._sessId].add(connId)
        else:
            self._sessions[self._sessId] = Set([connId])

    def onDisconnect(self, connId):
        """Remove id of connection to the set of open connections."""
        if self._sessId in self._sessions and \
                connId in self._sessions[self._sessId]:
            self._sessions[self._sessId].remove(connId)
        if self.getNumConnections(self._sessId) == 0:
            self.onSessionEnds(connId)
            if self._sessId in self._sessions:
                del self._sessions[self._sessId]

    def onSessionStarts(self, sessId):
        """Sets wfpad's `_visiting` flag to `True`."""
        log.debug("[wfpad - shim obs] Session %s begins." % self._sessId)
        self._visiting = True
        self._wfpad.onSessionStarts(self._sessId)

    def onSessionEnds(self, sessId):
        """Sets wfpad's `_visiting` flag to `False`."""
        log.debug("[wfpad - shim obs] Session %s ends." % self._sessId)
        self._visiting = False
        self._wfpad.onSessionEnds(self._sessId)

    def getSessId(self):
        """Return a hash of the current session id.

        We concatenate with a timestamp to get a unique session Id.
        In the final countermeasure we can hash the URL to set particular
        padding strategies for individual pages.
        """
        return gu.hash_text(str(self._sessId) + str(gu.timestamp()))
