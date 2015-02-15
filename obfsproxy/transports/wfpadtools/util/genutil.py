'''Provides general utility methods.'''
import signal
import hashlib
from random import choice
from os.path import exists
from time import strftime, sleep

from obfsproxy.transports.wfpadtools.util import fileutil as fu
import itertools


LOWERCASE_CHARS = 'abcdefghijklmnopqrstuvwxyz'
DIGITS = '0123456789'

DEFAULT_RAND_STR_SIZE = 6
DEFAULT_RAND_STR_CHARS = LOWERCASE_CHARS + DIGITS


class TimeExceededError(Exception):
    pass


def raise_signal(signum, frame):
    raise TimeExceededError("Timed Out!")


def set_timeout(duration, callback=None):
    """Timeout after given duration."""
    # SIGALRM is only usable on a unix platform!
    signal.signal(signal.SIGALRM, raise_signal)
    signal.alarm(duration)  # alarm after X seconds
    if callback:
        callback()


def cancel_timeout():
    signal.alarm(0)


def log_watchdog(line, logfile, timeout, delay=1, callback=None):
    set_timeout(timeout, callback)
    while not exists(logfile):
        sleep(delay)
    while line not in fu.read_file(logfile):
        sleep(delay)
    cancel_timeout()


def rand_str(size=DEFAULT_RAND_STR_SIZE, chars=DEFAULT_RAND_STR_CHARS):
    """Return random string given a size and character space."""
    return ''.join(choice(chars) for _ in range(size))


def hash_text(text, algo='sha1'):
    """Return the hash value for the text."""
    h = hashlib.new(algo)
    h.update(text)
    return h.hexdigest()


def timestamp():
    """Return a timestamp as string."""
    from time import time
    return str(int(time()))


def beautiful_timestmap():
    """Return a timestamp formatted as Year_month_dat-hour_minut_second."""
    return strftime("%Y_%m_%d-%H_%M_%S")


def lcat(*lists):
    """Concatenate lists."""
    return list(itertools.chain(*lists))


def memodict(f):
    """Memoization decorator for a function taking a single argument."""
    class memodict(dict):
        def __missing__(self, key):
            ret = self[key] = f(key)
            return ret
    return memodict().__getitem__


def flatten_list(l):
    """Return a flattened list of lists."""
    return [item for sublist in l for item in sublist]


def sort_tuple_list(l, tup_idx=0):
    """Return the list of tuples sorted by the index passed as argument."""
    return sorted(l, key=lambda tup: tup[tup_idx])


def apply_consecutive_elements(l, fn):
    """Apply `fn` taking as arguments consecutive elements of `l`."""
    return [fn(i, j) for i, j in zip(l[:-1], l[1:])]
