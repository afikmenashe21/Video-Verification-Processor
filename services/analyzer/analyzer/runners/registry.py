from __future__ import annotations

from typing import Callable

import structlog

from analyzer.runners.port import ModelRunnerPort

logger = structlog.get_logger()


class ModelRunnerRegistry:
    """Maps model name → runner factory. Lazy initialization on first use."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ModelRunnerPort]] = {}
        self._instances: dict[str, ModelRunnerPort] = {}

    def register(self, name: str, factory: Callable[[], ModelRunnerPort]) -> None:
        self._factories[name] = factory
        logger.info("model_runner_registered", model=name)

    def get(self, name: str) -> ModelRunnerPort:
        if name in self._instances:
            return self._instances[name]

        if name not in self._factories:
            raise KeyError(f"No runner registered for model: {name}")

        logger.info("model_runner_initializing", model=name)
        runner = self._factories[name]()
        self._instances[name] = runner
        return runner

    def available_models(self) -> set[str]:
        return set(self._factories.keys())
