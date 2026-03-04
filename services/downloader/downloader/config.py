from shared.config import BaseServiceConfig, DatabaseConfig


class DownloaderConfig(BaseServiceConfig, DatabaseConfig):
    kafka_topic: str = "video.download.ready.v1"
    kafka_group_id: str = "downloader-service"

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "videos"
    minio_secure: bool = False

    video_base_dir: str = "/data/videos"
    download_timeout_s: int = 120
