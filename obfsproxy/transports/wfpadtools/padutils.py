"""
Provides classes and methods to implement the padding of the link.
"""
import threading
import time

import obfsproxy.common.log as logging
from obfsproxy.transports.scramblesuit import probdist
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util as ut


log = logging.get_obfslogger()


class PeriodicTimer:
    """Implement timer to sync buffer.

    Modified from O'Reilly's Python Cookbook by David Beazley & Brian K. Jones
    chimera.labs.oreilly.com/books/1230000000393/ch12.html#_discussion_198
    It ticks following a given probability distribution for the intervals.
    """
    def __init__(self, time_probdist):
        """Initialize a new timer for the given probability distribution."""
        self._time_probdist = time_probdist
        self.__delta = 0
        self.__running = True
        self.tick = threading.Condition()

    def __run(self):
        """Run the timer and notify waiting threads after each interval."""
        while self.__running:
            t_sleep = self._time_probdist.randomSample()
            time.sleep(t_sleep)
            self.__delta += t_sleep
            with self.tick:
                self.tick.notify_all()

    def start(self):
        """Start the timer in a thread."""
        t = threading.Thread(target=self.__run)
        t.daemon = True
        self.__delta = 0
        self.__running = True
        t.start()

    def stop(self):
        """Stop the timer."""
        self.__running = False

    def elapsed(self):
        """Return the elapsed time."""
        return self.__delta


class BasePadder(object):
    """Implement the most general link-padding scheme.

    The basic padding scheme is composed by a buffer and a timer. The timer
    divides the time in intervals where data must be sent. We need to buffer
    the received data during timer sleeps.
    """
    def __init__(self, time_probdist, size_probdist):
        """Initialize the padder module.

        Instantiate the FIFO buffer from ScrambleSuit and the timer. We use
        the Scramblesuit's `probdist` module to model the probability
        distributions of both time sleeps and packet lengths.
        """
        self._buf = Buffer()
        self._state = const.ST_WAIT_FOR_VISIT
        self._time_probdist = time_probdist
        self._size_probdist = size_probdist
        self._timer = PeriodicTimer(time_probdist)

    def start(self):
        """Start timer in a new thread.

        This thread is the observer of the observer pattern. It waits for
        the notification from the subject, which is the timer. When we start
        the timer, we change the state to `ST_PADDING`.
        """
        self._timer.start()
        self.__thread = threading.Thread(target=self.pad_link)
        self.__thread.daemon = True
        self._state = const.ST_PADDING
        self.__thread.start()

    def stop(self):
        """Stop timer.

        When we stop the timer we change the state to `WAIT_FOR_VISIT`.
        """
        self._state = const.ST_WAIT_FOR_VISIT
        self._timer.stop()

    def push_to_buffer(self, data):
        """Push data to buffer."""
        self._buf.write(data)

    def stop_condition(self):
        """Return the evaluation of the stop condition.

        We assume that the most general scheme is to be continuously padding.
        More sophisticated defenses try to reduce the overhead and set a
        stopping condition.
        """
        return False

    def generate_padding(self):
        """Return padding data.

        The length of the padding is sampled from the packet length probability
        distribution `size_probdist`, passed as a parameter in the init.
        """
        return ut.rand_str(self._size_probdist.randomSample())

    def pad_link(self):
        """Return data to be sent to the remote end.

        In case the buffer is not empty, the buffer is flushed and we send this
        data over the wire. Otherwise, we generate random padding and we send
        it over the wire. We evaluate the stop condition and wait
        """
        while not self.stop_condition():
            with self._timer.tick:
                if len(self._buf) > 0:
                    print("Flush buffer")
                    self._buf.read(self._size_probdist.randomSample())
                else:
                    print("Generate padding")
                    self.generate_padding()
                self._timer.tick.wait()
        self.stop()


class BuFLO(BasePadder):
    """Implementation of the BuFLO countermeasure.

    It extends the BasePadder by choosing a constant probability distribution
    for time, and a constant probability distribution for packet lengths. The
    minimum time for which the link will be padded is also specified.
    """
    def __init__(self, period, psize, mintime):
        """Initialize the BuFLO padding scheme.

        BuFLO pads at a constant rate `period` and pads the packets to a
        constant size `psize`.
        """
        self._mintime = mintime
        super(BuFLO, self).__init__(time_probdist=probdist.new(lambda: period),
                                    size_probdist=probdist.new(lambda: psize))

    def stop_condition(self):
        """Returns evaluation of passing stop padding.

        BuFLO stops padding if the visit has finished and the elapsed time has
        exceeded the minimum padding time.
        """
        return self._timer.elapsed() > self._mintime \
            and self._state is const.ST_PADDING
