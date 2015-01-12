import commands
import hashlib
import math
from os import makedirs, remove, kill
from os.path import exists, isdir, isfile, join
from random import choice
import shutil
import signal
from time import sleep
from time import time

import cPickle as pick
from obfsproxy.transports.wfpadtools import const
import requesocks as requests


LOWERCASE_CHARS = 'abcdefghijklmnopqrstuvwxyz'
DIGITS = '0123456789'

DEFAULT_RAND_STR_SIZE = 6
DEFAULT_RAND_STR_CHARS = LOWERCASE_CHARS + DIGITS


def removefile(filepath):
    if exists(filepath) and isfile(filepath):
        remove(filepath)


def removedir(dirpath):
    """Remove dir if it does exist and is a dir."""
    if exists(dirpath) and isdir(dirpath):
        shutil.rmtree(dirpath)


def write_to_file(filepath, data, mode='w'):
    """Write data to file and close."""
    with open(filepath, mode) as f:
        f.write(data)


def append_to_file(filepath, data):
    """Write data to file and close."""
    write_to_file(filepath, data, mode='a')


def read_file(filepath):
    """Read and return file content."""
    content = None
    if exists(filepath) and isfile(filepath):
        with open(filepath, 'rU') as f:
            content = f.read()
    return content


def createdir(dirpath):
    """Create a dir if it does not exist."""
    if not exists(dirpath):
        makedirs(dirpath)
    return dirpath


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
    while line not in read_file(logfile):
        sleep(delay)
    cancel_timeout()


def run_cmd(cmd):
    return commands.getstatusoutput('%s ' % (cmd))


def is_installed(pkg_name):
    """Check if a package is installed."""
    cmd = 'which %s' % pkg_name
    status, _ = run_cmd(cmd)
    return False if status else True


def is_pid_running(pid):
    """Check process with `pid` is running."""
    # Only for UNIX platform!!
    return exists("/proc/{}".format(pid))


def terminate_process(pid):
    if is_pid_running(pid):
        kill(pid, signal.SIGTERM)


def rand_str(size=DEFAULT_RAND_STR_SIZE, chars=DEFAULT_RAND_STR_CHARS):
    """Return random string given a size and character space."""
    return ''.join(choice(chars) for _ in range(size))


def hash_text(text, algo='sha1'):
    """Return the hash value for the text."""
    h = hashlib.new(algo)
    h.update(text)
    return h.hexdigest()


def timestamp():
    return time()


def closest_multiple(n, k, ceil=True):
    """Return closest greater multiple of `k` to `n`."""
    if n == 0:
        return 0
    if n < k:
        return k
    if n % k == 0:
        return n
    return k * (n / k + (1 if ceil else 0))


def closest_power_of_two(n, ceil=True):
    """Return closest greater power of two to `n`."""
    if n == 0:
        return 0
    k = math.ceil(math.log(n, 2))
    return math.pow(2, k)


def bytes_after_total_padding(total_bytes, psize=1):
    """Return the total bytes transmitted after 'total' padding."""
    n2 = closest_power_of_two(total_bytes)
    return closest_multiple(n2, psize, ceil=False)


def bytes_after_payload_padding(data_bytes, total_bytes, psize=1):
    """Return the total bytes transmitted after 'payload' padding."""
    n2 = closest_power_of_two(data_bytes)
    m = closest_multiple(total_bytes, n2)
    return closest_multiple(m, psize, ceil=False)


def get_page(url, port, timeout):
    session = requests.session()
    session.proxies = {'http': 'socks5://127.0.0.1:{}'.format(port),
                       'https': 'socks5://127.0.0.1:{}'.format(port)}
    return session.get(url, timeout=timeout)


def check_picleable(obj):
    """Checks if object is can be cpickled."""
    # TODO: write a test
    temp_file = join(const.TEMP_DIR, str(timestamp()) + "tmp")
    try:
        pick_dump(obj, temp_file)
    except:
        return False
    finally:
        removefile(temp_file)
    return True


def pick_dump(obj, path):
    """Shorter method to dump objects."""
    with open(path, "wb") as f:
        pick.dump(obj, f)


def pick_load(path):
    """Shorter method to load objects."""
    with open(path, "rb") as f:
        return pick.load(f)


def update_dump(obj, fstate):
    """Updates dump file with new data."""
    dump_dict = {}
    if isfile(fstate):
        dump_dict = pick_load(fstate)
    dump_dict[timestamp()] = obj
    pick_dump(dump_dict, fstate)
