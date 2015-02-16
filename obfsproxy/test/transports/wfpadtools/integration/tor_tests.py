import psutil
import unittest
from time import sleep
from subprocess import Popen
from os.path import join, basename, exists


# WFPadTools imports
from obfsproxy.test import tester
import obfsproxy.common.log as logging
from obfsproxy.transports.wfpadtools import const
from obfsproxy.transports.wfpadtools.util import genutil as gu
from obfsproxy.transports.wfpadtools.util import fileutil as fu
from obfsproxy.transports.wfpadtools.util import netutil as nu
from obfsproxy.transports.wfpadtools.util.testutil import STTest
import obfsproxy.test.transports.wfpadtools.wfpad_tester as wft


# TEST CONFIGURATION
DEBUG_FNAME      = "debug.log"
ORPORT           = "65535"
DATA_DIRS        = {
                    "proxy": join(const.TEMP_DIR, "proxy"),
                    "router": join(const.TEMP_DIR, "router")
                   }
BOOTSRAP_LOGLINE = "Bootstrapped 100%: Done"
WATCHDOG_TIMEOUT = 180
GET_PAGE_TIMEOUT = 30

# Severity
DEBUG = True

# Switch to leave Tor running and speed-up tests
LEAVE_TOR_RUNNING = False

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


class UnmanagedTorTest(tester.TransportsSetUp):
    tor_endpoints = {}

    def setUp(self):
        # Run transport client and server
        super(UnmanagedTorTest, self).setUp()
        try:
            # Run Tor bridge
            self.tor_endpoints["router"] = self.start_tor_bridge(
                                                str(tester.EXIT_PORT),
                                                DATA_DIRS["router"])
            # Run Onion proxy
            self.tor_endpoints["proxy"] = self.start_tor_proxy(
                                                    str(wft.SOCKS_PORT),
                                                    str(tester.ENTRY_PORT),
                                                    str(tester.SERVER_PORT),
                                                    DATA_DIRS["proxy"])
        except Exception as exc:
            log.exception("TEST: Exception setting up the class {}: {}"
                    .format(self.__class__.__name__, exc))
            LEAVE_TOR_RUNNING = False
            self.tearDown()

    def tearDown(self):
        try:
            # Close transports ports
            super(UnmanagedTorTest, self).tearDown()
            if LEAVE_TOR_RUNNING:
                return
            for torend_name, torend in self.tor_endpoints.iteritems():
                self.terminate_process_and_log(torend,
                                       "TEST: killed Tor {}."
                                            .format(torend_name))
        except Exception as exc:
            log.exception("TEST: Exception tearing down the class {}: {}"
                    .format(self.__class__.__name__, exc))

    @classmethod
    def tearDownClass(cls):
        super(UnmanagedTorTest, cls).tearDownClass()
        try:
            for datadir in DATA_DIRS.itervalues():
                pidfile = join(datadir, "pid")
                if exists(pidfile):
                    pid = int(fu.read_file(pidfile))
                    fu.terminate_process(pid)
                    log.debug("TEST: killed Tor {}.".format(basename(datadir)))
                    fu.removedir(datadir)
        except Exception as exc:
            log.exception("Exception raised tearing down class {}: {}"
                          .format(cls.__name__, exc))

    def tor_log_watchdog(self, logfile, line=BOOTSRAP_LOGLINE):
        gu.log_watchdog(line, logfile, WATCHDOG_TIMEOUT, delay=3)

    def terminate_process_and_log(self, pid, msg=None):
        fu.terminate_process(pid)
        if msg:
            log.debug(msg)

    def start_tor(self, datadir, args, stdout_loglevel=DEFAULT_TOR_LOGLEVEL,
                  quiet=DEFAULT_TOR_LOG_QUIET):
        tor_proc_name = basename(datadir)
        pid_file = join(datadir, "pid")
        pid = fu.read_file(pid_file)
        if fu.is_pid_running(pid):
            log.debug("TEST: {} process is already running."
                      .format(tor_proc_name))
            return int(pid)
        logfile = join(datadir, DEBUG_FNAME)
        fu.removedir(datadir)
        log.debug("TEST: Starting Tor {}". format(tor_proc_name))
        log_args = ["--DataDirectory", datadir,
                    "--Log", "debug file {}".format(logfile),
                    "--Log", "{} stdout".format(stdout_loglevel)]
        if quiet:
            log_args += ["--quiet"]
        cmd = ["tor"] + args + log_args
        log.debug("COMMAND: {}".format(" ".join(cmd)))
        process = Popen(cmd)
        try:
            self.tor_log_watchdog(logfile)
        except gu.TimeExceededError:
            log.error("Attempt to run tor process has timedout!")
            self.tearDown()
            return
        fu.write_to_file(join(datadir, "pid"), str(process.pid))
        log.debug("TEST: Finished loading {}".format(tor_proc_name))
        return process.pid

    def start_tor_bridge(self, orport, datadir):
        return self.start_tor(datadir,
              ["--BridgeRelay", "1",
               "--Nickname", "{}Test".format(self.transport),
               "--SOCKSPort", "auto",
               "--ORPort", orport,
               "--ControlPort", "auto",
               "--AssumeReachable", "1",
               "--PublishServerDescriptor", "0"])

    def start_tor_proxy(self, socksport, client_port, server_port, datadir):
        return self.start_tor(datadir,
            ["--UseBridges", "1",
             "--Bridge", "{} 127.0.0.1:{}".format(self.transport, server_port),
             "--ClientTransportPlugin", "{} socks5 localhost:{}"
                    .format(self.transport, client_port),
             "--SOCKSPort", socksport])

    def get_page(self, url, port=wft.SHIM_PORT):
        return nu.get_page(url, port=port, timeout=GET_PAGE_TIMEOUT)

    def test_tor(self):
        sleep(5)
        resp = self.get_page("http://torcheck.xenobite.eu/", self.entry_port)
        self.assertEqual(resp.status_code, 200,
                         "The status code (%s) is not OK."
                         % resp.status_code)
        self.failUnless(resp.text)  # make sure it has a body
        self.assertIn("using Tor successfully to reach the web", resp.text,
                      "Tor-check does not detect Tor: %s"
                      % resp.text)


class WFPadToolsTransportTests():
    """Test protection offered by transport against Website Fingerprinting."""

    @unittest.skip("Not implemented yet.")
    def test_attacks(self):
        # TODO: as future work, one could implement existing attacks and
        # deploy them in this test.
        pass


class TestWFPadTor(wft.WFPadShimSocksConfig, UnmanagedTorTest,
                   WFPadToolsTransportTests, STTest):
    pass


class TesBuFLOTor(wft.BuFLOShimSocksConfig, UnmanagedTorTest,
                  WFPadToolsTransportTests, STTest):
    pass


def clean_test_setting():
    """Clean folders and processes."""
    processes = ["tor", "obfsproxy"]
    log.info("Cleaning test setting...")
    for proc in psutil.process_iter():
        if proc.name() in processes:
            proc.kill()
            log.info(proc.name() + " killed!")
    for dirpath in DATA_DIRS.itervalues():
        log.debug("Will remove old log directory: " + dirpath)
        fu.removedir(dirpath)
    obfs_log_prefix = "obfsproxy_tester_"
    for end in ["client", "server"]:
        dirpath = join(const.TEMP_DIR, obfs_log_prefix + end + ".log")
        log.debug("Will remove old obfsproxy log file: " + dirpath)
        fu.removefile(dirpath)

clean_test_setting()

if __name__ == "__main__":
    unittest.main()
