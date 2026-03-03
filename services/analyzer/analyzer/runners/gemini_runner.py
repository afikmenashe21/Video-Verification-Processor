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


class GeminiRunner(ModelRunnerPort):
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        timeout_s: int = _DEFAULT_TIMEOUT_S,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._timeout_s = timeout_s

    def name(self) -> str:
        return "gemini"

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

        parts: list[dict] = []
        for i, data_uri in enumerate(encoded_refs):
            mime_type, b64_data = _parse_data_uri(data_uri)
            parts.append({"text": f"[Reference Image {i + 1}]"})
            parts.append({"inline_data": {"mime_type": mime_type, "data": b64_data}})

        for i, data_uri in enumerate(encoded_frames):
            mime_type, b64_data = _parse_data_uri(data_uri)
            parts.append({"text": f"[Frame {i + 1}]"})
            parts.append({"inline_data": {"mime_type": mime_type, "data": b64_data}})

        parts.append({"text": prompt_text})

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "maxOutputTokens": 2048,
                "temperature": 0.0,
            },
        }

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}"
            f":generateContent?key={self._api_key}"
        )

        logger.info("gemini_request", model=self._model, frames=len(frame_images), refs=len(ref_images))

        with httpx.Client(timeout=self._timeout_s) as client:
            resp = client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()

        data = resp.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError(f"Gemini returned no candidates: {data}")

        raw_output = "".join(
            part["text"]
            for part in candidates[0].get("content", {}).get("parts", [])
            if "text" in part
        )

        logger.info("gemini_response", model=self._model, output_length=len(raw_output))
        return parse_model_output(raw_output)

    def healthcheck(self) -> RunnerHealth:
        if not self._api_key:
            return RunnerHealth(name=self.name(), healthy=False, detail="API key not configured")
        try:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}"
                f"?key={self._api_key}"
            )
            with httpx.Client(timeout=10) as client:
                resp = client.get(url)
                resp.raise_for_status()
            return RunnerHealth(name=self.name(), healthy=True)
        except Exception as e:
            return RunnerHealth(name=self.name(), healthy=False, detail=str(e))


def _parse_data_uri(data_uri: str) -> tuple[str, str]:
    """Extract mime_type and base64 data from a data URI."""
    header, b64_data = data_uri.split(",", 1)
    mime_type = header.split(":")[1].split(";")[0]
    return mime_type, b64_data
