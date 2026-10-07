"""HTTP API that accepts call requests."""

from __future__ import annotations

import hmac
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException

from .adb import AdbDevice
from .config import Settings
from .dialer import GuiDialer
from .jobs import CallRequest, JobQueue
from .notify import Notifier
from .numbers import InvalidNumber, to_dial_sequence
from .poller import Poller

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, device=None, jobs: JobQueue | None = None,
               start_worker: bool = True) -> FastAPI:
    settings = settings or Settings.from_env()
    device = device or AdbDevice(settings.adb_serial, settings.adb_path)
    if jobs is None:
        dialer = GuiDialer(device, dialer_package=settings.dialer_package, id_overrides=settings.id_overrides)
        notifier = Notifier(device, settings.notify_on_phone, settings.webhook_url)
        jobs = JobQueue(dialer, notifier, min_gap=settings.min_seconds_between_calls)
    poller = Poller(settings.poll_url, jobs, settings.poll_interval) if settings.poll_url else None

    @asynccontextmanager
    async def lifespan(app):
        if start_worker:
            jobs.start()
            if poller:
                poller.start()
        yield
        jobs.stop()
        if poller:
            poller.stop()

    app = FastAPI(title="Auto-dialer", version="0.1.0", lifespan=lifespan)
    app.state.jobs = jobs

    def auth(authorization: str | None = Header(None)):
        if settings.api_token:
            expected = f"Bearer {settings.api_token}"
            if not authorization or not hmac.compare_digest(authorization, expected):
                raise HTTPException(401, "invalid or missing bearer token")

    @app.get("/health")
    def health():
        connected = device.is_connected() if hasattr(device, "is_connected") else None
        return {"ok": True, "device_connected": connected, "queued": jobs.pending()}

    @app.post("/calls", status_code=202, dependencies=[Depends(auth)])
    def create_call(req: CallRequest):
        try:
            to_dial_sequence(req.phone_number)
        except InvalidNumber as e:
            raise HTTPException(422, f"invalid phone_number: {e}")
        job = jobs.submit(req)
        return job.public()

    @app.get("/calls", dependencies=[Depends(auth)])
    def list_calls():
        return [j.public() for j in reversed(jobs.all())]

    @app.get("/calls/{job_id}", dependencies=[Depends(auth)])
    def get_call(job_id: str):
        job = jobs.get(job_id)
        if job is None:
            raise HTTPException(404, "no such call")
        return job.public()

    return app
