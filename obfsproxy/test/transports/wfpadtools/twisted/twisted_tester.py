from argparse import ArgumentParser
from os.path import join
from twisted.internet import reactor
from twisted.internet.address import IPv4Address
from twisted.internet.error import TimeoutError
from twisted.internet.task import Clock
from twisted.test import proto_helpers
from twisted.trial import unittest
import sys

from obfsproxy.common import transport_config
from obfsproxy.network import network as net
from obfsproxy.pyobfsproxy import consider_cli_args, set_up_cli_parsing
from obfsproxy.transports.transports import get_transport_class
from obfsproxy.transports.wfpadtools import const


# Global variables for all the test cases
HOST = "127.0.0.1"
PORT = 0
ADDR = ":".join([HOST, str(PORT)])
NUM_DCALLS = 30  # default maximum number of delayed calls to call.


class TransportTestCase(object):
    """PT client and server connect over a string transport.

    We bypass the communication between client and server and intercept the
    messages sent over the string transport.
    """

    def setUp(self):
        """Set the reactor's callLater to our clock's callLater function
        and build the protocols.
        """
        self.clock = Clock()
        reactor.callLater = self.clock.callLater
        self.dump = []
        self.proto_client = self._build_protocol(const.CLIENT)
        self.proto_server = self._build_protocol(const.SERVER)
        self.pt_client = self.proto_client.circuit.transport
        self.pt_server = self.proto_server.circuit.transport
        self._proxy(self.proto_client, self.proto_server)
        self._bypass_connection(self.proto_client, self.proto_server)

    def _proxy(self, client, server):
        """Proxy the communication between client and server and dump
        intercepted data into a dictionary.
        """
        def decorate_intercept(end):
            old_rcv_f = end.circuit.transport.receivedDownstream
            old_snd_f = end.circuit.transport.sendDownstream
            def intercept(old_f, direction):
                def new_f(data):
                    msgs = old_f(data)
                    end.history[direction].append((self.clock.seconds(), msgs))
                return new_f
            end.circuit.transport.receivedDownstream = intercept(old_rcv_f, 'rcv')
            end.circuit.transport.sendDownstream = intercept(old_snd_f, 'snd')
        decorate_intercept(client)
        decorate_intercept(server)

    def _bypass_connection(self, client, server):
        """Instead of requiring TCP connections between client and server
        transports, we directly pass the data written from one end to the
        received function at the other.
        """
        def curry_bypass_connection(up, down, direction):
            old_write = up.circuit.downstream.write
            def write(data):
                old_write(data)
                down.dataReceived(data)
                self.dump.append((self.clock.seconds(), direction * len(data)))
            return write
        client.circuit.downstream.write = curry_bypass_connection(client, server, const.OUT)
        server.circuit.downstream.write = curry_bypass_connection(server, client, const.IN)

    def _build_protocol(self, mode):
        """Build client and server protocols for an end point."""
        addr_tuple = (HOST, str(PORT))
        address = IPv4Address('TCP', HOST, PORT)
        pt_config = self._build_transport_configuration(mode)
        transport_class = self._configure_transport_class(mode, pt_config)
        f_server = net.StaticDestinationServerFactory(addr_tuple, mode, transport_class, pt_config)
        protocol_server = self._set_protocol(f_server, address)
        f_client = net.StaticDestinationClientFactory(protocol_server.circuit, const.CLIENT)
        protocol_client = self._set_protocol(f_client, address)
        if mode == const.CLIENT:
            return protocol_client
        elif mode == const.SERVER:
            return protocol_server
        else:
            raise ValueError("Transport mode '%s' not recognized." % mode)

    def _set_protocol(self, factory, address):
        """Make protocol connection with a Twisted string transport."""
        protocol = factory.buildProtocol(address)
        protocol.makeConnection(proto_helpers.StringTransport())
        protocol.history = {'rcv': [], 'snd': []}
        return protocol

    def _build_transport_configuration(self, mode):
        """Configure transport as a managed transport."""
        pt_config = transport_config.TransportConfig()
        pt_config.setStateLocation(const.TEMP_DIR)
        pt_config.setObfsproxyMode("managed")
        pt_config.setListenerMode(mode)
        return pt_config

    def _configure_transport_class(self, mode, pt_config):
        """Use the global arguments to configure the trasnport."""
        transport_args = [mode, ADDR, "--dest=%s" % ADDR] + self.args
        sys.argv = [sys.argv[0],
                "--log-file", join(const.TEMP_DIR, "%s.log" % mode),
                "--log-min-severity", "debug"]
        sys.argv.append("wfpad")  # use wfpad transport
        sys.argv += transport_args
        parser = set_up_cli_parsing()
        consider_cli_args(parser.parse_args())
        transport_class = get_transport_class(self.transport, mode)
        transport_class.setup(pt_config)
        p = ArgumentParser()
        transport_class.register_external_mode_cli(p)
        args = p.parse_args(transport_args)
        transport_class.validate_external_mode_cli(args)
        return transport_class

    def _lose_protocol_connection(self, protocol):
        """Disconnect client and server transports."""
        protocol.circuit.upstream.transport.loseConnection()
        protocol.circuit.downstream.transport.loseConnection()

    def advance_next_delayed_call(self):
        """Advance clock to first delayed call in reactor."""
        first_delayed_call = self.clock.getDelayedCalls()[0]
        self.clock.advance(first_delayed_call.getTime() - self.clock.seconds())

    def is_timeout(self, call):
        """Check if the call has actually timed out."""
        return isinstance(call.args[0], TimeoutError)

    def advance_delayed_calls(self, max_dcalls=NUM_DCALLS, no_timeout=True):
        """Advance clock to the point all delayed calls up to that moment have
        been called.
        """
        i, timeouts = 0, []
        while len(self.clock.getDelayedCalls()) > 0 and i < max_dcalls:
            i += 1
            dcall = self.clock.getDelayedCalls()[0]
            if no_timeout:
                if len(dcall.args) > 0 and self.is_timeout(dcall):
                    if dcall in timeouts:
                        break
                    self._queue_first_call()
                    timeouts.append(dcall)
                    continue
            self.advance_next_delayed_call()

    def _queue_first_call(self, delay=10000.0):
        """Put the first delayed call to the last position."""
        timeout = self.clock.calls.pop(0)
        timeout.time = delay
        self.clock.calls.append(timeout)

    def tearDown(self):
        """Close connections and advance all delayed calls."""
        # Need to wait a bit beacuse obfsproxy network.Circuit.circuitCompleted
        # defers 0.02s a dummy call to dataReceived to flush connection.
        self._lose_protocol_connection(self.proto_client)
        self._lose_protocol_connection(self.proto_server)
        self.advance_delayed_calls()

