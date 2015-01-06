from os.path import join
import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util as ut


class UtilTest(STTest):
    """Test the wfpad.util module."""

    def test_log_watchdog(self):
        testfile = join(const.TEMP_DIR, "testfile")
        testline = "test line"
        ut.write_to_file(testfile, "line1\n" + testline + "\nline3")
        self.should_raise("Watchdog did not raised expected exception.",
                          ut.log_watchdog, "not test line", testfile, 1, 1)
        self.should_not_raise("Watchdog raised unexpected exception.",
                              ut.log_watchdog, testline, testfile, 5, 1)

    def test_closest_multiple_n_lesser_than_k(self):
        n, k = 3, 8
        obs_result = ut.closest_multiple(n, k)
        self.assertEqual(obs_result, k,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))

    def test_closest_multiple_n_multiple_of_k(self):
        n, k = 16, 8
        obs_result = ut.closest_multiple(n, k)
        self.assertEqual(obs_result, n,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))

    def test_closest_multiple_n_greater_than_k(self):
        n, k = 17, 8
        obs_result = ut.closest_multiple(n, k)
        self.assertEqual(obs_result, 3 * k,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))

    def test_closest_multiple_k_equals_1(self):
        n, k = 17, 1
        obs_result = ut.closest_multiple(n, k)
        self.assertEqual(obs_result, n,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))


if __name__ == "__main__":
    unittest.main()
