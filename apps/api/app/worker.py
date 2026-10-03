import argparse
import logging
import os
import signal
import socket
from threading import Event

from app.config import get_settings
from app.db import session_factory
from app.job_worker import DatabaseWorker
from app.logging import SensitiveDataFilter
from app.providers.registry import configured_registry

logger = logging.getLogger(__name__)


def worker_identity(configured: str) -> str:
    return configured or f"{socket.gethostname()}-{os.getpid()}"


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    secret_filter = SensitiveDataFilter(
        [
            settings.local_auth_secret,
            settings.supabase_service_role_key,
            settings.openai_api_key,
            settings.fal_key,
            settings.runwayml_api_secret,
        ]
    )
    logging.getLogger("app").addFilter(secret_filter)
    logging.getLogger("openai").addFilter(secret_filter)
    logging.getLogger("httpx").addFilter(secret_filter)
    for handler in logging.getLogger().handlers:
        handler.addFilter(secret_filter)


def main() -> None:
    parser = argparse.ArgumentParser(description="LinkToon PostgreSQL generation worker")
    parser.add_argument("--once", action="store_true", help="Process one due job and exit")
    args = parser.parse_args()
    configure_logging()
    settings = get_settings()
    worker_id = worker_identity(settings.worker_id)
    sessions = session_factory()
    worker = DatabaseWorker(sessions, settings, configured_registry(settings), worker_id)
    stopped = Event()

    def stop(signum: int, frame: object) -> None:
        logger.info("worker=%s shutdown_signal=%s", worker_id, signum)
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    logger.info("worker=%s started=true", worker_id)
    try:
        if args.once:
            worker.run_once()
            return
        while not stopped.is_set():
            processed = worker.run_batch()
            if processed == 0:
                stopped.wait(settings.worker_poll_interval_seconds)
    finally:
        bind = sessions.kw.get("bind")
        if bind is not None:
            bind.dispose()
        logger.info("worker=%s stopped=true", worker_id)


if __name__ == "__main__":
    main()
