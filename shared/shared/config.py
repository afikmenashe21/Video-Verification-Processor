from pydantic_settings import BaseSettings


class BaseServiceConfig(BaseSettings):
    model_config = {"env_prefix": "", "case_sensitive": False}

    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_group_id: str = "video-verification-service"
    kafka_auto_offset_reset: str = "earliest"
    dlq_max_retries: int = 3
