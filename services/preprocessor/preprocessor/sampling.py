from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

import av
from PIL import Image

from shared.errors import VideoProcessingError


@dataclass(frozen=True)
class SampledFrame:
    image: Image.Image
    timestamp_s: float


class FrameSampler(ABC):
    @abstractmethod
    def sample(self, video_path: str, max_frames: int) -> list[SampledFrame]: ...


class UniformSampler(FrameSampler):
    """Extract N evenly-spaced frames from the video."""

    def __init__(self, target_frames: int = 32) -> None:
        self._target_frames = target_frames

    def sample(self, video_path: str, max_frames: int) -> list[SampledFrame]:
        effective_n = min(self._target_frames, max_frames)
        return _extract_uniform_frames(video_path, effective_n)


class FpsSampler(FrameSampler):
    """Extract frames at a fixed FPS rate."""

    def __init__(self, fps: float = 1.0) -> None:
        self._fps = fps

    def sample(self, video_path: str, max_frames: int) -> list[SampledFrame]:
        return _extract_fps_frames(video_path, self._fps, max_frames)


def _extract_uniform_frames(video_path: str, n: int) -> list[SampledFrame]:
    try:
        container = av.open(video_path)
    except Exception as e:
        raise VideoProcessingError(f"Failed to open video for sampling: {e}") from e

    try:
        stream = container.streams.video[0]
        stream.codec_context.skip_frame = "NONKEY"

        all_frames: list[tuple[float, av.VideoFrame]] = []
        for frame in container.decode(video=0):
            ts = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
            all_frames.append((ts, frame))

        if not all_frames:
            return []

        total = len(all_frames)
        if total <= n:
            indices = list(range(total))
        else:
            step = total / n
            indices = [int(i * step) for i in range(n)]

        frames: list[SampledFrame] = []
        for idx in indices:
            ts, vf = all_frames[idx]
            pil_img = vf.to_image().convert("RGB")
            frames.append(SampledFrame(image=pil_img, timestamp_s=ts))

        return frames
    finally:
        container.close()


def _extract_fps_frames(video_path: str, target_fps: float, max_frames: int) -> list[SampledFrame]:
    try:
        container = av.open(video_path)
    except Exception as e:
        raise VideoProcessingError(f"Failed to open video for sampling: {e}") from e

    try:
        stream = container.streams.video[0]
        interval_s = 1.0 / target_fps
        next_capture_s = 0.0
        frames: list[SampledFrame] = []

        for frame in container.decode(video=0):
            ts = float(frame.pts * stream.time_base) if frame.pts is not None else 0.0
            if ts >= next_capture_s:
                pil_img = frame.to_image().convert("RGB")
                frames.append(SampledFrame(image=pil_img, timestamp_s=ts))
                next_capture_s = ts + interval_s

                if len(frames) >= max_frames:
                    break

        return frames
    finally:
        container.close()
