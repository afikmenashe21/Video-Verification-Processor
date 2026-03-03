from shared.config import BaseServiceConfig


class AnalyzerConfig(BaseServiceConfig):
    kafka_topic: str = "video.frames.extracted.v1"
    kafka_group_id: str = "analyzer-service"

    model_default: str = "gemini"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    openai_base_url: str = "https://api.openai.com/v1"

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
