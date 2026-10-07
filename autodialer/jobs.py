"""Call requests and the single worker that executes them one after another."""

from __future__ import annotations

import itertools
import logging
import queue
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

from .dialer import DialResult, GuiDialer, Outcome

log = logging.getLogger(__name__)


class CallRequest(BaseModel):
    phone_number: str = Field(..., description="Number to dial, e.g. '+91 98765 43210'")
    name: str | None = Field(None, description="Who is being called (shown in notifications)")
    reference: str | None = Field(None, description="Your own id for this request")
    info: dict[str, Any] = Field(default_factory=dict, description="Any extra data; echoed back")
    callback_url: str | None = Field(None, description="POST the result here when done")


@dataclass
class Job:
    id: str
    request: CallRequest
    status: str = "queued"        # queued -> dialing -> called | mismatch | invalid_number | failed
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    finished_at: str | None = None
    result: DialResult | None = None

    def public(self) -> dict:
        r = self.result
        return {
            "id": self.id,
            "status": self.status,
            "request": self.request.model_dump(),
            "created_at": self.created_at,
            "finished_at": self.finished_at,
            "called": bool(r and r.called),
            "expected_number": r.expected if r else None,
            "displayed_number": r.displayed if r else None,
            "message": r.message if r else None,
            "steps": r.steps if r else [],
        }


class JobQueue:
    """One phone can only dial one number at a time, so jobs run serially."""

    def __init__(self, dialer: GuiDialer, notifier=None, min_gap: float = 5.0, history: int = 500):
        self.dialer = dialer
        self.notifier = notifier
        self.min_gap = min_gap
        self.history = history
        self._q: queue.Queue[Job] = queue.Queue()
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def submit(self, req: CallRequest) -> Job:
        job = Job(id=f"{int(time.time())}-{next(self._ids)}", request=req)
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self.history:
                self._jobs.pop(next(iter(self._jobs)))
        self._q.put(job)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def all(self) -> list[Job]:
        with self._lock:
            return list(self._jobs.values())

    def pending(self) -> int:
        return self._q.qsize()

    def run_one(self, job: Job) -> Job:
        job.status = "dialing"
        try:
            job.result = self.dialer.dial(job.request.phone_number)
        except Exception as e:  # dial() already catches, this is a last resort
            job.result = DialResult(Outcome.FAILED, job.request.phone_number, message=str(e))
        job.status = job.result.outcome.value
        job.finished_at = datetime.now(timezone.utc).isoformat()
        if self.notifier:
            self.notifier.job_finished(job)
        return job

    def _loop(self) -> None:
        last = 0.0
        while not self._stop.is_set():
            try:
                job = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            wait = self.min_gap - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
            self.run_one(job)
            last = time.monotonic()

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="dialer-worker", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
