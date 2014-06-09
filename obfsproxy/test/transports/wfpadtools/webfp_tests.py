from os.path import join, basename, exists
from subprocess import Popen
import unittest

import obfsproxy.common.log as logging
from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util as ut
import requesocks as requests


DEBUG = True
# Switch to leave Tor running and speed-up tests
LEAVE_TOR_RUNNING = True
LEAVE_TRANSPORT_RUNNING = True

# Logging settings:
log = logging.get_obfslogger()
DEFAULT_TOR_LOGLEVEL = 'err'
log.set_log_severity('info')
log.obfslogger.propagate = True
DEFAULT_TOR_LOG_QUIET = True

if DEBUG:
    DEFAULT_TOR_LOG_QUIET = False
    DEFAULT_TOR_LOGLEVEL = 'notice'
    log.set_log_severity('debug')
else:
    log.disable_logs()

TRANSPORT = "buflo"


class TransportTest(STTest):
    transport_ends = {}

    def setUp(self):
        try:
            for mode, port in const.TRANSPORT_MODES.iteritems():
                self.transport_ends[mode] = self.start_transport(mode, port)
        except Exception as exc:
            log.exception("TEST: Exception setting up the class {}: {}"
                          .format(self.__class__.__name__, exc))
            LEAVE_TOR_RUNNING = False
            self.tearDownClass()

    def tearDown(self):
        if LEAVE_TRANSPORT_RUNNING:
            return
        for mode, transport_end in self.transport_ends:
            self.terminate_process_and_log(transport_end,
                                       "TEST: killed {} transport {}"
                                       .format(TRANSPORT, mode))

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        try:
            for mode in const.TRANSPORT_MODES:
                pidfile = join(const.TEMP_DIR, "{}-{}.pid"
                               .format(mode, TRANSPORT))
                if exists(pidfile):
                    pid = int(ut.read_file(pidfile))
                    ut.terminate_process(pid)
                    log.debug("TEST: killed {} transport {}"
                                       .format(TRANSPORT, mode))
                    ut.removefile(pidfile)
        except Exception as exc:
            log.exception("Exception raised tearing down class {}: {}"
                          .format(cls.__name__, exc))

    def run_transport(self, transport, mode, dest, listen_port):
        logfile = join(const.TEMP_DIR, "{}-{}.log".format(mode, TRANSPORT))
        pidfile = join(const.TEMP_DIR, "{}-{}.pid".format(mode, TRANSPORT))
        pid = ut.read_file(pidfile)
        if ut.is_pid_running(pid):
            log.debug("TEST: transport {} is already running."
                      .format(mode))
            return int(pid)
        log.debug("TEST: Starting {} of transport {} listening at {}"
                  .format(mode, transport, listen_port))
        process = Popen(["python", const.PYOBFSPROXY_PATH,
                         "--log-file", logfile,
                         "--log-min-severity", "debug",
                         transport,
                         mode,
                         "--dest", "localhost:{}".format(dest),
                         "localhost:{}".format(listen_port)])
        ut.write_to_file(pidfile, str(process.pid))
        return process.pid

    def terminate_process_and_log(self, pid, msg=None):
        ut.terminate_process(pid)
        if msg:
            log.debug(msg)

    def start_transport(self, mode, transport_port):
        return self.run_transport(TRANSPORT,
                                    mode,
                                    const.ORPORT,
                                    transport_port)

    def get_page(self, url):
        session = requests.session()
        session.proxies = {'http': 'socks5://127.0.0.1:{}'
                           .format(const.SOCKSPORT),
                           'https': 'socks5://127.0.0.1:{}'
                           .format(const.SOCKSPORT)}
        return session.get(url)


class UnmanagedTorTest(TransportTest):
    tor_ends = {}

    def setUp(self):
        super(UnmanagedTorTest, self).setUp()
        try:
            self.tor_ends["router"] = self.start_tor_bridge(const.ORPORT,
                                                const.DATA_DIRS["router"])
            self.tor_ends["proxy"] = self.start_tor_proxy(const.SOCKSPORT,
                                                const.CTRANS_SOCKSPORT,
                                                const.STRANS_SOCKSPORT,
                                                const.DATA_DIRS["proxy"])
        except Exception as exc:
            log.exception("TEST: Exception setting up the class {}: {}"
                    .format(self.__class__.__name__, exc))
            LEAVE_TOR_RUNNING = False
            self.tearDown()

    def tearDown(self):
        try:
            super(UnmanagedTorTest, self).tearDown()
            if LEAVE_TOR_RUNNING:
                return
            for torend_name, torend in self.tor_ends:
                self.terminate_process_and_log(torend,
                                       "TEST: killed Tor {}."
                                            .format(torend_name))
        except Exception as exc:
            log.exception("TEST: Exception tearing down the class {}: {}"
                    .format(self.__class__.__name__, exc))

    @classmethod
    def setUpClass(cls):
        pass

    @classmethod
    def tearDownClass(cls):
        super(UnmanagedTorTest, cls).tearDownClass()
        try:
            for datadir in const.DATA_DIRS.itervalues():
                pidfile = join(datadir, "pid")
                if exists(pidfile):
                    pid = int(ut.read_file(pidfile))
                    ut.terminate_process(pid)
                    log.debug("TEST: killed Tor {}.".format(basename(datadir)))
                    ut.removedir(datadir)
        except Exception as exc:
            log.exception("Exception raised tearing down class {}: {}"
                          .format(cls.__name__, exc))

    def tor_log_watchdog(self, logfile):
        ut.log_watchdog(const.FINISH_BOOTSRAP_LOGLINE,
                        logfile,
                        const.TOR_WATCHDOG_WAIT_TIME,
                        const.WATCHDOG_TIMEOUT)

    def start_tor(self, datadir, args, stdout_loglevel=DEFAULT_TOR_LOGLEVEL,
                  quiet=DEFAULT_TOR_LOG_QUIET):
        tor_proc_name = basename(datadir)
        pid_file = join(datadir, "pid")
        pid = ut.read_file(pid_file)
        if ut.is_pid_running(pid):
            log.debug("TEST: {} process is already running."
                      .format(tor_proc_name))
            return int(pid)
        logfile = join(datadir, const.DEBUG_FNAME)
        ut.removedir(datadir)
        log.debug("TEST: Starting Tor {}". format(tor_proc_name))
        log_args = ["--DataDirectory", datadir,
                    "--Log", "debug file {}".format(logfile),
                    "--Log", "{} stdout".format(stdout_loglevel)]
        if quiet:
            log_args += ["--quiet"]
        process = Popen(["tor"] + args + log_args)
        try:
            self.tor_log_watchdog(logfile)
        except ut.TimeExceededError:
            self.tearDown()
            return
        ut.write_to_file(join(datadir, "pid"), str(process.pid))
        log.debug("TEST: Finished loading {}".format(tor_proc_name))
        return process.pid

    def start_tor_bridge(self, orport, datadir):
        return self.start_tor(datadir,
                              ["--BridgeRelay", "1",
                               "--Nickname", "{}Test"
                                    .format(TRANSPORT),
                               "--SOCKSPort", "auto",
                               "--ORPort", orport,
                               "--ControlPort", "auto",
                               "--ExitPolicy", "reject *:*",
                               "--AssumeReachable", "1",
                               "--PublishServerDescriptor", "0"])

    def start_tor_proxy(self, socksport, client_port, server_port, datadir):
        return self.start_tor(datadir,
                              ["--UseBridges", "1",
                               "--Bridge", "{} localhost:{}"
                                    .format(TRANSPORT, server_port),
                               "--ClientTransportPlugin",
                                    "{} socks5 localhost:{}"
                                    .format(TRANSPORT, client_port),
                               "--SOCKSPort", socksport])


class WFPadToolsTransportTest(UnmanagedTorTest):
    """Test protection offered by transport against Website Fingerprinting."""

    def test_unmanaged_tor_connection(self):
        resp = self.get_page("http://torcheck.xenobite.eu/")
        self.assertEqual(resp.status_code, 200,
                         "The status code (%s) is not OK."
                         % resp.status_code)
        self.failUnless(resp.text)  # make sure it has body
        self.assertIn("using Tor successfully to reach the web", resp.text,
                      "Tor-check does not detect Tor: %s"
                      % resp.text)

    def test_attacks(self):
        pass

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
