import unittest

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import histo


class HistogramClassTestCase(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def assert_uniform(self, x):
        NUM_SAMPLES = 100
        u = histo.uniform(x)
        for i in xrange(NUM_SAMPLES):
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
        h = histo.new({0.1: 1,
                       0.2: 5,
                       0.3: 10,
                       0.4: 5,
                       0.5: 1,
                       const.INF_LABEL: 0},
                      interpolate=False)
        self.assert_mean(h, 0.3)

    def test_remove_tokens(self):
        h = histo.new({0.1: 1,
                       0.2: 5,
                       0.3: 10,
                       0.4: 5,
                       0.5: 1,
                       const.INF_LABEL: 0},
                      interpolate=False,
                      removeTokens=True)
        x = h.randomSample()
        h.removeToken(x)
        self.assertEqual(h.hist[x], h.template[x]-1, "%s, %s" % (x, h.hist))

