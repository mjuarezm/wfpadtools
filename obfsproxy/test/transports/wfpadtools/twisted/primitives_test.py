import argparse

import twisted
from twisted.internet import task, reactor
from twisted.trial import unittest
from twisted.test import proto_helpers
from twisted.internet.address import IPv4Address

from obfsproxy.common import transport_config
from obfsproxy.transports.transports import get_transport_class

from obfsproxy.transports.wfpadtools import const
from obfsproxy.network import network as net


HOST = "127.0.0.1"
PORT = 0
ADDR = ":".join([HOST, str(PORT)])

twisted.internet.base.DelayedCall.debug = True


class TransportTestCase(object):
    def setUp(self):
        self.proto_client = self._build_protocol("client")
        self.proto_server = self._build_protocol("server")

        self.pt_client = self.proto_client.circuit.transport
        self.pt_server = self.proto_server.circuit.transport

    def _build_protocol(self, mode):
        addr_tuple = (HOST, str(PORT))
        pt_config = self._build_transport_configuration(mode)
        transport_class = self._configure_transport_class(mode, pt_config)

        factory_server = net.StaticDestinationServerFactory(addr_tuple, mode, transport_class, pt_config)
        protocol_upstream = factory_server.buildProtocol(IPv4Address('TCP', HOST, PORT))

        factory_client = net.StaticDestinationClientFactory(protocol_upstream.circuit, "client")
        protocol_downstream = factory_client.buildProtocol(IPv4Address('TCP', HOST, PORT))

        # set protocol connections
        self._set_protocol_connection(protocol_upstream)
        self._set_protocol_connection(protocol_downstream)
        return protocol_upstream

    def _set_protocol_connection(self, protocol):
        protocol.makeConnection(proto_helpers.StringTransport())

    def _build_transport_configuration(self, mode):
        pt_config = transport_config.TransportConfig()
        pt_config.setStateLocation(const.TEMP_DIR)
        pt_config.setObfsproxyMode("managed")
        pt_config.setListenerMode(mode)
        return pt_config

    def _configure_transport_class(self, mode, pt_config):
        transport_args = [mode, ADDR, "--dest=%s" % ADDR]
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

    def tearDown(self):
        self._lose_protocol_connection(self.proto_client)
        self._lose_protocol_connection(self.proto_server)

        # Need to wait a bit beacuse obfsproxy netowrk.Circuit.circuitCompleted
        # defers 0.1s a dummy call to dataReceived to flush connection.
        return task.deferLater(reactor, 0.2, self._wait_deferred)


class PrimitiveTestCase(TransportTestCase):
    def _run_primitive_and_assert(self, primitive, args, assertion):
        d = getattr(self.pt_client, primitive)(*args)

        def cb(d=None):
            msg_sent = self.proto_client.circuit.downstream.transport.value()
            self.proto_server.dataReceived(msg_sent)
            assertion()

        if d:
            return d.addCallback(cb)
        return cb()


class WFPadTransportTestCase(PrimitiveTestCase, unittest.TestCase):
    transport = 'wfpad'


    def test_send_padding(self):
        delay = 0
        num_padding_messages = 5

        # assert total bytes received by server is the number of messages times MPU
        def assert_total_bytes():
            expected_bytes = num_padding_messages * const.MPU
            self.assertEqual(self.pt_server.session.totalBytes['rcv'], expected_bytes)

        return self._run_primitive_and_assert('relaySendPadding',
                                              (num_padding_messages, delay),
                                              assert_total_bytes)

    def test_relay_app_hint(self):
        sess_id = "12345"
        status = True

        # assert server state should be the one of a started session
        def assert_start_session():
            self.assertTrue(self.pt_server._visiting)
            self.assertTrue(self.pt_server.session.is_padding)
            # TODO: what else?

        return self._run_primitive_and_assert('relayAppHint',
                                              (sess_id, status),
                                              assert_start_session)


class BuFLOTransportTestCase(WFPadTransportTestCase):
    transport = 'buflo'


class CSBuFLOTransportTestCase(WFPadTransportTestCase):
    transport = 'csbuflo'


class AdaptiveTransportTestCase(WFPadTransportTestCase):
    transport = 'adaptive'
