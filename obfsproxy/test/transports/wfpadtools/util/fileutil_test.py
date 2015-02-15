import unittest

# WFPadTools imports
from obfsproxy.transports.wfpadtools.util import fileutil as fu
from obfsproxy.transports.wfpadtools.util import testutil as tu


class FileUtilTest(tu.STTest):

    def test_removefile(self):
        non_existent_file = "/tmp/this_file_must_not_exist.test"
        self.should_not_raise("Removing a non-existent file should raise.",
                              fu.removefile, non_existent_file)


if __name__ == "__main__":
    unittest.main()
