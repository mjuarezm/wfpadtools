WFPadTools
==========

The WFPadTools framework is a framework implemented as an Obfsproxy Pluggable Transport to develop lin-padding-based website fingerprinting strategies in Tor. It was forked from the obfsproxy master branch at the torproject git.

[![Build Status](https://drone.io/bitbucket.org/mjuarezm/obfsproxy_wfpadtools/status.png)](https://drone.io/bitbucket.org/mjuarezm/obfsproxy_wfpadtools/latest)

It implements a framing layer for the Tor protocol that allows to add cover traffic and provides a set of primitives that can be used to implement more specific anti-website fingerprinting strategies.

To use this framework, developers can extend the WFPadTransport, WFPadClient
and WFPadServer classes included in this module and use their methods to
develop the pluggable transport that implements the specific countermeasure.

In addition to a protocol to insert dummy messages in a stream of Tor data,
WFPadTools implements a set of primitives that have been proposed by Mike
Perry in:

gitweb.torproject.org/user/mikeperry/torspec.git/blob/refs/heads/multihop-
padding-primitives:/proposals/ideas/xxx-multihop-padding-primitives.txt

These primitives have been extracted from existing website fingerprinting
designs within the research community, such as Tamaraw, CS-BuFLO and Adaptive
Padding. They have been generalized in order to allow for a broader set of
possible strategies.

For further details on the protocol see /doc/wfpadtools/wfpadtools-spec.txt.

Features of WFPadTools
----------------------

- It allows to pad each specific message to a specified length or to specify
  a probability distribution to draw a value for the length each time.

- It allows to specify the probability distributions for delays after data
  messages and delays after padding messages.

- Since each end runs an instance of the transport, it allows to implement
  strategies that treat incoming and outgoing traffic independently.

- It allows for constant-rate padding by specifying uniform distributions for
  the delays and allows to specify a general stop condition for padding. This
  allows to implements strategies such as BuFLO, CS-BuFLO and Tamaraw.

- It allows to add padding in response to traffic coming upstream (e.g., web
  server or Tor) and/or in response to downstream traffic (coming from the
  other end). Distributions governing these two can be specified independently.

Limitations
-----------

Important note: this framework is intended for research purposes and it has the
following limitations:

- This module does not provide encryption. That is why it must be always
  combined with another transport that does provide it. For example, the
  transport that implements the final countermeasure by extending
  WFPadTransport might take care of this.

- It only pads until the bridge but in a typical website fingerprinting
  scenario the adversary might be sitting on the entry guard. Any final
  website fingerprinting countermeasure should run padding until the middle
  node in order to protect against this threat model.

- For now we assume the user is browsing using a single tab. Right now the
  SOCKS shim proxy (socks_shim.py module) cannot distinguish SOCKS requests
  coming from different pages. In the future, in case these primitives are
  implemented in Tor, there might be easier ways to get this sort of
  application-level information.

- This implementation might be vulnerable to timing attacks (exploit timing
  timing differences between padding messages vs data messages. Although
  there is a small random component (e.g., state of the network and use of
  resources), a final implementation should take care of that.

- It provides tools for padding-based countermeasures. It cannot be used
  for other type of strategies.

- It cannot be used stand-alone (to obfuscate applications other
  than Tor, for instance).
