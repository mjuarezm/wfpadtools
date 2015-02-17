"""Provide general tests for correctness of the wfpad protocol."""

# WFPadTools imports
import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import testutil as tu
from obfsproxy.test.transports.wfpadtools import wfpad_tester as wt

# Logging settings:
log = logging.get_obfslogger()


class TestReceivedBytes(wt.TestSendDataServer, tu.STTest):
    opcode = const.OP_SEND_PADDING
    N, t = 5, 1
    args = [N, t]

    AFTER_SESSION_TIME = 5

    def test_correctnes_bytes_stats(self):
        """Test that recorded number of bytes is correct."""
        # We sent 5 padding cells from server to client plus
        # the string `TEST_MSG`, we need to check that client
        # received the same amount of bytes as server, corresponding
        # to bytes of string and bytes of padding.

        # Test that server num snt msgs is equal to client num rcv msgs
        obs_cl_rcv_msgs = self.clientState["_numMessages"]['rcv']
        obs_sv_snd_msgs = self.serverState["_numMessages"]['snd']
        log.debug("Srv_snd_msgs = %s, Clt_rcv_msgs = %s",
                  obs_sv_snd_msgs, obs_cl_rcv_msgs)
        self.assertEqual(obs_cl_rcv_msgs, obs_sv_snd_msgs,
                         "Num msgs sent by server (%s) does not match num"
                         " msgs received by client (%s)."
                         % (obs_sv_snd_msgs, obs_cl_rcv_msgs))

        # Test sent and received TOTAL are equal
        obs_cl_rcv_total_bytes = self.clientState["_totalBytes"]['rcv']
        obs_sv_snd_total_bytes = self.serverState["_totalBytes"]['snd']
        log.debug("Srv_snd_total_bytes = %s, Clt_rcv_total_bytes = %s",
                  obs_sv_snd_total_bytes, obs_cl_rcv_total_bytes)
        self.assertEqual(obs_cl_rcv_total_bytes, obs_sv_snd_total_bytes,
                         "Total bytes sent by server (%s) does not match total"
                         " bytes received by client (%s)."
                         % (obs_sv_snd_total_bytes, obs_cl_rcv_total_bytes))

        # Test sent and received DATA are equal
        obs_cl_rcv_data_bytes = self.clientState["_dataBytes"]['rcv']
        obs_sv_snd_data_bytes = self.serverState["_dataBytes"]['snd']
        log.debug("Srv_snd_data_bytes = %s, Clt_rcv_data_bytes = %s",
                  obs_sv_snd_data_bytes, obs_cl_rcv_data_bytes)
        self.assertEqual(obs_cl_rcv_data_bytes, obs_sv_snd_data_bytes,
                         "Data bytes sent by server (%s) does not match data"
                         " bytes received by client (%s)."
                         % (obs_sv_snd_data_bytes, obs_cl_rcv_data_bytes))

        # Test data bytes are equal to bytes of string
        databytes = len(wt.TEST_MSG)
        log.debug("Data bytes = %s", databytes)
        self.assertEqual(obs_cl_rcv_data_bytes, databytes,
                         "Data bytes received by client (%s) does not match "
                         " length of test string: %s."
                         % (obs_cl_rcv_data_bytes, wt.TEST_MSG))

        # Test total bytes corresponds to the amount of padding messages plus
        # the data message multiplied by the payload len (wfpad pads to MPU by
        # default).
        totalbytes = (self.N + 1) * const.MPU
        log.debug("Total bytes = %s", totalbytes)
        self.assertEqual(obs_cl_rcv_total_bytes, totalbytes,
                         "Total bytes sent by server (%s) does not total "
                         " bytes (%s)." % (obs_cl_rcv_total_bytes, totalbytes))
