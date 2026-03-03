from __future__ import annotations

from abc import ABC, abstractmethod

from PIL import Image

from shared.domain import ModelAnalysis, RunnerHealth, VideoVerificationJob


class ModelRunnerPort(ABC):
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def supports(self, *, video: bool, images: bool) -> bool: ...

    @abstractmethod
    def analyze(
        self,
        job: VideoVerificationJob,
        frame_images: list[Image.Image],
        ref_images: list[Image.Image],
    ) -> ModelAnalysis: ...

    @abstractmethod
    def healthcheck(self) -> RunnerHealth: ...
