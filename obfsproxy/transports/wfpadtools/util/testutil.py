import copy
import json
import socket
import unittest
from time import sleep
import multiprocessing
from os import access, X_OK
from os.path import join, isfile

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import dumputil as du
from obfsproxy.transports.wfpadtools.util import fileutil as fu


class STTest(unittest.TestCase):
    """Provide methods useful for testing."""

    def should_not_raise(self, msg, fn, *xargs, **kwargs):
        """Ensure calling `fn` with given args does not raise an exception."""
        try:
            fn(*xargs, **kwargs)
        except:
            self.fail(msg)
        else:
            pass

    def should_raise(self, msg, fn, *xargs, **kwargs):
        """Ensure calling `fn` with given args raises an exception."""
        try:
            fn(*xargs, **kwargs)
        except:
            pass
        else:
            self.fail(msg)

    def assert_is_installed(self, pkg):
        """Ensure the system package `pkg` is installed."""
        self.failUnless(fu.is_installed(pkg),
                        "Cannot find {} in your system".format(pkg))

    def assert_package_is_installed(self, pkg):
        """Ensure the python package `pkg` is installed."""
        try:
            __import__(pkg)
        except ImportError:
            self.fail("Cannot find python package %{} in"
                      " your system".format(pkg))

    def assert_is_file(self, fpath, msg):
        """Assert existence of file in path `fpath`."""
        self.assertTrue(isfile(fpath), msg)

    def assert_is_executable(self, binpath):
        """Ensure the file `binpath` is executable."""
        if not isfile(binpath):
            self.fail("Cannot find %s".format(binpath))
        if not access(binpath, X_OK):
            self.fail("Don\'t have execution permission"
                      " for {}".format(binpath))

    def new_temp_file(self, filename):
        """Add file to the remove-list."""
        self.files_to_remove.append(filename)
        return filename


class DummyWriteWorker(object):

    @staticmethod
    def work(host, port):
        writer = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sleep(2)
        writer.connect((host, port))

        try:
            while True:
                writer.sendall('\0')
        except Exception, e:
            print "[ReadWorker] Exception %s" % str(e)
        writer.close()

    def __init__(self, address):
        self.worker = multiprocessing.Process(target=self.work,
                                              args=(address))
        self.worker.start()

    def stop(self):
        if self.worker.is_alive():
            self.worker.terminate()


class DummyReadWorker(object):

    @staticmethod
    def work(host, port):
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((host, port))
        listener.listen(1)
        (conn, _) = listener.accept()
        listener.close()
        try:
            while True:
                conn.recv(4096)
        except Exception, e:
            print "[ReadWorker] Exception %s" % str(e)
        conn.close()

    def __init__(self, address):
        self.worker = multiprocessing.Process(target=self.work,
                                              args=(address))
        self.worker.start()

    def stop(self):
        if self.worker.is_alive():
            self.worker.terminate()


def instrument_dump(func):
    """Decorator to instrument method and dump temporary states.

    The decorator should be applied on a class method, as it accesses
    to `self`. The decorator dumps return values and state of the instance
    into a file for later verification and testing purposes.

    The aforementioned class should implement the following attributes:
        - enable_test: bool, will only dump if the value is True
        - dump_path: str, will dump to the file specified by its value.
    """
    def call_and_dump(self, *args, **kwargs):
        data = func(self, *args, **kwargs)
        cls = self.__class__
        enabled = get_attr("enable_test", cls)
        if enabled and data:
            dump_path = get_attr("dump_path", cls) if find_attr("dump_path", cls) \
                else join(const.TEMP_DIR, "dump_file")
            du.update_dump((du.only_pickleable(self), data), dump_path)
        return data
    return call_and_dump


def instrument_rcv_upstream(func):
    """Decorator that parses test messages.

    The decorator should be applied on a class method, as it accesses
    to `self`. The decorator check if upstream data contains a message
    following the test protocol.

    The aforementioned class should implement the following attributes:
        - enable_test: bool, will only dump if the value is True
        - dump_path: str, will dump to the file specified by its value.
    """
    def parseControl(self, data):
        data = data.read()
        if ":" in data:
            op, payload = data.split(":")
            if op == "TEST":
                opcode, args_str = payload.split(";")
                opcode = int(opcode)
                if opcode == 0:
                    self.sendDataMessage("foo\n")
                    return True
                args = None
                if args_str != "":
                    args = json.loads(args_str)
                self.sendControlMessage(opcode, args)
                return True
        return False

    def check_test_message(self, data):
        cls = self.__class__
        enabled = get_attr("enable_test", cls)
        if enabled and data and self.weAreClient:
            control = parseControl(self,
                                   copy.deepcopy(data))
            if control:
                data.read()
                return
        return func(self, data)
    return check_test_message


def find_attr(attr, cls):
    """Return true if attribute is in any of the ancestors of class."""
    while cls:
        if attr in cls.__dict__.keys():
            return cls
        cls = cls.__base__
    return None


def get_attr(attr, cls):
    """Return value of attribute found in class or ancestors."""
    cls = find_attr(attr, cls)
    return cls.__dict__[attr] if cls else None
