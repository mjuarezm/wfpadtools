"""
This module provides code to generate and sample probability distributions.

The class RandProbDist provides an interface to randomly generate probability
distributions.  Random samples can then be drawn from these distributions.
"""

from random import randint
import random

import const
import obfsproxy.transports.wfpadtools.const as cons
import obfsproxy.common.log as logging
import bisect
from obfsproxy.transports.base import PluggableTransportError


log = logging.get_obfslogger()


class RandProbDist:

    """
    Provides code to generate, sample and dump probability distributions.
    """

    def __init__( self, genSingleton=None, genProbSignleton=None, seed=None, histo=None,
                  labels=None, bins=None, interpolate=None, removeToks=None):
        """
        Initialise a discrete probability distribution.

        The parameter `genSingleton' is expected to be a function which yields
        singletons for the probability distribution.  The optional `seed' can
        be used to seed the PRNG so that the probability distribution is
        generated deterministically.
        """
        assert(genSingleton or histo)

        self.histo = histo
        self.labels = labels
        self.interpolate = interpolate
        self.removeToks = removeToks

        if histo:
            self.templateHisto = list(histo)
            assert(labels != None and interpolate != None and removeToks != None)
            if sum(self.histo) <= 0:
                raise PluggableTransportError("Use %s bin label in the histo "
                                              "to indicate that a sample can't"
                                              " be drawn." % cons.INF_LABEL)
        else:
            self.prng = random if (seed is None) else random.Random(seed)
            self.sampleList = []
            self.dist = self.genDistribution(genSingleton, genProbSignleton, bins)
            self.dumpDistribution()

    def genDistribution( self, genSingleton, genProbSignleton, bins=None):
        """
        Generate a discrete probability distribution.

        The parameter `genSingleton` is a function which is used to generate
        singletons for the probability distribution. `genProbSignleton`
        returns the probabilities for singletons returned by `genSingleton`.
        """
        dist = {}

        # Amount of distinct bins, i.e., packet lengths or inter arrival times.
        if not bins:
            bins = self.prng.randint(const.MIN_BINS, const.MAX_BINS) + 1

        # Cumulative probability of all bins.
        cumulProb = 0

        for index in xrange(bins - 1):
            if genProbSignleton:
                prob = genProbSignleton(index, bins, cumulProb)
            else:
                prob = self.prng.uniform(0, (1 - cumulProb))
            cumulProb += prob

            singleton = genSingleton(index, bins, cumulProb)
            dist[singleton] = prob
            self.sampleList.append((cumulProb, singleton,))

        dist[genSingleton(index, bins, cumulProb)] = (1 - cumulProb)

        return dist

    def dumpDistribution( self ):
        """
        Dump the probability distribution using the logging object.

        Only probabilities > 0.01 are dumped.
        """
        log.debug("Dumping probability distribution.")

        for singleton in self.dist.iterkeys():
            # We are not interested in tiny probabilities.
            if self.dist[singleton] > 0.01:
                log.debug("P(%s) = %.3f" %
                          (str(singleton), self.dist[singleton]))

    def getIndexFromLabel(self, label):
        if self.interpolate:
            return bisect.bisect_right(self.labels, label,
                                      hi=len(self.labels) - 1)
        else:
            return self.labels.index(label)

    def _removeTokIter(self, index):
        for i, value in enumerate(self.histo[index:]):
            if value > 0:
                self.histo[index + i] -= 1
                return

    def refillHisto(self):
        self.histo = list(self.templateHisto)

    def removeToken(self, label):
        if self.histo and self.removeToks == True:
            histo_i = self.getIndexFromLabel(label)
            if sum(self.histo) == 0:
                self.refillHisto()
            self._removeTokIter(histo_i)
            log.debug("[probdist] Removed tokem from bin %s" % histo_i)
        else:
            pass

    def randomSample( self ):
        """
        Draw and return a random sample from the probability distribution.
        """
        if self.histo:
            sample = randint(1, sum(self.histo))  # between 0 and sum_tokens
            for i, b in enumerate(self.histo):
                sample -= b
                if sample <= 0:
                    if self.interpolate and i < len(self.histo) - 1:
                        if i == 0:
                            return self.labels[i] * random.random()
                        elif i == len(self.histo) - 2:
                            return self.labels[i - 1] + (cons.MAX_DELAY - \
                                        self.labels[i - 1]) * random.random()
                        elif i == len(self.histo):
                            return cons.INF_LABEL
                        else:
                            return self.labels[i - 1] + (self.labels[i] - \
                                        self.labels[i - 1]) * random.random()
                    return self.labels[i]
        else:
            assert len(self.sampleList) > 0

            rand = random.random()

            for cumulProb, singleton in self.sampleList:
                if rand <= cumulProb:
                    return singleton
            return self.sampleList[-1][1]

# Alias class name in order to provide a more intuitive API.
new = RandProbDist


def uniform(x):
    return new(lambda i, n, c: x, lambda i, n, c: 1)
