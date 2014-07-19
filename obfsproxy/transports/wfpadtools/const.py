from os.path import join, abspath, dirname, pardir
import tempfile


# Constant paths
TEMP_DIR = tempfile.gettempdir()
TEST_SERVER_DIR = join(TEMP_DIR, "test_server")
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
GET_PAGE_TIMEOUT = 10

# Protocol states
ST_WAIT = 0
ST_CONNECTED = 1
ST_PADDING = 2

# Flags header protocol
FLAG_DATA = (1 << 0)
FLAG_PADDING = (1 << 1)
FLAG_CONTROL = (1 << 2)

# Control OP codes
OP_START = 0
OP_STOP = 1

# Generic primitives
OP_IGNORE = 2
OP_SEND_PADDING = 3
OP_APP_HINT = 4

# Adaptive padding primitives
OP_BURST_HISTO = 5
OP_GAP_HISTO = 6
OP_INJECT_HISTO = 7

# CS-BuFLO primitives
OP_TOTAL_PAD = 8
OP_PAYLOAD_PAD = 9

# Tamaraw primitives
OP_BATCH_PAD = 10

# WFPad message structure fields's constants
TOTLENGTH_POS = 0
TOTLENGTH_LEN = 2

PAYLOAD_POS = 2
PAYLOAD_LEN = 2

FLAGS_POS = 4
FLAGS_LEN = 1

CONTROL_POS = 5
CONTROL_LEN = 1

ARGS_POS = 6


# arguments specification [arg_1, arg_2, ...] where arg_i = (length, type)
class arg(object):

    def __init__(self, arg_length, arg_type, name=None):
        self.length = arg_length
        self.type = arg_type
        self.name = name

    def __len__(self):
        return self.length


def get_args_len(self, opcode):
    return sum(map(len, ARGS_DICT[opcode]))

ARGS_DICT = {OP_SEND_PADDING: [arg(1, ord, "num_padding_msgs"), arg(1, ord, "delay")],
             OP_APP_HINT: [arg(1, str, "session_id"), arg(1, bool, "status")],
             OP_BURST_HISTO: [arg(1, list, "histogram"), arg(1, list, "labels_ms"), arg(1, bool, "remove_toks")],
             OP_GAP_HISTO: [arg(1, list, "histogram"), arg(1, list, "labels_ms"), arg(1, bool, "remove_toks")],
             OP_INJECT_HISTO: [arg(1, list, "histogram"), arg(list, "labels_ms")],
             OP_TOTAL_PAD: [],
             OP_PAYLOAD_PAD: [arg(1, str, "session_id"), arg(1, int, "delay")],
             OP_BATCH_PAD: [arg(1, str, "session_id"), arg(1, int, "L"), arg(1, int, "delay")],
            }

# Header length
MIN_HDR_LEN = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN
CTRL_HDR_LEN = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN + CONTROL_LEN

# The maximum amount of padding to be appended to handshake data.
MAX_PADDING_LENGTH = 1500

# Length of WFPad's MTU in bytes.  Note that this is *not* the link MTU
# which is probably 1500.
MTU = 1448

# Maximum payload unit of a WFPad message in bytes.
MPU = MTU - MIN_HDR_LEN
MPU_CTRL = MTU - CTRL_HDR_LEN
