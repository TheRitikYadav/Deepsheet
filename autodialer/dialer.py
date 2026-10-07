"""The GUI dialing flow: open keypad -> tap digits -> read back -> verify -> call."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from .human import Humanizer
from .numbers import numbers_match, normalise_display, to_dial_sequence
from .ui import DialerScreen, find_dialer_screen, parse_dump, read_digits

log = logging.getLogger(__name__)


class Outcome(str, Enum):
    CALLED = "called"            # number verified and call button tapped
    MISMATCH = "mismatch"        # on-screen number differed -> NOT called
    INVALID = "invalid_number"   # API gave a number we refuse to dial
    FAILED = "failed"            # device / UI problem -> NOT called


@dataclass
class DialResult:
    outcome: Outcome
    expected: str
    displayed: str | None = None
    message: str = ""
    steps: list[str] = field(default_factory=list)

    @property
    def called(self) -> bool:
        return self.outcome is Outcome.CALLED


class Device:  # pragma: no cover - documents the interface AdbDevice implements
    def dump_ui(self) -> str: ...
    def open_dialer(self, package: str | None = None) -> None: ...
    def press(self, x: int, y: int, x2: int, y2: int, duration_ms: int) -> None: ...
    def call_state(self) -> int | None: ...
    def wake_and_unlock_hint(self) -> None: ...


class GuiDialer:
    def __init__(
        self,
        device,
        humanizer: Humanizer | None = None,
        dialer_package: str | None = None,
        id_overrides: dict | None = None,
        sleep: Callable[[float], None] = time.sleep,
        confirm_call_timeout: float = 8.0,
    ):
        self.device = device
        self.h = humanizer or Humanizer()
        self.dialer_package = dialer_package
        self.overrides = id_overrides or {}
        self.sleep = sleep
        self.confirm_call_timeout = confirm_call_timeout

    # -- helpers ---------------------------------------------------------
    def _screen(self) -> tuple[DialerScreen, object]:
        root = parse_dump(self.device.dump_ui())
        return find_dialer_screen(root, self.overrides), root

    def _tap(self, bounds, long: bool = False) -> None:
        x, y = self.h.point_in(bounds)
        x2, y2 = self.h.drift(x, y, bounds)
        self.device.press(x, y, x2, y2, self.h.press_duration_ms(long=long))

    def _clear(self, screen: DialerScreen, current: str) -> None:
        """Erase whatever is in the number field using the on-screen delete key."""
        if not screen.delete_button or not current:
            return
        self._tap(screen.delete_button, long=True)   # long-press clears all on most dialers
        self.sleep(0.4)
        root = parse_dump(self.device.dump_ui())
        left = normalise_display(read_digits(root, self.overrides))
        for _ in range(len(left)):
            self._tap(screen.delete_button)
            self.sleep(self.h.rng.uniform(0.08, 0.18))

    # -- main flow -------------------------------------------------------
    def dial(self, phone_number: str) -> DialResult:
        steps: list[str] = []
        try:
            seq = to_dial_sequence(phone_number)
        except ValueError as e:
            return DialResult(Outcome.INVALID, str(phone_number), message=str(e))

        try:
            self.device.wake_and_unlock_hint()
            self.device.open_dialer(self.dialer_package)
            steps.append("opened dialer keypad")
            self.sleep(self.h.pause(self.h.p.before_dial))

            screen, root = self._screen()
            if screen.digits_field is None:
                return DialResult(Outcome.FAILED, seq, message="dialer number field not found on screen "
                                  "(is the keypad visible and the phone unlocked?)", steps=steps)
            missing = screen.missing_keys(seq)
            if missing:
                return DialResult(Outcome.FAILED, seq, message=f"dialpad keys not found on screen: {missing}",
                                  steps=steps)
            if screen.call_button is None:
                return DialResult(Outcome.FAILED, seq, message="call button not found on screen", steps=steps)

            # Start from an empty field (the dialer may remember a previous number).
            existing = normalise_display(screen.digits_field.text)
            if existing:
                self._clear(screen, existing)
                screen, root = self._screen()
                if normalise_display(screen.digits_field.text if screen.digits_field else ""):
                    return DialResult(Outcome.FAILED, seq, message="could not clear number field", steps=steps)
                steps.append("cleared previous number")

            # Type the number, one human-like key press at a time.
            for i, ch in enumerate(seq):
                self.sleep(self.h.key_gap(i))
                if ch == "+":
                    self._tap(screen.keys["0"], long=True)  # long-press 0 gives '+'
                else:
                    self._tap(screen.keys[ch])
            steps.append(f"tapped {len(seq)} keys")

            # Read back what the phone actually shows and compare.
            self.sleep(self.h.rng.uniform(0.4, 0.8))
            root = parse_dump(self.device.dump_ui())
            shown = read_digits(root, self.overrides)
            steps.append(f"screen shows {shown!r}")

            if not numbers_match(seq, shown):
                # Never call a number that is not exactly the requested one.
                screen_now = find_dialer_screen(root, self.overrides)
                try:
                    self._clear(screen_now, normalise_display(shown))
                    steps.append("cleared wrong number")
                except Exception:  # best effort only
                    log.exception("failed to clear mismatched number")
                return DialResult(
                    Outcome.MISMATCH, seq, displayed=shown,
                    message=f"dialed number {normalise_display(shown) or '(empty)'} does not match "
                            f"requested {seq}; call NOT placed",
                    steps=steps,
                )

            # Verified -> press call like a person would.
            self.sleep(self.h.pause(self.h.p.before_call))
            screen_now = find_dialer_screen(root, self.overrides)
            self._tap(screen_now.call_button or screen.call_button)
            steps.append("tapped call button")

            msg = "call placed"
            if self._wait_offhook():
                steps.append("phone is off-hook")
            else:
                msg = "call button tapped but phone did not report an active call"
            return DialResult(Outcome.CALLED, seq, displayed=shown, message=msg, steps=steps)
        except Exception as e:
            log.exception("dialing failed")
            return DialResult(Outcome.FAILED, seq, message=f"{type(e).__name__}: {e}", steps=steps)

    def _wait_offhook(self) -> bool:
        deadline = time.monotonic() + self.confirm_call_timeout
        while True:
            state = self.device.call_state()
            if state == 2:
                return True
            if state is None or time.monotonic() >= deadline:
                return False
            self.sleep(0.5)
