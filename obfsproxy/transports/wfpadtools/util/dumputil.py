import inspect
import json
import cPickle as pick
from os.path import join, isfile, basename, dirname

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools.util.genutil import timestamp
from obfsproxy.transports.wfpadtools.util.fileutil import removefile

log = logging.get_obfslogger()

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
    dump_list = []
    if isfile(fstate):
        dump_list = pick_load(fstate)
    dump_list.append(obj)
    pick_dump(dump_list, fstate)


def check_pickable(obj):
    """Checks if object can be (c)pickled."""
    # TESTME!
    temp_file = join(const.TEMP_DIR, str(timestamp()) + "tmp")
    try:
        pick_dump(obj, temp_file)
    except:
        return False
    finally:
        try:
            removefile(temp_file)
        except Exception as e:
            log.error("The file %s could not be removed: %s",
                      temp_file, e)
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
