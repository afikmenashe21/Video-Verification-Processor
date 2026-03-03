import pytest

from analyzer.runners.registry import ModelRunnerRegistry
from analyzer.runners.mock_runner import MockRunner


def test_shouldReturnRequestedModel_whenAvailable():
    registry = ModelRunnerRegistry()
    registry.register("mock", MockRunner)
    runner = registry.get("mock")
    assert runner.name() == "mock"


def test_shouldRaise_whenModelNotRegistered():
    registry = ModelRunnerRegistry()
    with pytest.raises(KeyError, match="No runner registered"):
        registry.get("nonexistent")


def test_shouldListAvailableModels():
    registry = ModelRunnerRegistry()
    registry.register("mock", MockRunner)
    registry.register("openai", lambda: None)
    assert registry.available_models() == {"mock", "openai"}
