from pathlib import Path
from typing import Protocol
from urllib.parse import quote

import httpx

from app.config import Settings
from app.errors import StorageError


class Storage(Protocol):
    def put(self, key: str, content: bytes, mime_type: str) -> None: ...
    def read(self, key: str) -> bytes: ...
    def delete(self, key: str) -> None: ...


class LocalStorage:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root) or path == self.root:
            raise StorageError("Invalid storage key")
        return path

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        try:
            path = self.path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(content)
        except OSError as exc:
            raise StorageError() from exc

    def read(self, key: str) -> bytes:
        try:
            return self.path(key).read_bytes()
        except OSError as exc:
            raise StorageError() from exc

    def delete(self, key: str) -> None:
        try:
            self.path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError() from exc


class SupabaseStorage:
    def __init__(self, settings: Settings) -> None:
        self.base = f"{settings.supabase_url.rstrip('/')}/storage/v1/object"
        self.bucket = settings.supabase_storage_bucket
        self.headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }

    def url(self, key: str) -> str:
        return f"{self.base}/{quote(self.bucket, safe='')}/{quote(key, safe='/')}"

    def put(self, key: str, content: bytes, mime_type: str) -> None:
        try:
            response = httpx.post(
                self.url(key),
                content=content,
                headers={**self.headers, "Content-Type": mime_type, "x-upsert": "false"},
                timeout=60,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError() from exc

    def read(self, key: str) -> bytes:
        try:
            response = httpx.get(self.url(key), headers=self.headers, timeout=30)
            response.raise_for_status()
            return response.content
        except httpx.HTTPError as exc:
            raise StorageError() from exc

    def delete(self, key: str) -> None:
        try:
            response = httpx.delete(self.url(key), headers=self.headers, timeout=30)
            if response.status_code != 404:
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise StorageError() from exc


def storage_for(settings: Settings) -> Storage:
    if settings.storage_provider == "supabase":
        return SupabaseStorage(settings)
    return LocalStorage(settings.local_storage_path)
