import os
from os.path import join, exists
import unittest

from obfsproxy.test.transports.wfpadtools.sttest import STTest
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

    def test_tor(self):
        self.assert_is_installed('tor')

    def test_pyptlib(self):
        self.assert_package_is_installed('pyptlib')

    def test_requesocks(self):
        self.assert_package_is_installed('requesocks')

    def test_psutil(self):
        self.assert_package_is_installed('psutil')

    def test_bin_obfsproxy(self):
        """Checks obfsproxy executable/link is found in bin.

        This is necessary to run tester.py. We assume unix dir structure
        as it also is assumed in tester.py. Since we want to use pyobfsproxy
        to run our transports still under development, we can create a symbolic
        link to obfsproxy's python version running the following command:
        """
        self.assertTrue(exists(join("/bin", "obfsproxy")),
                        msg="The symbolic link to pyobfsproxy does not work."
                            "Create one by running: sudo ln -s {} {}"
                            .format(const.PYOBFSPROXY_PATH,
                                    "/bin/obfsproxy"))

if __name__ == "__main__":
    # import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
