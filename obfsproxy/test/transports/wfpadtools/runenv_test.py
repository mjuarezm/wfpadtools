import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest


class RunEnvTest(STTest):
    """Makes sure the extra dependency requirements are satisfied."""

    def test_tor(self):
        self.assert_is_installed('tor')

    def test_pyptlib(self):
        self.assert_package_is_installed('pyptlib')

    def test_requesocks(self):
        self.assert_package_is_installed('requesocks')


if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
