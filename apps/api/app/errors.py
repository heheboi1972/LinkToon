class ApplicationError(Exception):
    def __init__(self, message: str, code: str = "application_error", status: int = 400) -> None:
        self.message = message
        self.code = code
        self.status = status
        super().__init__(message)


class ProviderError(ApplicationError):
    def __init__(self, message: str = "AI provider is unavailable") -> None:
        super().__init__(message, "provider_error", 502)


class GenerationError(ApplicationError):
    def __init__(self, message: str) -> None:
        super().__init__(message, "generation_error", 422)


class StorageError(ApplicationError):
    def __init__(self, message: str = "Storage is temporarily unavailable") -> None:
        super().__init__(message, "storage_error", 502)
