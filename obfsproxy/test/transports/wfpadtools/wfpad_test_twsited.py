import argparse

from twisted.trial import unittest
from twisted.test import proto_helpers
from twisted.internet.address import IPv4Address

from obfsproxy.common import transport_config
from obfsproxy.transports.transports import get_transport_class

from obfsproxy.transports.wfpadtools import const
from obfsproxy.network.network import StaticDestinationServerFactory


HOST = "127.0.0.1"
PORT = 0
ADDR = ":".join([HOST, str(PORT)])


class TransportTestCase(object):

    def setUp(self):
        self.proto_client = self._build_protocol("client")
        self.proto_server = self._build_protocol("server")


    def _build_protocol(self, mode):
        addr_tuple = (HOST, str(PORT))
        pt_config = self._build_transport_configuration(mode)
        transport_class = self._configure_transport_class(mode, pt_config)
        factory = StaticDestinationServerFactory(addr_tuple, mode, transport_class, pt_config)
        return factory.buildProtocol(IPv4Address('TCP', HOST, PORT))


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


class WFPadTransportTestCase(TransportTestCase, unittest.TestCase):

    transport = 'wfpad'

    def setUp(self):
        TransportTestCase.setUp(self)

        self._set_protocol_transport(self.proto_client)
        self._set_protocol_transport(self.proto_server)

        # shortcuts
        self.pt_client =self.proto_client.circuit.transport
        self.pt_server =self.proto_server.circuit.transport

    def _set_protocol_transport(self, protocol):
        # set upstream transport
        upstream = proto_helpers.StringTransport()
        protocol.makeConnection(upstream)

        # set downstream transport
        downstream = proto_helpers.StringTransport()
        protocol.makeConnection(downstream)

    def _test_primitive(self, primitive, args, expected):
        d = getattr(self.pt_client, primitive)(*args)

        def callback(d=None):
            msg_sent = self.proto_client.circuit.downstream.transport.value()
            self.proto_server.dataReceived(msg_sent)

            # wait till reaction from server
            msg_rcvd = self.proto_server.circuit.upstream.transport.value()
            self.assertEqual(len(msg_rcvd), expected)
        d[-1].addCallback(callback)
        return d

    def test_send_padding(self):
        delay = 0
        num_padding_messages = 5
        expected_bytes = num_padding_messages * const.MTU
        return self._test_primitive('relaySendPadding',
                                    (num_padding_messages, delay),
                                    expected_bytes)

