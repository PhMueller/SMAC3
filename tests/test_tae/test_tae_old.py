import os
import shlex
import unittest

from smac.configspace import ConfigurationSpace
from smac.scenario.scenario import Scenario
from smac.stats.stats import Stats
from smac.tae import StatusType
from smac.tae.execute_ta_run_old import ExecuteTARunOld

__copyright__ = "Copyright 2021, AutoML.org Freiburg-Hannover"
__license__ = "3-clause BSD"


class TaeOldTest(unittest.TestCase):
    def setUp(self):
        self.current_dir = os.getcwd()
        base_dir = os.path.split(__file__)[0]
        base_dir = os.path.join(base_dir, "../../tests", "..")
        os.chdir(base_dir)

    def tearDown(self):
        os.chdir(self.current_dir)

    def test_run(self):
        """
        running some simple algo in old style
        """
        scen = Scenario(
            scenario={"cs": ConfigurationSpace(), "run_obj": "quality", "output_dir": ""},
            cmd_options=None,
        )
        stats = Stats(scen)

        eta = ExecuteTARunOld(ta=shlex.split("python tests/test_tae/dummy_ta_wrapper.py 1"), stats=stats)
        status, cost, runtime, ar_info = eta.run(config={})
        assert status == StatusType.SUCCESS
        assert cost == 1.0
        assert runtime == 1.0

        print(status, cost, runtime)

        eta = ExecuteTARunOld(ta=shlex.split("python tests/test_tae/dummy_ta_wrapper.py 2"), stats=stats)
        status, cost, runtime, ar_info = eta.run(config={})
        assert status == StatusType.SUCCESS
        assert cost == 2.0
        assert runtime == 2.0

        print(status, cost, runtime)

        eta = ExecuteTARunOld(
            ta=shlex.split("python tests/test_tae/dummy_ta_wrapper.py 2"),
            stats=stats,
            run_obj="quality",
        )
        status, cost, runtime, ar_info = eta.run(
            config={},
        )
        assert status == StatusType.SUCCESS
        assert cost == 4.0
        assert runtime == 2.0

        print(status, cost, runtime, ar_info)

    def test_status(self):

        scen = Scenario(
            scenario={"cs": ConfigurationSpace(), "run_obj": "quality", "output_dir": ""},
            cmd_options=None,
        )
        stats = Stats(scen)

        eta = ExecuteTARunOld(ta=shlex.split(""), stats=stats)

        def test_success(**kwargs):
            return "Result of this algorithm run: SUCCESS,1,1,1,12354", ""

        eta._call_ta = test_success
        status, cost, runtime, ar_info = eta.run(
            config={},
        )
        self.assertEqual(status, StatusType.SUCCESS)

        def test_success(**kwargs):
            return "Result of this algorithm run: SUCESS,1,1,1,12354", ""

        eta._call_ta = test_success
        status, cost, runtime, ar_info = eta.run(
            config={},
        )
        self.assertEqual(status, StatusType.CRASHED)

        def test_success(**kwargs):
            return "Result of this algorithm run: success,1,1,1,12354", ""

        eta._call_ta = test_success
        status, cost, runtime, ar_info = eta.run(
            config={},
        )
        self.assertEqual(status, StatusType.SUCCESS)


if __name__ == "__main__":
    unittest.main()
