import argparse
import random
from os.path import join
import sys

import twisted
from twisted.internet.error import TimeoutError
from twisted.trial import unittest
from twisted.internet import reactor
from twisted.test import proto_helpers
from twisted.internet.address import IPv4Address
from twisted.internet.task import Clock
from obfsproxy.pyobfsproxy import consider_cli_args, set_up_cli_parsing

from obfsproxy.transports.wfpadtools.util import mathutil
from obfsproxy.common import transport_config
from obfsproxy.transports.wfpadtools.message import isData, isPadding, isControl
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.transports import get_transport_class
from obfsproxy.transports.wfpadtools.util import genutil as gu
from obfsproxy.transports.wfpadtools import const
from obfsproxy.network import network as net


HOST = "127.0.0.1"
PORT = 0
ADDR = ":".join([HOST, str(PORT)])

N_SAMPLES = 30  # for testig histogram primitives

twisted.internet.base.DelayedCall.debug = True


class ClockTransportTestCase(object):
    def setUp(self):
        self.clock = Clock()
        reactor.callLater = self.clock.callLater
        self.proto_client = self._build_protocol(const.CLIENT)
        self.proto_server = self._build_protocol(const.SERVER)
        self.pt_client = self.proto_client.circuit.transport
        self.pt_server = self.proto_server.circuit.transport
        self._set_interception(self.proto_client, self.proto_server)
        self._bypass_connection(self.proto_client, self.proto_server)

    def _set_interception(self, client, server):
        def decorate_intercept(end):
            old_rcv_f = end.circuit.transport.receivedDownstream
            old_snd_f = end.circuit.transport.sendDownstream
            def curry_intercept(old_f, dir):
                def new_f(data):
                    msgs = old_f(data)
                    end.history[dir].append((self.clock.seconds(), msgs))
                return new_f
            end.circuit.transport.receivedDownstream = curry_intercept(old_rcv_f, 'rcv')
            end.circuit.transport.sendDownstream = curry_intercept(old_snd_f, 'snd')
        decorate_intercept(client)
        decorate_intercept(server)

    def _bypass_connection(self, client, server):
        def curry_bypass_connection(up, down):
            old_write = up.circuit.downstream.write
            def write(data):
                old_write(data)
                down.dataReceived(data)
            return write
        client.circuit.downstream.write = curry_bypass_connection(client, server)
        server.circuit.downstream.write = curry_bypass_connection(server, client)

    def _build_protocol(self, mode):
        addr_tuple = (HOST, str(PORT))
        address = IPv4Address('TCP', HOST, PORT)
        pt_config = self._build_transport_configuration(mode)
        transport_class = self._configure_transport_class(mode, pt_config)
        f_server = net.StaticDestinationServerFactory(addr_tuple, mode, transport_class, pt_config)
        protocol_server = f_server.buildProtocol(address)
        f_client = net.StaticDestinationClientFactory(protocol_server.circuit, const.CLIENT)
        protocol_client = f_client.buildProtocol(address)
        protocol_server.makeConnection(proto_helpers.StringTransport())
        protocol_client.makeConnection(proto_helpers.StringTransport())
        protocol_client.history = {'rcv': [], 'snd': []}
        protocol_server.history = {'rcv': [], 'snd': []}
        if mode == const.CLIENT:
            return protocol_client
        elif mode == const.SERVER:
            return protocol_server

    def _build_transport_configuration(self, mode):
        pt_config = transport_config.TransportConfig()
        pt_config.setStateLocation(const.TEMP_DIR)
        pt_config.setObfsproxyMode("managed")
        pt_config.setListenerMode(mode)
        return pt_config

    def _configure_transport_class(self, mode, pt_config):
        transport_args = [mode, ADDR, "--dest=%s" % ADDR] + self.args
        sys.argv = [sys.argv[0], "--log-file", join(const.TEMP_DIR, "%s.log" % mode),
                    "--log-min-severity", "debug"]
        sys.argv.append("wfpad")
        sys.argv += transport_args
        parser = set_up_cli_parsing()
        consider_cli_args(parser.parse_args())
        transport_class = get_transport_class(self.transport, mode)
        transport_class.setup(pt_config)
        p = argparse.ArgumentParser()
        transport_class.register_external_mode_cli(p)
        args = p.parse_args(transport_args)
        transport_class.validate_external_mode_cli(args)
        return transport_class

    def _lose_protocol_connection(self, protocol):
        protocol.circuit.upstream.transport.loseConnection()
        protocol.circuit.downstream.transport.loseConnection()

    def _wait_deferred(self, d=None):
        return d

    def advance_next_delayed_call(self):
        self.clock.advance(self.clock.getDelayedCalls()[0].getTime() - self.clock.seconds())

    def is_timeout(self, call):
        return isinstance(call.args[0], TimeoutError)

    def advance_delayed_calls(self, no_timeout=True, n_samples=N_SAMPLES):
        # TODO: needs refactoring
        timeouts = []
        i = 0
        while len(self.clock.getDelayedCalls()) > 0 and i < n_samples:
            i += 1
            delayed_call = self.clock.getDelayedCalls()[0]
            if no_timeout:
                if len(delayed_call.args) > 0 and self.is_timeout(delayed_call):
                    if delayed_call in timeouts:
                        break
                    timeout = self.clock.calls.pop(0)
                    timeout.time = 10000.0
                    self.clock.calls.append(timeout)
                    timeouts.append(delayed_call)
                    continue
            self.advance_next_delayed_call()

    def tearDown(self):
        # Need to wait a bit beacuse obfsproxy network.Circuit.circuitCompleted
        # defers 0.02s a dummy call to dataReceived to flush connection.
        self._lose_protocol_connection(self.proto_client)
        self._lose_protocol_connection(self.proto_server)
        self.advance_delayed_calls()


class WFPadPrimitiveTestCase(ClockTransportTestCase):
    transport = 'wfpad'
    args = []


class SessionPrimitiveTestCase(WFPadPrimitiveTestCase):
    sess_id = gu.hash_text(str(random.randint(1, 10)) + str(gu.timestamp()))

    def setUp(self):
        WFPadPrimitiveTestCase.setUp(self)
        self.pt_client.onSessionStarts(self.sess_id)

    def send_message(self, endpoint, msg):
        endpoint.receivedUpstream(msg)

    def send_str(self, endpoint, txt):
        b = Buffer()
        b.write(txt)
        self.send_message(endpoint, b)

    def send_timestamp(self, endpoint):
        self.send_str(endpoint, str(gu.timestamp()))

    def replay(self, trace):
        for p in trace:
            bytes_padding = self._lengthDataProbdist.randomSample()
            if p.direction == const.IN:
                self.send_str(self.pt_server, '\0' * bytes_padding)
            elif p.direction == const.OUT:
                self.send_str(self.pt_client, '\0' * bytes_padding)

    def dump_capture(self):
        pass

    def extract_ts(self, history, selector=gu.iden):
        return [ts for ts, msgs in history if len(msgs) > 0
                and len(self.extract_msgs(msgs, selector)) > 0]


    def extract_msgs(self, msgs, selector=gu.iden):
        return [msg for msg in msgs
                if selector(msg) and not isControl(msg)]


    def set_hist_and_get_samples(self, *args, **kwargs):
        endpoint = kwargs.get('endpoint', self.pt_client)
        getattr(self.pt_client, self.primitive)(*args)
        for i in xrange(N_SAMPLES):
            self.send_timestamp(endpoint)
            self.advance_delayed_calls()  # call flush buffer
            self.advance_delayed_calls()  # call timeouts set in flushbuffer
        self.advance_delayed_calls()

    def tearDown(self):
        if self.pt_client.isVisiting():
            self.pt_client.onSessionEnds(self.sess_id)
        self.pt_client.session.is_peer_padding = False
        WFPadPrimitiveTestCase.tearDown(self)


class SendPaddingTestCase(WFPadPrimitiveTestCase, unittest.TestCase):
    def test_total_bytes_is_num_pad_msgs_times_MTU_and_data_is_zero(self):
        delay = 1000
        num_padding_messages = 5
        self.pt_client.relaySendPadding(num_padding_messages, delay)
        self.advance_delayed_calls()
        self.assertEqual(self.pt_server.session.dataBytes['rcv'], 0)
        expected_bytes = num_padding_messages * const.MPU
        self.assertEqual(self.pt_server.session.totalBytes['rcv'], expected_bytes)

    def test_total_bytes_is_num_pad_msgs_times_MTU_and_data_is_zero_randomized(self):
        delay = random.randint(0, 1000)
        num_padding_messages = random.randint(0, 10)
        self.pt_client.relaySendPadding(num_padding_messages, delay)
        self.advance_delayed_calls()
        self.assertEqual(self.pt_server.session.dataBytes['rcv'], 0)
        expected_bytes = num_padding_messages * const.MPU
        self.assertEqual(self.pt_server.session.totalBytes['rcv'], expected_bytes)


class AppHintTestCase(WFPadPrimitiveTestCase, unittest.TestCase):
    def test_session_status_is_visiting(self):
        sess_id = gu.hash_text(str(random.randint(1, 10)) + str(gu.timestamp()))
        status = True
        self.pt_client.relayAppHint(sess_id, status)
        self.pt_client.session.is_peer_padding = False
        self.assertTrue(self.pt_server._visiting)


class BurstHistogramTestCase(SessionPrimitiveTestCase, unittest.TestCase):
    primitive = 'relayBurstHistogram'

    def test_snd_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = random.randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)
        self.assertEqual(N_SAMPLES, len(iats))

    def test_snd_interpolate_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = random.randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        for iat in iats:
            self.assertGreater(iat, 0)
            self.assertGreater(ts, iat)
        self.assertEqual(N_SAMPLES, len(iats))

    def test_rcv_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = random.randint(0, 5000)
        histo = {ts: 1}
        when = "rcv"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when, endpoint=self.pt_server)
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
        ts = random.randint(0, 5000)
        n_tokens = 50
        histo = {ts: n_tokens}
        when = "snd"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        tokens = self.pt_client._burstHistoProbdist[when].hist[ts]
        self.assertEqual(tokens, n_tokens - N_SAMPLES)
        self.assertEqual(N_SAMPLES, len(iats))


class GapHistogramTestCase(SessionPrimitiveTestCase, unittest.TestCase):
    primitive = 'relayGapHistogram'

    def set_hist_and_get_samples(self, *args, **kwargs):
        endpoint = kwargs.get('endpoint', self.pt_client)
        self.pt_client.relayBurstHistogram(*args)
        getattr(self.pt_client, self.primitive)(*args)
        self.send_timestamp(endpoint)
        self.advance_delayed_calls()

    def test_snd_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = random.randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)

    def test_snd_interpolate_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = random.randint(0, 5000)
        histo = {ts: 1}
        when = "snd"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        for iat in iats:
            self.assertGreater(iat, 0)
            self.assertGreater(ts, iat)

    def test_rcv_discrete_histogram_random_time(self):
        interpolate = False
        removeTokens = False
        ts = random.randint(0, 5000)
        histo = {ts: 1}
        when = "rcv"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when, endpoint=self.pt_server)
        padd_ts = self.extract_ts(self.proto_server.history['rcv'], isPadding)
        data_ts = self.extract_ts(self.proto_server.history['snd'], isData)
        ts_l = gu.combine_lists_alternate(data_ts, padd_ts)
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)
        self.assertAlmostEqual(ts / const.SCALE, mean_iat, 2)

    def test_snd_removetoks_histogram_random_time(self):
        interpolate = False
        removeTokens = True
        ts = random.randint(0, 5000)
        n_tokens = 50
        histo = {ts: n_tokens}
        when = "snd"
        self.set_hist_and_get_samples(histo, removeTokens, interpolate, when)
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        tokens = self.pt_client._burstHistoProbdist[when].hist[ts]
        self.assertLess(tokens, n_tokens)


class TotalPadTestCase(SessionPrimitiveTestCase, unittest.TestCase):

    def test_stop_condition_with_msgs(self):
        sess_id = self.sess_id
        t = random.randint(0, 100)
        msg_level = True
        n_padd_msgs = 11
        self.pt_client.relayTotalPad(sess_id, t, msg_level)
        self.pt_server.relayTotalPad(sess_id, t, msg_level)
        self.send_timestamp(self.pt_client)
        self.advance_delayed_calls(n_samples=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        pad_num_msgs = self.pt_client.session.totalPadding
        num_msgs = self.pt_client.session.numMessages['snd']
        self.assertGreaterEqual(num_msgs, pad_num_msgs)
        # payloadpad pads total num messages to closest power of two
        # closest power of 2 to n_padd_msgs is 16
        self.assertLessEqual(abs(num_msgs - 16), 1)

class PayloadPadTestCase(SessionPrimitiveTestCase, unittest.TestCase):

    def test_stop_condition_with_msgs(self):
        sess_id = self.sess_id
        t = random.randint(0, 100)
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
        self.advance_delayed_calls(n_samples=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        num_msgs = self.pt_client.session.numMessages['snd']
        # payloadpad pads total num messages to closest multiple
        # of closest power of two of data msgs
        # closest power of two of n_data_msgs is 8
        # closes multiple of 8 to total msgs (n_data_msgs + n_padd_msgs = 18) is 24
        self.assertLessEqual(abs(num_msgs - 24), 1)


class BatchPadTestCase(SessionPrimitiveTestCase, unittest.TestCase):

    def test_stop_condition_with_msgs(self):
        sess_id = self.sess_id
        L = 5
        t = random.randint(0, 100)
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
        self.advance_delayed_calls(n_samples=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        num_msgs = self.pt_client.session.numMessages['snd']
        # payloadpad pads total num messages to closest multiple
        # of L to n_data_msgs + n_padd_msgs = 18 is 20
        self.assertLessEqual(abs(num_msgs - 20), 1)

    def test_stop_condition_with_bytes(self):
        sess_id = self.sess_id
        L = 5
        t = random.randint(0, 100)
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
        self.advance_delayed_calls(n_samples=n_padd_msgs)
        self.pt_client.onSessionEnds(self.sess_id)
        self.advance_delayed_calls()
        num_bytes = self.pt_client.session.totalBytes['snd']
        num_msgs = self.pt_client.session.numMessages['snd']
        # payloadpad pads total num messages to closest multiple of L
        ts_len = 10
        stop_bytes = const.MPU * n_padd_msgs + n_data_msgs * ts_len + const.MPU
        self.assertLessEqual(abs(num_bytes - stop_bytes), 1)
