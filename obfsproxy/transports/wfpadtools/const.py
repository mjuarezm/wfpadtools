from os.path import join, abspath, dirname, pardir
import tempfile


# Constant paths
TEMP_DIR = tempfile.gettempdir()
BASE_DIR = abspath(join(dirname(__file__), pardir, pardir))
PYOBFSPROXY_PATH = join(BASE_DIR, "pyobfsproxy.py")

# Trnasport constants
TRANSPORT_NAME = "wfpad"  # The protocol name which is used in log messages.

# Tor constants
ORPORT = "65535"
DATA_DIRS = {"proxy": join(TEMP_DIR, "proxy"),
             "router": join(TEMP_DIR, "router")}

DEBUG_FNAME = "debug.log"
FINISH_BOOTSRAP_LOGLINE = "Bootstrapped 100%: Done."

# Times
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
OP_START = 0
OP_STOP = 1

# Generic primitives
OP_IGNORE = 2
OP_SEND_PADDING = 3
OP_APP_HINT = 4

# Adaptive padding primitives
OP_BURST_HISTO = 5
OP_INJECT_HISTO = 6

# CS-BuFLO primitives
OP_TOTAL_PAD = 7
OP_PAYLOAD_PAD = 8

# Tamaraw primitives
OP_BATCH_PAD = 9

# WFPad message structure fields's constants
TOTLENGTH_POS = 0
TOTLENGTH_LEN = 2

PAYLOAD_POS = 2
PAYLOAD_LEN = 2

FLAGS_POS = 4
FLAGS_LEN = 1

CONTROL_POS = 5
CONTROL_LEN = 1

# Header length
HDR_LENGTH = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN
HDR_CTRL_LENGTH = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN + CONTROL_LEN

# The maximum amount of padding to be appended to handshake data.
MAX_PADDING_LENGTH = 1500

# Length of WFPad's MTU in bytes.  Note that this is *not* the link MTU
# which is probably 1500.
MTU = 1448

# Maximum payload unit of a WFPad message in bytes.
MPU = MTU - HDR_LENGTH
MPU_CTRL = MTU - HDR_CTRL_LENGTH
