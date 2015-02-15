import unittest

# WFPadTools imports
from obfsproxy.transports.wfpadtools.util.testutil import STTest
import obfsproxy.transports.wfpadtools.util.mathutil as mu


class MathUtilTest(STTest):
    """Test the wfpad.util module."""

    def test_closest_multiple_n_lesser_than_k(self):
        n, k = 3, 8
        obs_result = mu.closest_multiple(n, k)
        self.assertEqual(obs_result, k,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))

    def test_closest_multiple_n_multiple_of_k(self):
        n, k = 16, 8
        obs_result = mu.closest_multiple(n, k)
        self.assertEqual(obs_result, n,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))

    def test_closest_multiple_n_greater_than_k(self):
        n, k = 17, 8
        obs_result = mu.closest_multiple(n, k)
        self.assertEqual(obs_result, 3 * k,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))

    def test_closest_multiple_k_equals_1(self):
        n, k = 17, 1
        obs_result = mu.closest_multiple(n, k)
        self.assertEqual(obs_result, n,
                         "The closest multiple of {1} to {0} is not {2}"
                         .format(n, k, obs_result))


if __name__ == "__main__":
    unittest.main()
