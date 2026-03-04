from shared.config import DatabaseConfig


class SubmitterConfig(DatabaseConfig):
    http_port: int = 8000
    apify_api_token: str = ""
    apify_actor_id: str = ""
    webhook_base_url: str = "http://gateway:8001"
    match_target: int = 3
