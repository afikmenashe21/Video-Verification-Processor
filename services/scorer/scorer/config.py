from shared.config import BaseServiceConfig


class ScorerConfig(BaseServiceConfig):
    kafka_topic: str = "video.analysis.completed.v1"
    kafka_group_id: str = "scorer-service"

    output_dir: str = "/data/output"
