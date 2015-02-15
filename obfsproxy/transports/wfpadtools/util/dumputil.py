import inspect
import json
import cPickle as pick
from os.path import join, isfile, basename, dirname

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import logutil
from obfsproxy.transports.wfpadtools.util.genutil import timestamp
from obfsproxy.transports.wfpadtools.util.fileutil import removefile

log = logutil.get_logger("dumputil")

# Shortcuts
jn = join
bn = basename
dn = dirname


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


def check_pickable(obj):
    """Checks if object can be (c)pickled."""
    # TODO: write a test
    temp_file = join(const.TEMP_DIR, str(timestamp()) + "tmp")
    try:
        pick_dump(obj, temp_file)
    except:
        return False
    finally:
        removefile(temp_file)
    return True


def only_pickleable(C):
    # TODO: refactor
    attributes = inspect.getmembers(C, lambda c: not(inspect.isroutine(c)))
    return {k: v for k, v in attributes if not k.startswith("__")
            and check_pickable(v)}


def load_json(exp_spec_file):
    with open(exp_spec_file, "r") as f:
        return json.loads(f.read())


def dump_json(exp_spec_file):
    with open(exp_spec_file, "w") as f:
        return json.dumps(f.read())
