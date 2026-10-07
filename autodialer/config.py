"""Settings, read from environment variables (or a .env-style shell)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Settings:
    adb_serial: str | None = None          # which phone (adb devices); None = the only one
    adb_path: str = "adb"
    dialer_package: str | None = None      # e.g. com.google.android.dialer
    id_overrides: dict = field(default_factory=dict)
    api_token: str | None = None           # if set, requests need "Authorization: Bearer <token>"
    notify_on_phone: bool = True           # post a notification on the phone on mismatch/failure
    webhook_url: str | None = None         # default callback URL for results
    poll_url: str | None = None            # optional: GET this URL for new call requests
    poll_interval: float = 10.0
    min_seconds_between_calls: float = 5.0

    @classmethod
    def from_env(cls) -> "Settings":
        overrides = _env("AUTODIALER_ID_OVERRIDES")
        return cls(
            adb_serial=_env("AUTODIALER_ADB_SERIAL"),
            adb_path=_env("AUTODIALER_ADB_PATH", "adb"),
            dialer_package=_env("AUTODIALER_DIALER_PACKAGE"),
            id_overrides=json.loads(overrides) if overrides else {},
            api_token=_env("AUTODIALER_API_TOKEN"),
            notify_on_phone=_env("AUTODIALER_NOTIFY_ON_PHONE", "1") not in ("0", "false", "no"),
            webhook_url=_env("AUTODIALER_WEBHOOK_URL"),
            poll_url=_env("AUTODIALER_POLL_URL"),
            poll_interval=float(_env("AUTODIALER_POLL_INTERVAL", "10")),
            min_seconds_between_calls=float(_env("AUTODIALER_MIN_GAP", "5")),
        )
