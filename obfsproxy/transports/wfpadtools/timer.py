from twisted.internet import task

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


class RandomIntervalTimer(object):
    """Implement timer to sync buffer.

    It uses a probability distribution to sample the time interval for the
    loopingCall object.
    """
    def __init__(self, f, time_probdist):
        self._time_probdist = time_probdist
        self._looper = task.LoopingCall(self._run)
        self._callable = f
        self._elapsed_time = 0

    def _run(self):
        t = self._time_probdist.randomSample()
        self._elapsed_time += t
        self._looper.interval = t
        self._callable()

    def elapsed(self):
        return self._elapsed_time

    def stop(self):
        self._looper.stop()

    def start(self):
        self._looper.start(0)
