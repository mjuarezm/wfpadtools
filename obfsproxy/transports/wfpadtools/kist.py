""""
Implements the link capacity estimation algorithm from
    'Never Been KIST: Tor's Congestion Management Blossoms with
    Kernel-Informed Socket Transport'

This is in fact a translation from go to python of Yawning's kist
module in basket:
https://github.com/Yawning/basket/blob/master/kist/kist_linux.go
"""
import array
import fcntl
import socket
import struct
import termios  # @UnresolvedImport

import obfsproxy.common.log as logging


log = logging.get_obfslogger()


def estimate_write_capacity(sock):
    """Attempt to figure out how much can be written to `sock` without blocking.

    It is assumed that `sock` is a TCP socket (since the algorithm
    queries TCP_INFO).

    The amount that can be sent at any time can be estimated as:
        socket_space = sndbufcap - sndbuflen
        tcp_space = (cwnd - unacked) * mss
        limit = min(socket_space, tcp_space)
    """
    # Determine the total capacity of the send socket buffer "sndbufcap",
    # with a SO_SNDBUF getsockopt() call, and the current amount of data in
    # the send socket buffer "sndbuflen" with a TIOCOUTQ ioctl.
    sndbufcap = sock.getsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF)
    buf = array.array('h', [0])  # signed short array
    fcntl.ioctl(sock, termios.TIOCOUTQ, buf, 1)
    sndbuflen = buf[0]
    socket_space = sndbufcap - sndbuflen

    # Determine the tcp_space via a TCP_INFO getsockopt() call.
    # The struct fmt is 7 bytes followed by 24 unsig ints, for more detail
    # see: http://lxr.free-electrons.com/source/include/uapi/linux/tcp.h#L149
    # * snd_cwnd = TCP congestion window size (number of segments we can send)
    # * unacked = number of segments that need to be acked
    # * snd_mss = maximum segment size specified by the sender
    # snd_cwnd - unacked = number of segments with PT *data* that we can send
    tcp_info = struct.unpack("B"*7+"I"*24,
                             sock.getsockopt(socket.SOL_TCP,
                                             socket.TCP_INFO, 104))
    snd_cwnd, unacked, snd_mss = tcp_info[25], tcp_info[11], tcp_info[9]
    tcp_space = (snd_cwnd - unacked) * snd_mss

    # Return the minimum of the two capacities.
    if tcp_space > socket_space:
        log.debug("[kist module] socket_space (%s) is smaller"
                  " than tcp_space (%s)" % (socket_space, tcp_space))
        return socket_space
    log.debug("[kist module] tcp_space is: %s, socket space is: %s"
              % (socket_space, tcp_space))
    return tcp_space
