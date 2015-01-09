import copy
import inspect
import json
from os.path import join

from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools import util as ut


def instrument_class_method(func):
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
            ut.update_dump((self.__dict__, data), dump_path)
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
        if ":" in data:
            op, payload = data.split(":")
            if op == "TEST":
                opcode, args_str = payload.split(";")
                opcode = int(opcode)
                if opcode == 0:
                    self.sendDataMessage("foo")
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
        if enabled and data:
            control = parseControl(data,
                                   copy.deepcopy(data))
            if control:
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


def get_attributes(C):
    attributes = inspect.getmembers(C, lambda c: not(inspect.isroutine(c)))
    return {k: v for k, v in attributes if '__' not in k}
