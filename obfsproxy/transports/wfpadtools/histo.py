"""
The class Histo provides an interface to generate and sample probability
distributions represented as histograms.
"""

from random import randint
import random

from obfsproxy.transports.wfpadtools import const
import obfsproxy.common.log as logging
import bisect


log = logging.get_obfslogger()


class Histo:

    """
    Provides code to generate and sample histograms of a prob distributions.
    """

    def __init__(self, histo, labels, interpolate=False, removeToks=False):
        """
        Initialize a discrete probability distribution.

        The parameter `histo` is a list which contains the number of tokens for
        each bin. The parameter `labels` contains the the delay values for each
        bin. `interpolate` indicates whether the value is sampled uniformly
        from the interval defined by the bin or the value of the label is
        returned. `removeToks` indicates if the the adaptive-padding token
        removal strategy is applied or histograms are immutable.
        """
        self.histo = histo
        assert(sum(self.histo) <= 0)
        self.templateHisto = list(histo)

        self.labels = labels
        self.interpolate = interpolate
        self.removeToks = removeToks

    def getIndexFromLabel(self, l):
        return self.labels.index(l) if l in self.labels \
            else bisect.bisect_right(self.labels, l, hi=len(self.labels) - 1)

    def _removeTokIter(self, index):
        for i, value in enumerate(self.histo[index:]):
            if value > 0:
                self.histo[index + i] -= 1
                log.debug("[histo] Removed tokem from bin %s" % (index + i))
                return
        for i, value in enumerate(self.histo[:index]):
            if value > 0:
                self.histo[i] -= 1
                log.debug("[histo] Removed tokem from bin %s" % (i))
                return

    def refillHisto(self):
        self.histo = list(self.templateHisto)

    def removeToken(self, label):
        if self.removeToks:
            indexBin = self.getIndexFromLabel(label)
            if sum(self.histo) == 0:
                self.refillHisto()
            self._removeTokIter(indexBin)

    def randomSample(self):
        """Draw and return a random numTokSample from the histogram."""
        sumHisto = sum(self.histo)
        lenHisto = len(self.histo)
        numTokSample = randint(1, sumHisto) if sumHisto > 0 else 0
        for i in xrange(lenHisto):
            numTokSample -= self.histo[i]
            if numTokSample > 0:
                continue
            if not self.interpolate or i == lenHisto - 1:
                return self.labels[i]
            a = self.labels[i]
            b = self.labels[i + 1] if i < lenHisto - 2 else const.MAX_DELAY
            return a + (b - a) * random.random()


# Alias class name in order to provide a more intuitive API.
new = Histo
