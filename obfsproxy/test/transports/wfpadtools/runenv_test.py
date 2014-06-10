from os.path import join, exists
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

    def test_bin_obfsproxy(self):
        """Checks obfsproxy executable/link is found in bin.
        
        This is necessary to run tester.py. We assume unix dir structure
        as it also is assumed in tester.py. Since we want to use pyobfsproxy
        to run our transports still under development, we can create a symbolic
        link to obfsproxy's python version running the following command: 
        sudo ln -s ~/git/obfsproxy-wfpadtools/obfsproxy/pyobfsproxy.py /bin/obfsproxy
        """
        self.assertTrue(exists(join("/bin", "obfsproxy")))

if __name__ == "__main__":
    #import sys;sys.argv = ['', 'Test.testName']
    unittest.main()
