from os.path import join, abspath, dirname, pardir
import tempfile


# The protocol name which is used in log messages
TRANSPORT_NAME          = "wfpad"

# Paths
TEMP_DIR                = tempfile.gettempdir()
TEST_SERVER_DIR         = join(TEMP_DIR, "test_server")

BASE_DIR                = abspath(join(dirname(__file__), pardir, pardir, pardir))
OBFSPROXY_DIR           = join(BASE_DIR, "obfsproxy") 
PYOBFSPROXY_PATH        = join(OBFSPROXY_DIR, "pyobfsproxy.py")

INF_LABEL               = -1

# Scale is milliseconds
SCALE                   = 1000.0

# Protocol states
ST_WAIT                 = 0
ST_CONNECTED            = 1

# Flags header protocol
FLAG_DATA               = (0 << 0)
FLAG_PADDING            = (1 << 0)
FLAG_CONTROL            = (1 << 1)
FLAG_LAST               = (1 << 2)

# CS-BuFLO padding modes
PAYLOAD_PADDING         = 'payload'
TOTAL_PADDING           = 'total'

# Opcodes
OP_SEND_PADDING         = 1
OP_APP_HINT             = 2
OP_BURST_HISTO          = 3
OP_GAP_HISTO            = 4
OP_INJECT_HISTO         = 5
OP_TOTAL_PAD            = 6
OP_PAYLOAD_PAD          = 7
OP_BATCH_PAD            = 8

# WFPad message structure fields's constants
TOTLENGTH_POS           = 0
TOTLENGTH_LEN           = 2

PAYLOAD_POS             = 2
PAYLOAD_LEN             = 2

FLAGS_POS               = 4
FLAGS_LEN               = 1

CONTROL_POS             = 5
CONTROL_LEN             = 1

ARGS_TOTAL_LENGTH_POS   = 6
ARGS_TOTAL_LENGTH_LEN   = 2

ARGS_POS                = 8

# Length of WFPad's MTU in bytes.  Note that this is *not* the link MTU
# which is probably 1500 (we substract 52 bytes = TCP+IP headers)
MTU                     = 1448
PSIZE                   = 600

# Header length
MIN_HDR_LEN             = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN
HDR_CTRL_LEN            = MIN_HDR_LEN + CONTROL_LEN + ARGS_TOTAL_LENGTH_LEN

# Maximum payload unit of a WFPad message in bytes
MPU                     = MTU - MIN_HDR_LEN
MPU_CTRL                = MTU - HDR_CTRL_LEN

# Max delay
MAX_DELAY               = 262144

# Default shim ports
SHIM_PORT               = 4997
SOCKS_PORT              = 4998

DEFAULT_SESSION         = 0
MAX_LAST_DATA_TIME      = 5
