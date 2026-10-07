import random

from fake_phone import FakePhone
from fastapi.testclient import TestClient

from autodialer.config import Settings
from autodialer.dialer import GuiDialer
from autodialer.human import Humanizer
from autodialer.jobs import JobQueue
from autodialer.notify import Notifier
from autodialer.poller import extract_requests


def setup(phone, token=None):
    dialer = GuiDialer(phone, Humanizer(rng=random.Random(0)), sleep=lambda s: None, confirm_call_timeout=0)
    jobs = JobQueue(dialer, Notifier(phone, True), min_gap=0)
    from autodialer.server import create_app
    app = create_app(Settings(api_token=token), device=phone, jobs=jobs, start_worker=False)
    return TestClient(app), jobs


def test_call_flow_through_api():
    phone = FakePhone()
    client, jobs = setup(phone)
    resp = client.post("/calls", json={"phone_number": "+1 555 123 4567", "name": "Asha", "info": {"crm": 7}})
    assert resp.status_code == 202
    job_id = resp.json()["id"]
    jobs.run_one(jobs._q.get_nowait())
    body = client.get(f"/calls/{job_id}").json()
    assert body["status"] == "called"
    assert body["called"] is True
    assert body["request"]["info"] == {"crm": 7}
    assert phone.notifications == []


def test_mismatch_notifies_user_on_phone():
    phone = FakePhone(drop_index=0)
    client, jobs = setup(phone)
    job_id = client.post("/calls", json={"phone_number": "5551234567", "name": "Ravi"}).json()["id"]
    jobs.run_one(jobs._q.get_nowait())
    body = client.get(f"/calls/{job_id}").json()
    assert body["status"] == "mismatch"
    assert body["called"] is False
    assert not phone.called
    assert phone.notifications and "Ravi" in phone.notifications[0][0]


def test_rejects_bad_number_and_requires_token():
    client, _ = setup(FakePhone(), token="s3cret")
    assert client.post("/calls", json={"phone_number": "123"}).status_code == 401
    h = {"Authorization": "Bearer s3cret"}
    assert client.post("/calls", json={"phone_number": "abc"}, headers=h).status_code == 422
    assert client.post("/calls", json={"phone_number": "123"}, headers=h).status_code == 202


def test_extract_requests_shapes():
    assert extract_requests(None) == []
    assert extract_requests({"phone_number": "1"}) == [{"phone_number": "1"}]
    assert extract_requests({"calls": [{"phone_number": "1"}]}) == [{"phone_number": "1"}]
    assert extract_requests([{"phone_number": "1"}, 5]) == [{"phone_number": "1"}]
