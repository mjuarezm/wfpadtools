from twisted.internet.base import DelayedCall
from twisted.trial import unittest

from obfsproxy.test.transports.wfpadtools.twisted import primitives_tester as pt
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import genutil as gu
from obfsproxy.transports.wfpadtools.util import mathutil   


# Set to True if you want twisted to cry when something goes wrong:
DelayedCall.debug = True

N_SAMPLES = 30


class SimpleRequestResponsePattern(pt.SessionPrimitiveTestCase, unittest.TestCase):
    primitive = 'relaySendPadding'
    
    def test_simple_request_response(self):
        """
        In this case, you want the client to generate a small burst of
        RELAY_DROP cells, and have the relay respond with a webpage sized set of
        RELAY_DROP cells with some small initial delay, but no inter-packet
        delays.
        
        This means that the client should maintain a RELAY_GAP histogram with
        when="send", but no RELAY_BURST histogram (since we're starting the
        burst off manually with a RELAY_DROP cell). The client-side RELAY_GAP
        histogram should have 10 tokens in the 0ms bin, 10 tokens in the
        Infinity bin, and set decay_by=20. 
        
        In this way, you would expect the client to generate a second
        back-to-back RELAY_DROP cell with 50% probability, a third back-to-back
        cell with 10/(10+20) == 33% probability, a fourth with 10/(10+20+20) ==
        20% probability, and so on. (Note that these probabilities are not
        normalized across the packet train, because of how we specified
        decay_by.. this could be something we might want to improve somehow).
        
        On the relay side, you would similarly have one RELAY_BURST histogram
        and one RELAY_GAP histogram (but both with when="receive" in this case).
        The RELAY_BURST histogram should have 10 tokens in the 50ms bin, 10
        tokens in the 100ms bin, and 10 tokens in the 200ms bin, and none in the
        Infinity bin. This should mean that there will be 33% probability of
        responding to the client's request in 50ms, 100ms, and 200ms. In the
        RELAY_GAP histogram, you would place a large number of tokens in the 0ms
        bin, slightly fewer in the Infinity bin, and a smaller decay_by
        parameter, but no other tokens in any other bins. The combination of
        these two histograms should produce large continuous packet trains in
        response to the client's RELAY_DROP cell "requests".
        
        The end result should look like a single multi-cell request, followed by
        a single, continuous, and longer multi-cell response.
        """
        
        interpolate = False
        removeTokens = False
        
#         client_burst_histo_snd = {}
#         self.pt_client.relayBurstHistogram(client_burst_histo_snd,
#                                            removeTokens, interpolate, 'snd')
#         client_burst_histo_rcv = {}
#         self.pt_client.relayBurstHistogram(client_burst_histo_rcv,
#                                            removeTokens, interpolate, 'rcv')
        client_gap_histo_snd = {0: 10, const.INF_LABEL: 10}
        self.pt_client.relayGapHistogram(client_gap_histo_snd,
                                         removeTokens, interpolate, 'snd',
                                         decay_by=20)
#         client_gap_histo_rcv = {}
#         self.pt_client.relayGapHistogram(client_gap_histo_rcv,
#                                          removeTokens, interpolate, 'rcv')

        
#         server_burst_histo_snd = {}
#         self.pt_server.relayBurstHistogram(server_burst_histo_snd,
#                                            removeTokens, interpolate, 'snd')
        server_burst_histo_rcv = {50: 10, 100: 10, 200: 10, const.INF_LABEL: 0}
        self.pt_server.relayBurstHistogram(server_burst_histo_rcv,
                                           removeTokens, interpolate, 'rcv')
#         
#         server_gap_histo_snd = {}
#         self.pt_server.relayGapHistogram(server_gap_histo_snd,
#                                          removeTokens, interpolate, 'snd')
        server_gap_histo_rcv = {0: 50, const.INF_LABEL: 30}
        self.pt_server.relayGapHistogram(server_gap_histo_rcv,
                                         removeTokens, interpolate, 'rcv')
        
        # we're starting the burst off manually with a RELAY_DROP cell:
        self.run_primitive(1, 0)
        
        ts_l = self.extract_ts(self.proto_server.history['rcv'])
        iats = gu.map_to_each_n_elements_in_list(ts_l, gu.get_iats)
        mean_iat = mathutil.mean(iats)

