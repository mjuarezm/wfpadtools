from random import randint

from obfsproxy.test.transports.wfpadtools.twisted.twisted_tester import TransportTestCase, TCPTransportTestCase
from obfsproxy.transports.scramblesuit.fifobuf import Buffer
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.message import isControl
from obfsproxy.transports.wfpadtools.util import genutil as gu


# Default number of samples for a test case
N_SAMPLES = 30


class WFPadPrimitiveTestCase(TCPTransportTestCase):
    """Define a test case for primitives that do not need a session."""
    transport = 'wfpad'
    args = []


class SessionPrimitiveTestCase(WFPadPrimitiveTestCase):
    """Provide methods for test cases that do require a session."""
    sess_id = gu.hash_text(str(randint(1, 10)) + str(gu.timestamp()))

    def setUp(self):
        """Start a session."""
        WFPadPrimitiveTestCase.setUp(self)
        self.pt_client.onSessionStarts(self.sess_id)

    def send_message(self, endpoint, msg):
        """Send message to the specified endpoint."""
        endpoint.receivedUpstream(msg)

    def send_str(self, endpoint, txt):
        """Send a text string to the endpoint."""
        b = Buffer()
        b.write(txt)
        self.send_message(endpoint, b)

    def send_timestamp(self, endpoint):
        """Send a timestamp to the endpoint."""
        self.send_str(endpoint, str(gu.timestamp()))

    def extract_ts(self, history, selector=gu.iden):
        """Extract the list of timestamps from the history of messages."""
        return [ts for ts, msgs in history if len(msgs) > 0
                and len(self.extract_msgs(msgs, selector)) > 0]

    def extract_msgs(self, msgs, selector=gu.iden):
        """Extract messages satisfying a condition specified by `selector`."""
        return [msg for msg in msgs if selector(msg) and not isControl(msg)]

    def run_primitive(self, *args, **kwargs):
        """Run the primitive with the specified arguments."""
        endpoint = kwargs.get('endpoint', self.pt_client)
        getattr(self.pt_client, self.primitive)(*args)
        for _ in xrange(N_SAMPLES):
            self.send_timestamp(endpoint)
            self.advance_delayed_calls()  # call flush buffer
            self.advance_delayed_calls()  # call timeouts set in flushbuffer
        self.advance_delayed_calls()

    def tearDown(self):
        """Close session and tear down the setting."""
        if self.pt_client.isVisiting():
            self.pt_client.onSessionEnds(self.sess_id)
        self.pt_client.session.is_peer_padding = False
        WFPadPrimitiveTestCase.tearDown(self)


class DumpTrafficTestCase(SessionPrimitiveTestCase):
    
    def setUp(self):
        SessionPrimitiveTestCase.setUp(self)
        
    def tearDown(self):
        SessionPrimitiveTestCase.tearDown(self)
