'''Provide general methods to deal with file and dir structure operations.'''
import csv
import psutil
import shutil
import signal
import commands
from os import makedirs, remove, kill, utime, symlink, unlink
from os.path import exists, isdir, isfile, dirname, abspath, realpath,\
    lexists

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const


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


def touch(fname, times=None):
    with open(fname, 'a'):
        utime(fname, times)


def write_list_to_csv(l, csvpath, mode='wb'):
    with open(csvpath, mode) as f:
        wr = csv.writer(f, dialect='excel')
        wr.writerows(l)


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


def resetdir(dirpath):
    """Removes and creates a new dir."""
    removedir(dirpath)
    createdir(dirpath)


def remove_symlink(linkpath):
    if lexists(linkpath):
        unlink(linkpath)


def replace_symlink(src, dst):
    """Remove old symlink and create a new one."""
    remove_symlink(dst)
    symlink(src, dst)


def run_cmd(cmd):
    return commands.getstatusoutput('%s ' % (cmd))


def get_package_path(pkg):
    try:
        m = __import__(pkg)
    except:
        raise Exception("Package `{}` could not be imported.".format(pkg))
    pkg_path = m.__file__
    pkg_abspath = abspath(pkg_path)
    pkg_realpath = realpath(pkg_abspath)
    return dirname(pkg_realpath)


def apply_patch_to_file(file_path, patch_path):
    """Apply patch to file and return string boolean on changes.

    Will return '1' if file had been already patched and '0' otherwise.
    """
    return bool(run_cmd("sudo patch -N -s {} < {} > {} 2>&1; echo $?"
                        .format(file_path, patch_path, const.DEFAULT_LOG)))


def apply_patch_to_dir(dir_path, patch_path):
    """Apply patch to directory and return string boolean on changes.

    Will return '1' if file had been already patched and '0' otherwise.
    """
    return bool(run_cmd("sudo cd {} && patch -p0 -s < {} > {} 2>&1; echo $?"
                        .format(dir_path, patch_path, const.DEFAULT_LOG)))


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
    """Terminate process with `pid`."""
    if is_pid_running(pid):
        kill(pid, signal.SIGTERM)


def kill_process(pid):
    """Terminate process with `pid`."""
    if is_pid_running(pid):
        kill(pid, signal.SIGKILL)


def get_pids_by_name(procname):
    """Return all pids associated to process name `procname`."""
    return [proc for proc in psutil.process_iter() if proc.name() == procname]


def is_procname_running(procname):
    """Return boolean whether the process identified by name is running."""
    return len(get_pids_by_name(procname)) > 0


def terminate_process_by_name(procname):
    """Terminate process by process name."""
    for proc in psutil.process_iter():
        if proc.name() == procname:
            proc.kill()
