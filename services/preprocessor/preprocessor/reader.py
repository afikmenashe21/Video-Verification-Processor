from __future__ import annotations

import av

from shared.domain import VideoMetadata
from shared.errors import VideoProcessingError


def read_video_metadata(video_path: str) -> VideoMetadata:
    try:
        container = av.open(video_path)
    except Exception as e:
        raise VideoProcessingError(f"Failed to open video: {video_path} — {e}") from e

    try:
        stream = container.streams.video[0]
        duration_s = float(container.duration / av.time_base) if container.duration else 0.0
        fps = float(stream.average_rate) if stream.average_rate else 24.0
        width = stream.codec_context.width
        height = stream.codec_context.height
        codec = stream.codec_context.name or "unknown"

        return VideoMetadata(
            duration_s=duration_s,
            fps=fps,
            width=width,
            height=height,
            codec=codec,
        )
    finally:
        container.close()
