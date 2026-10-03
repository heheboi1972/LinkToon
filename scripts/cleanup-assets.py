"""Dry-run by default. Remove orphaned objects in a dedicated LinkToon bucket/root."""

import argparse
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import httpx
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))

from app.config import get_settings
from app.db import session_factory
from app.models import Asset
from app.storage import LocalStorage, SupabaseStorage, storage_for


def valid_key(key: str) -> bool:
    parts = key.split("/")
    try:
        if len(parts) == 3:
            for part in parts:
                UUID(part)
            return True
        if (
            len(parts) == 6
            and parts[0] == "users"
            and parts[2] == "projects"
            and parts[4] == "generated"
        ):
            UUID(parts[1])
            UUID(parts[3])
            filename = Path(parts[5])
            UUID(filename.stem)
            return filename.suffix.lower() in {".png", ".jpg", ".webp"}
        return False
    except ValueError:
        return False


def list_objects() -> list[tuple[str, datetime]]:
    storage = storage_for(get_settings())
    result: list[tuple[str, datetime]] = []
    if isinstance(storage, LocalStorage):
        for path in storage.root.rglob("*"):
            if path.is_file():
                result.append(
                    (
                        path.relative_to(storage.root).as_posix(),
                        datetime.fromtimestamp(path.stat().st_mtime, UTC),
                    )
                )
    elif isinstance(storage, SupabaseStorage):
        prefixes = [""]
        while prefixes:
            prefix = prefixes.pop()
            offset = 0
            while True:
                response = httpx.post(
                    f"{storage.base}/list/{storage.bucket}",
                    headers=storage.headers,
                    json={
                        "prefix": prefix,
                        "limit": 100,
                        "offset": offset,
                        "sortBy": {"column": "name", "order": "asc"},
                    },
                    timeout=30,
                )
                response.raise_for_status()
                rows = response.json()
                for row in rows:
                    key = f"{prefix}/{row['name']}".lstrip("/")
                    if row.get("id") is None:
                        prefixes.append(key)
                    elif row.get("updated_at"):
                        result.append(
                            (
                                key,
                                datetime.fromisoformat(row["updated_at"].replace("Z", "+00:00")),
                            )
                        )
                if len(rows) < 100:
                    break
                offset += 100
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Delete listed orphan objects")
    parser.add_argument("--older-than-hours", type=int, default=24)
    args = parser.parse_args()
    if args.older_than_hours < 1:
        parser.error("Grace period must be at least one hour")
    settings = get_settings()
    factory = session_factory()
    storage = storage_for(settings)
    cutoff = datetime.now(UTC) - timedelta(hours=args.older_than_hours)
    with factory() as db:
        live_keys = set(db.scalars(select(Asset.storage_key)))
        for key, modified in list_objects():
            if not valid_key(key) or key in live_keys or modified >= cutoff:
                continue
            # Recheck immediately before deleting in case another process registered the object.
            if db.scalar(select(Asset.id).where(Asset.storage_key == key)):
                continue
            print(("DELETE " if args.apply else "WOULD DELETE ") + key)
            if args.apply:
                storage.delete(key)
    factory.kw["bind"].dispose()


if __name__ == "__main__":
    main()
