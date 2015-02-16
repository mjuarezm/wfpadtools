import unittest

# WFPadTools imports
from obfsproxy.transports.wfpadtools.util import dumputil as du
from obfsproxy.transports.wfpadtools.util import fileutil as fu
from obfsproxy.transports.wfpadtools.util import testutil as test_ut


class TestUtilTest(test_ut.STTest):
    """Test the wfpad.test_util module."""

    def test_instrument_dump(self):
        enable_test_value = False
        dump_path_value = "/tmp/test.dump"
        return_value = [1, 2, 3]

        class A(object):
            enable_test = enable_test_value
            dump_path = dump_path_value

            def __init__(self):
                self.state = 1

            @test_ut.instrument_dump
            def meth_test(self):
                return return_value

        a = A()
        a.meth_test()
        self.should_raise("There was a dump file found in %s. "
                          "It might be leftover from previous test."
                          % dump_path_value, du.pick_load, dump_path_value)

        A.enable_test = True
        a.meth_test()
        dump = du.pick_load(dump_path_value)
        values = [v for v in dump.itervalues()]

        obs_value = values[0][1]
        exp_return = return_value
        self.assertEqual(obs_value, exp_return,
                         "Return values do not match: %s != %s"
                         % (obs_value, exp_return))
        fu.removefile(dump_path_value)

    def test_find_attr(self):
        class A(object):
            pass

        class B(A):
            attr = 2

        class C(B):
            pass

        self.assertTrue(test_ut.find_attr('attr', C),
                        "Attribute %s was not found in ancestors of %s"
                        % ('attr', C.__name__))
        self.assertFalse(test_ut.find_attr('foo', C),
                         "Attribute %s was found in ancestors of %s"
                         % ('attr', C.__name__))


if __name__ == "__main__":
    unittest.main()
