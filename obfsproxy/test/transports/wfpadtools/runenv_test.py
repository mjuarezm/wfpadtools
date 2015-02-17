import os
import unittest

# WFPadTools imports
from obfsproxy.transports.wfpadtools.util.testutil import STTest
from obfsproxy.transports.wfpadtools import const


class RunEnvTest(STTest):
    """Tests whether the extra dependency requirements are satisfied.

    Eventually, these requirements could be added to obfsproxy/setup.py
    """

    def test_pythonpath_bashrc(self):
        """Test base dir is loaded in the PYTHONPATH."""
        self.assertTrue(const.BASE_DIR in os.environ['PYTHONPATH'],
                        msg="The base dir is not loaded in the PYTHONPATH. "
                        "You can solve this problem by running:\n"
                        "echo \'export PYTHONPATH=$PYTHONPATH:{}\' >> "
                        "~/.bashrc && source ~/.bashrc;"
                        .format(const.BASE_DIR))

    def test_numpy(self):
        self.assert_package_is_installed('numpy')

    def test_tor(self):
        self.assert_is_installed('tor')

    def test_pyptlib(self):
        self.assert_package_is_installed('pyptlib')

    def test_requesocks(self):
        self.assert_package_is_installed('requesocks')

    def test_psutil(self):
        self.assert_package_is_installed('psutil')


if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
