import random

from fake_phone import FakePhone

from autodialer.dialer import GuiDialer, Outcome
from autodialer.human import Humanizer


def make(phone, seed=0):
    return GuiDialer(phone, Humanizer(rng=random.Random(seed)), sleep=lambda s: None, confirm_call_timeout=0)


def test_dials_verifies_and_calls():
    phone = FakePhone(formatter=lambda s: f"{s[:5]} {s[5:]}")
    r = make(phone).dial("98765 43210")
    assert r.outcome is Outcome.CALLED, r.message
    assert phone.digits == "9876543210"
    assert phone.called
    assert phone.opened
    # each digit + call button = 11 touches, all with varying contact time
    assert len(phone.presses) == 11
    assert len({p[4] for p in phone.presses}) > 1


def test_plus_prefix_uses_long_press_zero():
    phone = FakePhone()
    r = make(phone).dial("+44 20 7946 0000")
    assert r.called, r.message
    assert phone.digits == "+442079460000"


def test_missed_tap_means_no_call():
    phone = FakePhone(drop_index=3)
    r = make(phone).dial("9876543210")
    assert r.outcome is Outcome.MISMATCH
    assert not phone.called
    assert "NOT placed" in r.message
    assert phone.digits == ""          # wrong number was wiped


def test_wrong_key_means_no_call():
    phone = FakePhone(wrong_key={2: "8"})
    r = make(phone).dial("1234567890")
    assert r.outcome is Outcome.MISMATCH
    assert r.displayed == "1284567890"
    assert not phone.called


def test_clears_leftover_number_first():
    phone = FakePhone(prefilled="5550000")
    r = make(phone).dial("12345")
    assert r.called, r.message
    assert phone.digits == "12345"


def test_invalid_number_never_touches_phone():
    phone = FakePhone()
    r = make(phone).dial("12-AB-34")
    assert r.outcome is Outcome.INVALID
    assert not phone.opened and not phone.presses


def test_missing_keypad_fails_without_calling():
    phone = FakePhone()
    phone.dump_ui = lambda: "<?xml version='1.0'?><hierarchy rotation='0'><node bounds='[0,0][10,10]'/></hierarchy>"
    r = make(phone).dial("123")
    assert r.outcome is Outcome.FAILED
    assert not phone.called
