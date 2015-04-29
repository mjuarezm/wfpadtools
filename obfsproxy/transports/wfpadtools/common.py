from twisted.internet import reactor, task
from twisted.internet.defer import CancelledError

import obfsproxy.common.log as logging
import obfsproxy.transports.wfpadtools.const as const
from obfsproxy.transports.wfpadtools.util.mathutil import closest_power_of_two, closest_multiple


log = logging.get_obfslogger()


def deferLater(*args, **kargs):
    """Shortcut to twisted deferLater.

    It allows to call twisted deferLater and add callback and errback methods.
    """
    delayms, fn = args[0], args[1]
    callback = None
    if 'cbk' in kargs:
        callback = kargs['cbk']
        del kargs['cbk']
    d = task.deferLater(reactor, delayms / const.SCALE, fn, *args[2:], **kargs)
    log.debug("[wfpad] - Defer call to %s after %sms delay."
              % (fn.__name__, delayms))
    if callback:
        d.addCallback(callback)

    def errbackCancel(f):
        if f.check(CancelledError):
            log.debug("[wfpad] A deferred was cancelled.")
        else:
            raise f.raiseException()

    d.addErrback(errbackCancel)
    return d


def cast_dictionary_to_type(d, t):
    return {t(k): v for k, v in d.iteritems()}


def bytes_after_total_padding(total_bytes, psize=1):
    """Return the total bytes transmitted after 'total' padding."""
    n2 = closest_power_of_two(total_bytes)
    return closest_multiple(n2, psize, ceil=False)


def bytes_after_payload_padding(data_bytes, total_bytes, psize=1):
    """Return the total bytes transmitted after 'payload' padding."""
    n2 = closest_power_of_two(data_bytes)
    m = closest_multiple(total_bytes, n2)
    return closest_multiple(m, psize, ceil=False)
