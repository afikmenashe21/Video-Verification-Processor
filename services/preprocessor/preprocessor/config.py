from shared.config import BaseServiceConfig


class PreprocessorConfig(BaseServiceConfig):
    kafka_topic: str = "video.verification.requested.v1"
    kafka_group_id: str = "preprocessor-service"

    frames_base_dir: str = "/data/frames"
    frame_sampling_fps: float = 1.0
    frame_sampling_max_frames: int = 64
    max_video_seconds: int = 300
