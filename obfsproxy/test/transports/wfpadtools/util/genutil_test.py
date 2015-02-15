import unittest
from os.path import join

# WFPadTools imports
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util.genutil as gu
import obfsproxy.transports.wfpadtools.util.fileutil as fu
from obfsproxy.transports.wfpadtools.util.testutil import STTest


class GeneralUtilTest(STTest):
    """Test the wfpad.util module."""

    def test_log_watchdog(self):
        testfile = join(const.TEMP_DIR, "testfile")
        testline = "test line"
        fu.write_to_file(testfile, "line1\n" + testline + "\nline3")
        self.should_raise("Watchdog did not raised expected exception.",
                          gu.log_watchdog, "not test line", testfile, 1, 1)
        self.should_not_raise("Watchdog raised unexpected exception.",
                              gu.log_watchdog, testline, testfile, 5, 1)


if __name__ == "__main__":
    unittest.main()
