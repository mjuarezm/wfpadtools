from os import access, getcwd, X_OK
from os.path import join, isfile
import unittest

import obfsproxy.transports.wfpadtools.util as ut


class STTest(unittest.TestCase):
    """Provides methods useful for testing."""

    def should_not_raise(self, msg, fn, *xargs, **kwargs):
        """Check that function does not raise."""
        try:
            fn(*xargs, **kwargs)
        except:
            self.fail(msg)
        else:
            pass

    def should_raise(self, msg, fn, *xargs, **kwargs):
        """Ensure that function raises with given args."""
        try:
            fn(*xargs, **kwargs)
        except:
            pass
        else:
            self.fail(msg)

    def assert_is_installed(self, pkg):
        """Ensure the program is installed."""
        self.failUnless(ut.is_installed(pkg),
                        'Cannot find %s in your system' % pkg)

    def assert_package_is_installed(self, pkg):
        """Ensure the python package is installed."""
        try:
            __import__(pkg)
        except ImportError:
            self.fail("Cannot find python package %s in your system" % pkg)

    def assert_is_file(self, filename, msg):
        """Check if file exist."""
        self.assertTrue(isfile(filename), msg)

    def assert_is_executable(self, binary):
        if not isfile(binary):
            self.fail('Cannot find %s' % binary)
        if not access(binary, X_OK):
            self.fail('Don\'t have execution permission for %s' % binary)

    def new_temp_file(self, filename):
        """Add file to remove-list."""
        self.files_to_remove.append(filename)
        return filename

    def abs_test_file_name(self, filename):
        """Return full path for file."""
        base = getcwd()
        return join(base, filename)
