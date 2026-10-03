import logging
import re
from collections.abc import Mapping
from typing import Any


class SensitiveDataFilter(logging.Filter):
    """Remove credentials and capability tokens from application log records."""

    _bearer = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
    _named = re.compile(
        r"(?i)\b(authorization|password|access[_-]?token|api[_-]?key|key|secret|"
        r"service[_-]?role[_-]?key)(\s*[:=]\s*)([^\s,;&]+)"
    )
    _query = re.compile(r"(?i)([?&](?:token|access_token|api_key|key|secret|signature)=)[^&\s]+")

    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = sorted((value for value in (secrets or []) if value), key=len, reverse=True)

    def redact(self, value: str) -> str:
        result = self._bearer.sub("Bearer <redacted>", value)
        result = self._named.sub(r"\1\2<redacted>", result)
        result = self._query.sub(r"\1<redacted>", result)
        for secret in self.secrets:
            result = result.replace(secret, "<redacted>")
        return result

    def sanitize(self, value: Any) -> Any:
        if isinstance(value, str):
            return self.redact(value)
        if isinstance(value, tuple):
            return tuple(self.sanitize(item) for item in value)
        if isinstance(value, list):
            return [self.sanitize(item) for item in value]
        if isinstance(value, Mapping):
            return {key: self.sanitize(item) for key, item in value.items()}
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        if (
            record.name == "uvicorn.access"
            and isinstance(record.args, tuple)
            and len(record.args) == 5
        ):
            arguments = list(record.args)
            arguments[2] = str(arguments[2]).split("?", 1)[0]
            record.msg = self.sanitize(record.msg)
            record.args = tuple(self.sanitize(arguments))
            return True
        try:
            rendered = record.getMessage()
        except (TypeError, ValueError):
            record.msg = self.sanitize(record.msg)
            record.args = self.sanitize(record.args)
        else:
            record.msg = self.redact(rendered)
            record.args = ()
        return True


RedactCapabilityQuery = SensitiveDataFilter
