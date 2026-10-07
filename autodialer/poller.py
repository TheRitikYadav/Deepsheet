"""Optional: pull call requests from your own API instead of having it push them.

``AUTODIALER_POLL_URL`` must return either a single request object, a list of
them, or ``{"calls": [...]}``. Each object needs ``phone_number`` and may
carry ``name``, ``reference``, ``info`` and ``callback_url``. Requests with a
``reference`` that was already seen are skipped.
"""

from __future__ import annotations

import logging
import threading

import httpx
from pydantic import ValidationError

from .jobs import CallRequest, JobQueue

log = logging.getLogger(__name__)


def extract_requests(data) -> list[dict]:
    if not data:
        return []
    if isinstance(data, dict):
        if "calls" in data and isinstance(data["calls"], list):
            return data["calls"]
        return [data] if "phone_number" in data else []
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    return []


class Poller:
    def __init__(self, url: str, jobs: JobQueue, interval: float = 10.0, headers: dict | None = None):
        self.url = url
        self.jobs = jobs
        self.interval = interval
        self.headers = headers or {}
        self.seen: set[str] = set()
        self._stop = threading.Event()

    def poll_once(self) -> int:
        resp = httpx.get(self.url, headers=self.headers, timeout=15)
        resp.raise_for_status()
        added = 0
        for raw in extract_requests(resp.json() if resp.content else None):
            try:
                req = CallRequest(**raw)
            except ValidationError as e:
                log.warning("ignoring bad call request %r: %s", raw, e)
                continue
            if req.reference:
                if req.reference in self.seen:
                    continue
                self.seen.add(req.reference)
            self.jobs.submit(req)
            added += 1
        return added

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                n = self.poll_once()
                if n:
                    log.info("queued %d call request(s) from %s", n, self.url)
            except Exception as e:
                log.warning("polling %s failed: %s", self.url, e)
            self._stop.wait(self.interval)

    def start(self) -> None:
        threading.Thread(target=self._loop, name="poller", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
