from os.path import join
import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest
from obfsproxy.transports.wfpadtools import const
import obfsproxy.transports.wfpadtools.util as ut


class UtilTest(STTest):
    """Test the wfpad.util module."""

    def test_log_watchdog(self):
        testfile = join(const.TEMP_DIR, "testfile")
        testline = "test line"
        ut.write_to_file(testfile, "line1\n" + testline + "\nline3")
        self.should_raise("Watchdog did not raised expected exception.",
                              ut.log_watchdog, "not test line", testfile, 1, 1)
        self.should_not_raise("Watchdog raised unexpected exception.",
                              ut.log_watchdog, testline, testfile, 5, 1)


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
