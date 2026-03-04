class ServiceError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class ValidationError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("VALIDATION_ERROR", message)


class ModelError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("MODEL_ERROR", message)


class StorageError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("STORAGE_ERROR", message)


class VideoProcessingError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("VIDEO_PROCESSING_ERROR", message)


class DownloadError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("DOWNLOAD_ERROR", message)


class ApifyError(ServiceError):
    def __init__(self, message: str) -> None:
        super().__init__("APIFY_ERROR", message)
