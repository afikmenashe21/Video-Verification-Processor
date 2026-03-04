from shared.config import BaseServiceConfig, DatabaseConfig


class GatewayConfig(BaseServiceConfig, DatabaseConfig):
    http_port: int = 8001
    apify_api_token: str = ""
