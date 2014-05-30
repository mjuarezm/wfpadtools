from os.path import join, abspath, dirname, pardir
import tempfile


# Constant paths
TEMP_DIR = tempfile.gettempdir()
BASE_DIR = abspath(join(dirname(__file__), pardir, pardir))
PYOBFSPROXY_PATH = join(BASE_DIR, "pyobfsproxy.py")

# The protocol name which is used in log messages.
TRANSPORT_NAME = "wfpad"
STRANS_SOCKSPORT = "5000"
CTRANS_SOCKSPORT = "4999"

# Tor constants
ORPORT = "65535"
SOCKSPORT = "4998"
DATA_DIRS = {"proxy": join(TEMP_DIR, "proxy-wfpad"),
             "router": join(TEMP_DIR, "router-wfpad")}
TRANSPORT_MODES = {"server": STRANS_SOCKSPORT,
                   "socks": CTRANS_SOCKSPORT}
DEBUG_FNAME = "debug.log"
FINISH_BOOTSRAP_LOGLINE = "Bootstrapped 100%: Done."

# Times
TOR_WATCHDOG_WAIT_TIME = 3
WATCHDOG_TIMEOUT = 60
DEFAULT_TIME_PERIOD = 60

# Protocol states
ST_WAIT_FOR_VISIT = 0
ST_PADDING = 1
