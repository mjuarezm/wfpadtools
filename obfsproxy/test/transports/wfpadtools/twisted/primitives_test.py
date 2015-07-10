from random import randint
from twisted.internet.base import DelayedCall
from twisted.trial import unittest

from obfsproxy.test.transports.wfpadtools.twisted import primitives_tester as pt
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.message import isData, isPadding
from obfsproxy.transports.wfpadtools.util import genutil as gu
from obfsproxy.transports.wfpadtools.util import mathutil   


# Set to True if you want twisted to cry when something goes wrong:
DelayedCall.debug = True

N_SAMPLES = 30


class SendPaddingTestCase(pt.WFPadPrimitiveTestCase, unittest.TestCase):
    def test_total_bytes_is_num_pad_msgs_times_MTU_and_data_is_zero(self):
        delay = 1000
        num_padding_messages = 5
        self.pt_client.relaySendPadding(num_padding_messages, delay)
        self.advance_delayed_calls()
        self.assertEqual(self.pt_server.session.dataBytes['rcv'], 0)
        expected_bytes = num_padding_messages * const.MPU
        self.assertEqual(self.pt_server.session.totalBytes['rcv'], expected_bytes)

    def test_total_bytes_is_num_pad_msgs_times_MTU_and_data_is_zero_randomized(self):
        delay = randint(0, 1000)
        num_padding_messages = randint(0, 10)
        self.pt_client.relaySendPadding(num_padding_messages, delay)
        self.advance_delayed_calls()
        self.assertEqual(self.pt_server.session.dataBytes['rcv'], 0)
        expected_bytes = num_padding_messages * const.MPU
        self.assertEqual(self.pt_server.session.totalBytes['rcv'], expected_bytes)


class AppHintTestCase(pt.WFPadPrimitiveTestCase, unittest.TestCase):
    def test_session_status_is_visiting(self):
        sess_id = gu.hash_text(str(randint(1, 10)) + str(gu.timestamp()))
        status = True
        self.pt_client.relayAppHint(sess_id, status)
        self.pt_client.session.is_peer_padding = False
        self.assertTrue(self.pt_server._visiting)


class BurstHistogramTestCase(pt.SessionPrimitiveTestCase, unittest.TestCase):
    primitive = 'relayBurstHistogram'

    def test_snd_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.run_primitive(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)
        self.assertEqual(N_SAMPLES, len(iats))

    def test_snd_interpolate_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.run_primitive(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        for iat in iats:
            self.assertGreater(iat, 0)
            self.assertGreater(ts, iat)
        self.assertEqual(N_SAMPLES, len(iats))

    def test_rcv_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = randint(0, 5000)
        histo = {ts: 1}
        when = "rcv"
        self.run_primitive(histo, removeTokens, interpolate, when, endpoint=self.pt_server)
        padd_ts = self.extract_ts(self.proto_server.history['rcv'], isPadding)
        data_ts = self.extract_ts(self.proto_server.history['snd'], isData)
        ts_l = gu.combine_lists_alternate(data_ts, padd_ts)
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)
        self.assertEqual(N_SAMPLES, len(iats))

    def test_snd_removetoks_histogram_random_time(self):
        interpolate = False
        removeTokens = True
        ts = randint(0, 5000)
        n_tokens = 50
        histo = {ts: n_tokens}
        when = "snd"
        self.run_primitive(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        tokens = self.pt_client._burstHistoProbdist[when].hist[ts]
        self.assertEqual(tokens, n_tokens - N_SAMPLES)
        self.assertEqual(N_SAMPLES, len(iats))


class GapHistogramTestCase(pt.SessionPrimitiveTestCase, unittest.TestCase):
    primitive = 'relayGapHistogram'

    def run_primitive(self, *args, **kwargs):
        endpoint = kwargs.get('endpoint', self.pt_client)
        self.pt_client.relayBurstHistogram(*args)
        getattr(self.pt_client, self.primitive)(*args)
        self.send_timestamp(endpoint)
        self.advance_delayed_calls()

    def test_snd_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.run_primitive(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)

    def test_snd_interpolate_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.run_primitive(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        for iat in iats:
            self.assertGreater(iat, 0)
            self.assertGreater(ts, iat)

    def test_rcv_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = randint(0, 5000)
        histo = {ts: 1}
        when = "rcv"
        self.run_primitive(histo, removeTokens, interpolate, when, endpoint=self.pt_server)
        padd_ts = self.extract_ts(self.proto_server.history['rcv'], isPadding)
        data_ts = self.extract_ts(self.proto_server.history['snd'], isData)
        ts_l = gu.combine_lists_alternate(data_ts, padd_ts)
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)

    def test_snd_removetoks_histogram_random_time(self):
        interpolate = False
        removeTokens = True
        ts = randint(0, 5000)
        n_tokens = 50
        histo = {ts: n_tokens}
        when = "snd"
        self.run_primitive(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        tokens = self.pt_client._burstHistoProbdist[when].hist[ts]
        self.assertLess(tokens, n_tokens)


class TotalPadTestCase(pt.SessionPrimitiveTestCase, unittest.TestCase):

    def test_stop_condition_with_msgs(self):
        sess_id = self.sess_id
        t = randint(0, 100)
        msg_level = True
        n_padd_msgs = 11
        self.pt_client.relayTotalPad(sess_id, t, msg_level)
        self.pt_server.relayTotalPad(sess_id, t, msg_level)
        self.send_timestamp(self.pt_client)
        self.advance_delayed_calls(max_dcalls=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        pad_num_msgs = self.pt_client.session.totalPadding
        num_msgs = self.pt_client.session.numMessages['snd']
        self.assertGreaterEqual(num_msgs, pad_num_msgs)
        # payloadpad pads total num messages to closest power of two
        # closest power of 2 to n_padd_msgs is 16
        self.assertLessEqual(abs(num_msgs - 16), 1)

class PayloadPadTestCase(pt.SessionPrimitiveTestCase, unittest.TestCase):

    def test_stop_condition_with_msgs(self):
        sess_id = self.sess_id
        t = randint(0, 100)
        msg_level = True
        n_data_msgs = 7
        n_padd_msgs = 11
        self.pt_client.relayPayloadPad(sess_id, t, msg_level)
        self.advance_next_delayed_call()
        self.pt_server.relayPayloadPad(sess_id, t, msg_level)
        self.advance_next_delayed_call()
        for _ in xrange(n_data_msgs):
            self.send_timestamp(self.pt_client)
            self.advance_next_delayed_call()
        self.advance_delayed_calls(max_dcalls=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        num_msgs = self.pt_client.session.numMessages['snd']
        # payloadpad pads total num messages to closest multiple
        # of closest power of two of data msgs
        # closest power of two of n_data_msgs is 8
        # closes multiple of 8 to total msgs (n_data_msgs + n_padd_msgs = 18) is 24
        self.assertLessEqual(abs(num_msgs - 24), 1)


class BatchPadTestCase(pt.SessionPrimitiveTestCase, unittest.TestCase):

    def test_stop_condition_with_msgs(self):
        sess_id = self.sess_id
        L = 5
        t = randint(0, 100)
        msg_level = True
        n_data_msgs = 6
        n_padd_msgs = 11
        self.pt_client.relayBatchPad(sess_id, L, t, msg_level)
        self.advance_next_delayed_call()
        self.pt_server.relayBatchPad(sess_id, L, t, msg_level)
        self.advance_next_delayed_call()
        for _ in xrange(n_data_msgs):
            self.send_timestamp(self.pt_client)
            self.advance_next_delayed_call()
        self.advance_delayed_calls(max_dcalls=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        num_msgs = self.pt_client.session.numMessages['snd']
        # payload pads total num messages to closest multiple
        # of L to n_data_msgs + n_padd_msgs = 18 is 20
        self.assertLessEqual(abs(num_msgs - 20), 1)

    def test_stop_condition_with_bytes(self):
        sess_id = self.sess_id
        L = 5
        t = randint(0, 100)
        msg_level = False
        n_data_msgs = 6
        n_padd_msgs = 11
        self.pt_client.relayBatchPad(sess_id, L, t, msg_level)
        self.advance_next_delayed_call()
        self.pt_server.relayBatchPad(sess_id, L, t, msg_level)
        self.advance_next_delayed_call()
        for _ in xrange(n_data_msgs):
            self.send_timestamp(self.pt_client)
            self.advance_next_delayed_call()
        self.advance_delayed_calls(max_dcalls=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        num_bytes = self.pt_client.session.totalBytes['snd']
        # payload pads total num messages to closest multiple of L
        ts_len = 10
        stop_bytes = const.MPU * n_padd_msgs + n_data_msgs * ts_len + const.MPU
        self.assertLessEqual(abs(num_bytes - stop_bytes), 1)
