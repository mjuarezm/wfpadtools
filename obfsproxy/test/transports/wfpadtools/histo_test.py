import unittest

from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import histo

TEST_DICTIONARY = {0.1: 1,
                   0.2: 5,
                   0.3: 10,
                   0.4: 5,
                   0.5: 1,
                   const.INF_LABEL: 0}

TEST_DICT_INF = {0.1: 1,
                 0.2: 5,
                 0.3: 10,
                 0.4: 5,
                 0.5: 1,
                 const.INF_LABEL: 10}


class HistogramClassTestCase(unittest.TestCase):

    def assert_uniform(self, x):
        NUM_SAMPLES = 100
        u = histo.uniform(x)
        for _ in xrange(NUM_SAMPLES):
            s = u.randomSample()
            self.assertEquals(s, x)

    def assert_mean(self, hist, m):
        NUM_SAMPLES = 1000
        samples = [hist.randomSample() for _ in xrange(NUM_SAMPLES)]
        mean = sum(samples) / len(samples)
        self.assertAlmostEqual(mean, m, 1)

    def test_uniform_distribution(self):
        self.assert_uniform(0)
        self.assert_uniform(1)
        self.assert_uniform(4)
        self.assert_uniform(100.0213)
        self.assert_uniform(const.INF_LABEL)

    def test_mean_of_histogram(self):
        h = histo.new(TEST_DICTIONARY, interpolate=False)
        self.assert_mean(h, 0.3)

    def test_remove_tokens_without_interpolation(self):
        h = histo.new(TEST_DICTIONARY, interpolate=False, removeTokens=True)
        x = h.randomSample()
        h.removeToken(x)
        self.assertEqual(h.hist[x], h.template[x] - 1)

    def test_remove_tokens_with_interpolation(self):
        h = histo.new(TEST_DICTIONARY, removeTokens=True)
        x = h.randomSample()
        h.removeToken(x)
        label = h.getLabelFromFloat(x)
        self.assertEqual(h.hist[label], h.template[label] - 1)
    
    def test_remove_tokens_with_gaps(self):
        h = histo.new(TEST_DICTIONARY, removeTokens=True)
        h.removeToken(0.5)
        h.removeToken(0.5)
        self.assertEqual(h.hist[0.4], h.template[0.4] -1)
    
    def test_remove_tokens_with_only_positive_on_right(self):
        h = histo.new(TEST_DICTIONARY, removeTokens=True)
        h.removeToken(0.1)
        h.removeToken(0.1)
        self.assertEqual(h.hist[0.2], h.template[0.2] - 1)


    def test_remove_tokens_with_interpolation_with_inf_label(self):
        h = histo.new(TEST_DICT_INF, removeTokens=True)
        h.removeToken(const.INF_LABEL)
        self.assertEqual(h.hist[const.INF_LABEL],
                         h.template[const.INF_LABEL] - 1)
    
    def test_remove_tokens_with_gaps_with_inf_label(self):
        h = histo.new(TEST_DICT_INF, removeTokens=True)
        h.removeToken(0.5)
        h.removeToken(0.5)
        self.assertEqual(h.hist[0.4], h.template[0.4] -1)
    
    def test_remove_tokens_with_only_positive_on_right_with_inf_label(self):
        h = histo.new(TEST_DICT_INF, removeTokens=True)
        h.removeToken(0.1)
        h.removeToken(0.1)
        self.assertEqual(h.hist[0.2], h.template[0.2] - 1)


    def test_refill_histo(self):
        h = histo.new({1: 1})
        h.removeToken(1)
        self.assertEqual(h.hist[1], 1)
