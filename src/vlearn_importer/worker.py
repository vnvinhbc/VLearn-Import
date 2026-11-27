"""Systemd-managed importer entrypoint."""

import logging
import signal
import threading

from vlearn_importer.config import Settings

logger = logging.getLogger(__name__)
stop_requested = threading.Event()


def _stop(signum: int, _frame: object) -> None:
    logger.info("Received signal %s; stopping gracefully", signum)
    stop_requested.set()


def run_worker(settings: Settings) -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("VLearn Import Worker started (mode=%s)", settings.mode)
    if settings.mode == "api":
        from vlearn_importer.api_worker import ApiClient, process_job

        client = ApiClient(settings)
        while not stop_requested.is_set():
            if not process_job(client, stop_requested):
                stop_requested.wait(settings.heartbeat_seconds)
    else:
        while not stop_requested.wait(settings.heartbeat_seconds):
            logger.info("heartbeat: idle service healthy")
    logger.info("VLearn Import Worker stopped")
