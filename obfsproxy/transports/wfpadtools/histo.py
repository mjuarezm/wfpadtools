"""
The class Histogram provides an interface to generate and sample probability
distributions represented as histograms.
"""
from bisect import bisect_right
import operator
from random import randint
import random

import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools.const import INF_LABEL
import obfsproxy.transports.wfpadtools.const as ct


log = logging.get_obfslogger()


class Histogram:
    """Provides methods to generate and sample histograms of prob distributions."""

    def __init__(self, hist, interpolate=True, removeTokens=False, decay_by=0, name=''):
        """Initialize an histogram.

        `hist` is a dictionary. The keys are labels of an histogram. They represent
        the value of the rightmost endpoint of the right-open interval of the bin. The
        dictionary value corresponding to that key is a count of tokens representing
        the frequency in the histogram.

        For example, the histogram:
         5-                                                     __
         4-                  __                                |  |
         3-        __       |  |                __             |  |
         2-       |  |      |  |               |  |            |  |
         1-       |  |      |  |               |  |            |  |
                [0, x_0) [x_0, x_1), ..., [x_(n-1), x_n), [x_n, infinite)

        Would be represented with the following dictionary:

            h = {'x_0': 3, 'x_1': 4, ..., 'x_n': 3, INF_LABEL: 5}

        `interpolate` indicates whether the value is sampled uniformly
        from the interval defined by the bin (e.g., U([x_0, x_1)) or the value
        of the label is returned. In case of a discrete histogram we would have:

         5-                                                     __
         4-                  __                                |  |
         3-        __       |  |                __             |  |
         2-       |  |      |  |               |  |            |  |
         1-       |  |      |  |               |  |            |  |
                  x_0       x_1      ...       x_n           infinite

        `removeToks` indicates that every time a sample is drawn from the histrogram,
        we remove one token from the count (the values in the dictionary). We keep a
        copy of the initial value of the histogram to re assign it when the histogram
        runs out of tokens.

        We assume all values in the dictionary are positive integers and
        that there is at least a non-zero value. For efficiency, we assume the labels
        are floats that have been truncated up to some number of decimals. Normally, the
        labels will be seconds and since we want a precision of milliseconds, the float
        is truncated up to the 3rd decimal position with for example round(x_i, 3).
        """
        self.name = name
        self.hist = hist
        self.inf = False
        self.interpolate = interpolate
        self.removeTokens = removeTokens

        if Histogram.isEmpty(hist):
            self.interpolate = False
            self.removeTokens = False

        # create template histogram
        self.template = dict(hist)

        # store labels in a list for fast search over keys
        self.labels = sorted(self.hist.keys())
        self.n = len(self.labels)

        # decay_by is the number of tokens we add to the infinity bin after
        # each successive padding packet is sent.
        self.decay_by = decay_by

        # dump initial histogram
        self.dumpHistogram()

    def getLabelFromFloat(self, f):
        """Return the label for the interval to which `f` belongs."""
        if f in self.labels:
            return f
        return self.labels[bisect_right(self.labels, f)]

    def removeToken(self, f, padding=True):
        # TODO: move the if below to the calls to the function `removeToken`
        if self.removeTokens:

            if padding:
                if ct.INF_LABEL in self.hist:
                    self.hist[ct.INF_LABEL] += self.decay_by
                if ct.INF_LABEL in self.template:
                    self.template[ct.INF_LABEL] += self.decay_by

            label = self.getLabelFromFloat(f)
            pos_counts = [l for l in self.labels if self.hist[l] > 0]

            # else remove tokens from label or the next non-empty label on the left
            # if there is none, continue removing tokens on the right.
            if label not in pos_counts:
                if label < pos_counts[0]:
                    label = pos_counts[0]
                else:
                    label = pos_counts[bisect_right(pos_counts, label) - 1]
            self.hist[label] -= 1
            #log.debug("[histo] Remove token! Tokens: %s" % sum(self.hist.values()))
            
            # if histogram is empty, refill the histogram
            if sum(self.hist.values()) == 0:
                self.refillHistogram()

    def mean(self):
        return sum([k * v for k, v in self.hist.iteritems() if k != INF_LABEL]) / sum(self.hist.values())

    def variance(self):
        m = self.mean()
        n = sum(self.hist.values())
        if n < 2:
            raise ValueError("The sample is not big enough for an unbiased variance.")
        return sum([k * ((v - m) ** 2) for k, v in self.hist.iteritems() if k != INF_LABEL]) / (n - 1)

    def dumpHistogram(self):
        """Print the values for the histogram."""
        log.debug("Dumping histogram: %s" % self.name)
        if sum(self.hist.values()) > 3:
            log.debug("Mean: %s" % self.mean())
            log.debug("Variance: %s" % self.variance())
        if self.interpolate:
            log.debug("[0, %s), %s", self.labels[0], self.hist[self.labels[0]])
            for labeli, labeli1 in zip(self.labels[0:-1], self.labels[1:]):
                log.debug("[%s, %s), %s", labeli, labeli1, self.hist[labeli1])
        else:
            for label, count in self.hist.iteritems():
                log.debug("(%s, %s)", label, count)

    def refillHistogram(self):
        """Copy the template histo."""
        self.hist = dict(self.template)
        log.debug("[histo] Refilled histogram: %s" % (self.hist))

    def randomSample(self):
        """Draw and return a sample from the histogram."""
        total_tokens = sum(self.hist.values())
        prob = randint(1, total_tokens) if total_tokens > 0 else 0
        for i, label_i in enumerate(self.labels):
            prob -= self.hist[label_i]
            if prob > 0:
                continue
            if not self.interpolate or i == self.n - 1:
                return label_i
            label_i_1 = 0 if i == 0 else self.labels[i - 1]
            if label_i == ct.INF_LABEL:
                return ct.INF_LABEL
            p = label_i + (label_i_1 - label_i) * random.random()
            return p
        log.exception("[histo - sample] Tokens = %s, prob = %s", sum(self.hist.values()), prob)
        raise ValueError("In `histo.randomSample`: probability is larger than range of counts!")

    @classmethod
    def get_intervals_from_endpoints(self, ep_list):
        """Return list of intervals built from a list of endpoints."""
        return [[i, j] for i, j in zip(ep_list[:-1], ep_list[1:])]

    @classmethod
    def isEmpty(self, d):
        return len(d.keys()) == 1 and INF_LABEL in d.keys()

    @classmethod
    def divideHistogram(self, histogram, divide_by=None):
        if divide_by == None:
            return histogram, histogram
        if divide_by == 'mode':
            divide_by = max(histogram.iteritems(), key=operator.itemgetter(1))[0]
        high_bins = {k: v for k, v in histogram.iteritems()  if k >= divide_by}
        low_bins = {k: v for k, v in histogram.iteritems() if k <= divide_by}
        low_bins.update({ct.INF_LABEL: 0})
        high_bins.update({divide_by: 0})
        return low_bins, high_bins

    @classmethod
    def skewHistoOneBin(self, d, side='left'):
        keys = sorted([k for k in d])
        if side == "left":
            pass
        elif side == "right":
            keys = keys[::-1]
        else:
            raise ValueError("No side %s." % side)
        assert(len(keys) > 2)
        for left_ep, left_ep_1 in zip(keys[:-1], keys[1:]):
            d[left_ep] = d[left_ep_1]
        d[keys[-1]] = 0
        return d

    @classmethod
    def skewHisto(self, d, nbins, side="left"):
        """Shift histo nbins to left/right."""
        if nbins == 0:
            return d
        for _ in xrange(nbins):
            d = Histogram.skewHistoOneBin(d, side)
        return d

    @classmethod
    def getDictHistoFromList(self, l):
        import numpy as np
        counts, bins = np.histogram(l, bins=self.create_exponential_bins(a=0, b=10, n=20))
        d = dict(zip(list(bins) + [INF_LABEL], [0] + list(counts) + [0]))
        d[0] = 0  # remove 0 iner-arrival times
        return d

    @classmethod
    def dictFromList(self, l, num_samples=1000):
        import numpy as np
        counts, bins = np.histogram(random.sample(l, num_samples),
                                    bins=self.create_exponential_bins(a=0, b=10, n=20))
        d = dict(zip(list(bins) + [INF_LABEL], [0] + list(counts) + [0]))
        d[0] = 0  # remove 0 iner-arrival times
        return d

    @classmethod
    def dictFromDistr(self, name, params, scale=1.0, num_samples=10000):
        import numpy as np
        counts, bins = [], []

        if name == "weibull":
            shape = params
            counts, bins = np.histogram(np.random.weibull(shape, num_samples) * scale,
                                        bins=self.create_exponential_bins(a=0, b=10, n=100))

        elif name == "beta":
            a, b = params
            counts, bins = np.histogram(np.random.beta(a, b, num_samples) * scale,
                                        bins=self.create_exponential_bins(a=0, b=10, n=100))

        elif name == "logis":
            location, scale = params
            counts, bins = np.histogram(np.random.logistic(location, scale, num_samples),
                                        bins=self.create_exponential_bins(a=0, b=10, n=100))

        elif name == "lnorm":
            mu, sigma = params
            counts, bins = np.histogram(np.random.lognormal(mu, sigma, num_samples),
                                        bins=self.create_exponential_bins(a=0, b=10, n=100))

        elif name == "norm":
            mu, sigma = params
            counts, bins = np.histogram(np.random.normal(mu, sigma, num_samples),
                                        bins=self.create_exponential_bins(a=0, b=10, n=100))

        elif name == "gamma":
            shape, scale = params
            counts, bins = np.histogram(np.random.gamma(shape, scale, num_samples),
                                        bins=self.create_exponential_bins(a=0, b=10, n=100))

        elif name == "empty":
            return ct.NO_SEND_HISTO

        else:
            raise ValueError("Unknown probability distribution.")

        d = dict(zip(list(bins) + [INF_LABEL], [0] + list(counts) + [0]))
        d[0] = 0  # remove 0 iner-arrival times
        return d

    @classmethod
    def create_exponential_bins(self, sample=None, min_bin=None,
                                a=None, b=None, n=None):
        """Return a partition of the interval [a, b] with n number of bins.

        Alternatively, it can take a sample of the data and extract the interval
        endpoints by taking the minimum and the maximum.
        """
        if sample:
            a = min(sample)
            b = max(sample)
            if not min_bin:
                n = 20  # TODO: what is the best number of bins?
            n = int(b - a / min_bin)
        return ([b] + [(b - a) / 2.0 ** k for k in xrange(1, n)] + [a])[::-1]

    @classmethod
    def drop_first_n_bins(self, h, n):
        for k in sorted(h.keys())[:n]:
            del h[k]
        return h


def uniform(x):
    return new({x: 1}, interpolate=False, removeTokens=False)


# Alias class name in order to provide a more intuitive API.
new = Histogram

