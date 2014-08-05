from os.path import join, basename, exists
from subprocess import Popen
import unittest

import obfsproxy.common.log as logging
from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util as ut
from obfsproxy.test import tester
from time import sleep

# Test config
WATCHDOG_TIMEOUT = 180
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
                                                const.DATA_DIRS["router"])
            # Run Onion proxy
            self.tor_endpoints["proxy"] = self.start_tor_proxy(
                                                    str(tester.SOCKS_PORT),
                                                    str(tester.ENTRY_PORT),
                                                    str(tester.SERVER_PORT),
                                                    const.DATA_DIRS["proxy"])
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
                        WATCHDOG_TIMEOUT,
                        delay=3)

    def terminate_process_and_log(self, pid, msg=None):
        ut.terminate_process(pid)
        if msg:
            log.debug(msg)

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
        cmd = ["tor"] + args + log_args
        log.debug("COMMAND: {}".format(" ".join(cmd)))
        process = Popen(cmd)
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
               "--Nickname", "{}Test".format(self.transport),
               "--SOCKSPort", "auto",
               "--ORPort", orport,
               "--ControlPort", "auto",
               "--AssumeReachable", "1",
               "--PublishServerDescriptor", "0"])

    def start_tor_proxy(self, socksport, client_port, server_port, datadir):
        return self.start_tor(datadir,
            ["--UseBridges", "1",
             "--Bridge", "{} localhost:{}".format(self.transport, server_port),
             "--ClientTransportPlugin", "{} socks5 localhost:{}"
                    .format(self.transport, client_port),
             "--SOCKSPort", socksport])

    def get_page(self, url, port=tester.SHIM_PORT):
        return ut.get_page(url, port=port)

    def test_tor(self):
        sleep(5)
        resp = self.get_page("http://torcheck.xenobite.eu/", self.entry_port)
        self.assertEqual(resp.status_code, 200,
                         "The status code (%s) is not OK."
                         % resp.status_code)
        self.failUnless(resp.text)  # make sure it has body
        self.assertIn("using Tor successfully to reach the web", resp.text,
                      "Tor-check does not detect Tor: %s"
                      % resp.text)


class WFPadToolsTransportTests():
    """Test protection offered by transport against Website Fingerprinting."""

    @unittest.skip("")
    def test_attacks(self):
        pass


@unittest.skip("")
class WFPadTorTest(UnmanagedTorTest, WFPadToolsTransportTests, STTest):
    transport = tester.DirectWFPad.transport
    client_args = list(tester.DirectWFPad.client_args)
    client_args[1] = "socks"
    client_args = tuple(client_args)
    server_args = tester.DirectWFPad.server_args
    entry_port = tester.SOCKS_PORT


class BuFLOTorTest(UnmanagedTorTest, WFPadToolsTransportTests, STTest):
    transport = tester.DirectBuFLO.transport
    client_args = list(tester.DirectBuFLO.client_args)
    client_args[1] = "socks"
    client_args = tuple(client_args)
    server_args = tester.DirectBuFLO.server_args
    entry_port = tester.SHIM_PORT


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
