from __future__ import annotations

import httpx
import structlog
from PIL import Image

from shared.domain import ModelAnalysis, RunnerHealth, VideoVerificationJob
from analyzer.base import prepare_frames_and_refs
from analyzer.parsing import parse_model_output
from analyzer.prompts import build_prompt
from analyzer.runners.port import ModelRunnerPort

logger = structlog.get_logger()

_DEFAULT_TIMEOUT_S = 120


class OpenAIRunner(ModelRunnerPort):
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = "https://api.openai.com/v1",
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def name(self) -> str:
        return "openai"

    def supports(self, *, video: bool, images: bool) -> bool:
        return True

    def analyze(
        self,
        job: VideoVerificationJob,
        frame_images: list[Image.Image],
        ref_images: list[Image.Image],
    ) -> ModelAnalysis:
        prompt_text = build_prompt(job.query, len(ref_images))
        encoded_frames, encoded_refs = prepare_frames_and_refs(frame_images, ref_images)

        content: list[dict] = []
        for i, data_uri in enumerate(encoded_refs):
            content.append({"type": "text", "text": f"[Reference Image {i + 1}]"})
            content.append({"type": "image_url", "image_url": {"url": data_uri, "detail": "low"}})

        for i, data_uri in enumerate(encoded_frames):
            content.append({"type": "text", "text": f"[Frame {i + 1}]"})
            content.append({"type": "image_url", "image_url": {"url": data_uri, "detail": "low"}})

        content.append({"type": "text", "text": prompt_text})

        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 2048,
            "temperature": 0.0,
        }

        logger.info("openai_request", model=self._model, frames=len(frame_images), refs=len(ref_images))

        with httpx.Client(timeout=self._timeout_s) as client:
            resp = client.post(
                f"{self._base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        raw_output = data["choices"][0]["message"]["content"]

        logger.info("openai_response", model=self._model, output_length=len(raw_output))
        return parse_model_output(raw_output)

    def healthcheck(self) -> RunnerHealth:
        if not self._api_key:
            return RunnerHealth(name=self.name(), healthy=False, detail="API key not configured")
        try:
            with httpx.Client(timeout=10) as client:
                resp = client.get(
                    f"{self._base_url}/models",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                )
                resp.raise_for_status()
            return RunnerHealth(name=self.name(), healthy=True)
        except Exception as e:
            return RunnerHealth(name=self.name(), healthy=False, detail=str(e))
