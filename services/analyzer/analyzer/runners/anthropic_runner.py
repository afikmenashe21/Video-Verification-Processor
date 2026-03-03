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
_API_VERSION = "2023-06-01"


class AnthropicRunner(ModelRunnerPort):
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str = "https://api.anthropic.com",
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout_s = timeout_s

    def name(self) -> str:
        return "anthropic"

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
            media_type, b64_data = _parse_data_uri(data_uri)
            content.append({"type": "text", "text": f"[Reference Image {i + 1}]"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64_data},
            })

        for i, data_uri in enumerate(encoded_frames):
            media_type, b64_data = _parse_data_uri(data_uri)
            content.append({"type": "text", "text": f"[Frame {i + 1}]"})
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": media_type, "data": b64_data},
            })

        content.append({"type": "text", "text": prompt_text})

        payload = {
            "model": self._model,
            "max_tokens": 2048,
            "messages": [{"role": "user", "content": content}],
        }

        logger.info("anthropic_request", model=self._model, frames=len(frame_images), refs=len(ref_images))

        with httpx.Client(timeout=self._timeout_s) as client:
            resp = client.post(
                f"{self._base_url}/v1/messages",
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": _API_VERSION,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        raw_output = "".join(
            block["text"] for block in data["content"] if block["type"] == "text"
        )

        logger.info("anthropic_response", model=self._model, output_length=len(raw_output))
        return parse_model_output(raw_output)

    def healthcheck(self) -> RunnerHealth:
        if not self._api_key:
            return RunnerHealth(name=self.name(), healthy=False, detail="API key not configured")
        return RunnerHealth(name=self.name(), healthy=True, detail="API key configured")


def _parse_data_uri(data_uri: str) -> tuple[str, str]:
    """Extract media_type and base64 data from a data URI."""
    header, b64_data = data_uri.split(",", 1)
    media_type = header.split(":")[1].split(";")[0]
    return media_type, b64_data
