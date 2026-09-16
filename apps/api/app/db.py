from collections.abc import Generator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite") and ":memory:" not in url:
        filename = url.split("///", 1)[-1]
        Path(filename).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False} if url.startswith("sqlite") else {},
    )
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def set_sqlite_pragma(connection: Any, record: Any) -> None:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")

    return engine


def session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=make_engine(get_settings().database_url), expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    from app.main import app

    with app.state.session_factory() as session:
        try:
            yield session
        except Exception:
            session.rollback()
            raise
