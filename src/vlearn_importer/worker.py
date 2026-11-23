"""Systemd-managed bootstrap worker. Does not consume or ACK Queue messages."""

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
    while not stop_requested.wait(settings.heartbeat_seconds):
        logger.info("heartbeat: service healthy; queue consumer not yet enabled")
    logger.info("VLearn Import Worker stopped")
