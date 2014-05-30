import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest
import obfsproxy.transports.wfpadtools.padutils as pu
from obfsproxy.transports.scramblesuit import probdist


class PeriodicTimerTest(STTest):

    def test_elapsed_time(self):
        interval = 1
        expected_elapsed = interval
        t = pu.PeriodicTimer(probdist.new(lambda: interval))
        t.start()
        with t.tick:
            t.tick.wait()
        self.assertAlmostEqual(expected_elapsed, t.elapsed(), places=2,
                               msg="Elapsed time (%s) does not match with"
                               "expected elapsed time (%s)."
                               % (t.elapsed(), expected_elapsed))

    def test_periodicity(self):
        interval = 1
        test_periods = 3
        periods = 0
        t = pu.PeriodicTimer(probdist.new(lambda: interval))
        t.start()
        while True:
            with t.tick:
                t.tick.wait()
                periods += 1
                if periods == test_periods:
                    break
        expected_elapsed = interval * test_periods
        self.assertAlmostEqual(expected_elapsed, t.elapsed(), places=2,
                               msg="Elapsed time (%s) does not match with"
                               "expected elapsed time (%s)."
                               % (t.elapsed(), expected_elapsed))


class PadUtilsTest(STTest):

    def test_BuFLO(self):
        buflo = pu.BuFLO(1, 2, 10)
        buflo.start()


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
