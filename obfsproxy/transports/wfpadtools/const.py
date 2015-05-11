from os.path import join, abspath, dirname, pardir, expanduser

# Shortcuts
jn = join
dn = dirname

# The protocol name which is used in log messages
TRANSPORT_NAME          = "wfpad"

# Paths
BASE_DIR                = abspath(jn(dirname(__file__), pardir, pardir, pardir))
OBFSPROXY_DIR           = jn(BASE_DIR, "obfsproxy")
PYOBFSPROXY_PATH        = jn(OBFSPROXY_DIR, "pyobfsproxy.py")
TEMP_DIR                = jn(BASE_DIR, "tmp")
TEST_DIR                = jn(OBFSPROXY_DIR, "test")
ETC_DIR                 = jn(TEST_DIR, "transports", "wfpadtools", "etc")
DEFAULT_LOG             = "wfpad.log"
TEST_DUMP_DIR           = jn(TEMP_DIR, "test_dumps")
DUMPS                   = {"client": join(TEST_DUMP_DIR, "client.dump"),
                           "server": join(TEST_DUMP_DIR, "server.dump")}

INF_LABEL               = float("inf")

# Scale is milliseconds
SCALE                   = 1000.0

# Protocol states
ST_WAIT                 = 0
ST_CONNECTED            = 1

# Flags header protocol
FLAG_DATA               = (1 << 0)  # 0001 = 1
FLAG_PADDING            = (1 << 1)  # 0010 = 2
FLAG_CONTROL            = (1 << 2)  # 0100 = 4
FLAG_LAST               = (1 << 3)  # 1000 = 8

# CS-BuFLO padding modes
PAYLOAD_PADDING         = 'payload'
TOTAL_PADDING           = 'total'

# Opcodes
OP_SEND_PADDING         = 1
OP_END_PADDING          = 2
OP_APP_HINT             = 3
OP_BURST_HISTO          = 4
OP_GAP_HISTO            = 5
OP_INJECT_HISTO         = 6
OP_TOTAL_PAD            = 7
OP_PAYLOAD_PAD          = 8
OP_BATCH_PAD            = 9

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
# which is probably 1500 (we substract 52 bytes = TCP (32B) + IP (20B) headers)
TOR_CELL_SIZE           = 512
MTU                     = 1448
MSS                     = 1460
PSIZE                   = 600

# Header length
MIN_HDR_LEN             = TOTLENGTH_LEN + PAYLOAD_LEN + FLAGS_LEN
CTRL_FIELDS_LEN         = CONTROL_LEN + ARGS_TOTAL_LENGTH_LEN
HDR_CTRL_LEN            = MIN_HDR_LEN + CTRL_FIELDS_LEN

# Maximum payload unit of a WFPad message in bytes
MPU                     = MTU - MIN_HDR_LEN
MPU_CTRL                = MTU - HDR_CTRL_LEN

# Max delay
MAX_DELAY               = 262144
INIT_RHO                = 0
MAX_RHO                 = 10000

# Default shim ports
SHIM_PORT               = 4997
SOCKS_PORT              = 4998

DEFAULT_SESSION         = 0
MAX_LAST_DATA_TIME      = 100

# Direction
OUT                     = 1
IN                      = -1

# IPs
LOCALHOST               = "127.0.0.1"
