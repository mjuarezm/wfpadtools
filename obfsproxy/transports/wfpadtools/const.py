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
DATA_DIRS = {"proxy": join(TEMP_DIR, "proxy"),
             "router": join(TEMP_DIR, "router")}
TRANSPORT_MODES = {"server": STRANS_SOCKSPORT,
                   "socks": CTRANS_SOCKSPORT}
DEBUG_FNAME = "debug.log"
FINISH_BOOTSRAP_LOGLINE = "Bootstrapped 100%: Done."

# Times
TOR_WATCHDOG_WAIT_TIME = 3
WATCHDOG_TIMEOUT = 60
DEFAULT_TIME_PERIOD = 60

# Protocol states
ST_WAIT = 0
ST_CONNECTED = 1
ST_PADDING = 2

# Flags header protocol
FLAG_DATA = (1 << 0)
FLAG_PADDING = (1 << 1)
FLAG_CONTROl = (1 << 2)

# Control OP codes
OP_START = (1 << 0)
OP_STOP = (1 << 1)

# WFPad message structure fields's constants
TOTLENGTH_POS = 0
TOTLENGTH_LEN = 2

PAYLOAD_POS = 2
PAYLOAD_LEN = 2

FLAGS_POS = 4
FLAGS_LEN = 1

# Header length
HDR_LENGTH = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN

# The maximum amount of padding to be appended to handshake data.
MAX_PADDING_LENGTH = 1500

# Length of WFPad's MTU in bytes.  Note that this is *not* the link MTU
# which is probably 1500.
MTU = 1448

# Maximum payload unit of a WFPad message in bytes.
MPU = MTU - HDR_LENGTH
