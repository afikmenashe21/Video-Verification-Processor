from shared.config import BaseServiceConfig, DatabaseConfig


class CompletionHandlerConfig(BaseServiceConfig, DatabaseConfig):
    kafka_topic: str = "video.verification.completed.v1"
    kafka_group_id: str = "completion-handler-service"
