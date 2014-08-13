import commands
import hashlib
from os import makedirs, remove, kill
from os.path import exists, isdir, isfile
from random import choice
import shutil
import signal
from time import sleep
import requesocks as requests
from obfsproxy.transports.wfpadtools import const


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


def set_timeout(duration):
    """Timeout after given duration."""
    # SIGALRM is only usable on a unix platform!
    signal.signal(signal.SIGALRM, raise_signal)
    signal.alarm(duration)  # alarm after X seconds


def cancel_timeout():
    signal.alarm(0)


def log_watchdog(line, logfile, timeout, delay=1):
    set_timeout(timeout)
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
    from time import time
    return time()


def get_page(url, port, timeout):
    session = requests.session()
    session.proxies = {'http': 'socks5://127.0.0.1:{}'.format(port),
                       'https': 'socks5://127.0.0.1:{}'.format(port)}
    return session.get(url, timeout=timeout)
