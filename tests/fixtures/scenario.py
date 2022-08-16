from typing import Callable
from ConfigSpace import ConfigurationSpace
from smac import Scenario
import pytest


@pytest.fixture
def make_scenario() -> Callable:
    def _make(
        configspace: ConfigurationSpace,
        deterministic: bool = False,
        use_multi_objective: bool = False,
        use_instances: bool = False,
        n_instances: int = 3,
    ) -> Scenario:
        objectives = "cost"
        if use_multi_objective:
            objectives = ["cost1", "cost2"]

        instances = None
        instance_features = None
        if use_instances:
            instances = []
            instance_features = {}
            for i in range(n_instances):
                instance_name = f"i{i+1}"
                instances += [instance_name]
                instance_features[instance_name] = [j + i for j in range(3)]

        return Scenario(
            configspace=configspace,
            name="test",
            output_directory="smac3_output_test",
            objectives=objectives,
            deterministic=deterministic,
            walltime_limit=30,
            n_trials=100,
            instances=instances,
            instance_features=instance_features,
        )

    return _make