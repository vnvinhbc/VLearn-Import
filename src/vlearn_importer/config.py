"""Small bootstrap settings module. No secrets are logged."""

import os
import re
from dataclasses import dataclass, field
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    mode: str = "idle"
    heartbeat_seconds: int = 60
    api_url: str = ""
    service_token: str = field(default="", repr=False)

    @classmethod
    def from_environment(cls) -> "Settings":
        mode = os.environ.get("WORKER_MODE", "idle").strip().lower()
        if mode not in {"idle", "api"}:
            raise ValueError("WORKER_MODE must be idle or api")
        raw_heartbeat = os.environ.get("HEARTBEAT_SECONDS", "60")
        try:
            heartbeat = int(raw_heartbeat)
        except ValueError as exc:
            raise ValueError("HEARTBEAT_SECONDS must be an integer") from exc
        if not 5 <= heartbeat <= 3600:
            raise ValueError("HEARTBEAT_SECONDS must be between 5 and 3600")
        if mode == "idle":
            return cls(mode=mode, heartbeat_seconds=heartbeat)

        api_url = os.environ.get("VLEARN_API_URL", "").strip()
        try:
            parsed = urlsplit(api_url)
            port = parsed.port
            valid_origin = (
                parsed.hostname
                and not parsed.username
                and parsed.password is None
                and not any(char in api_url for char in ("\\", "?", "#", "@"))
                and all("!" <= char <= "~" for char in api_url)
                and parsed.path in ("", "/")
                and (port is None or 1 <= port <= 65535)
                and (
                    parsed.scheme == "https"
                    or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
                )
            )
        except ValueError:
            valid_origin = False
        if not valid_origin:
            raise ValueError("VLEARN_API_URL must be an HTTPS origin or a local HTTP origin")

        service_token = os.environ.get("VLEARN_SERVICE_TOKEN", "")
        if not re.fullmatch(r"[!-~]{32,1024}", service_token):
            raise ValueError("VLEARN_SERVICE_TOKEN must be at least 32 printable non-space characters")
        return cls(mode, heartbeat, api_url.rstrip("/"), service_token)
