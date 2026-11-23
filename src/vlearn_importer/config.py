"""Small bootstrap settings module. No secrets are logged."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    mode: str = "idle"
    heartbeat_seconds: int = 60

    @classmethod
    def from_environment(cls) -> "Settings":
        mode = os.environ.get("WORKER_MODE", "idle").strip().lower()
        if mode != "idle":
            raise ValueError(
                "Only WORKER_MODE=idle is implemented in this bootstrap. "
                "Connect Queue/R2/Main API and add durable ACK handling before enabling imports."
            )
        raw_heartbeat = os.environ.get("HEARTBEAT_SECONDS", "60")
        try:
            heartbeat = int(raw_heartbeat)
        except ValueError as exc:
            raise ValueError("HEARTBEAT_SECONDS must be an integer") from exc
        if not 5 <= heartbeat <= 3600:
            raise ValueError("HEARTBEAT_SECONDS must be between 5 and 3600")
        return cls(mode=mode, heartbeat_seconds=heartbeat)
