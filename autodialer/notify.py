"""Tell the user what happened: phone notification, webhook, and log."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, device=None, notify_on_phone: bool = True, default_webhook: str | None = None):
        self.device = device
        self.notify_on_phone = notify_on_phone
        self.default_webhook = default_webhook

    def job_finished(self, job) -> None:
        payload = job.public()
        r = job.result
        if r is not None and not r.called:
            log.warning("call %s NOT placed: %s", job.id, r.message)
            if self.notify_on_phone and self.device is not None:
                who = f" ({job.request.name})" if job.request.name else ""
                try:
                    self.device.notify(f"Call not placed{who}", r.message, tag=f"autodialer-{job.id}")
                except Exception:
                    log.exception("could not post phone notification")
        else:
            log.info("call %s placed to %s", job.id, job.request.phone_number)

        url = job.request.callback_url or self.default_webhook
        if url:
            try:
                httpx.post(url, json=payload, timeout=10)
            except Exception:
                log.exception("webhook %s failed", url)
