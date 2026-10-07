"""Thin wrapper around ``adb`` for driving a phone's touch screen."""

from __future__ import annotations

import re
import shlex
import subprocess
import time


class DeviceError(RuntimeError):
    pass


class AdbDevice:
    """Talks to one Android device through the ``adb`` binary."""

    DUMP_PATH = "/sdcard/autodialer_ui.xml"

    def __init__(self, serial: str | None = None, adb_path: str = "adb", timeout: float = 20.0):
        self.serial = serial
        self.adb_path = adb_path
        self.timeout = timeout

    # -- low level -------------------------------------------------------
    def _base(self) -> list[str]:
        cmd = [self.adb_path]
        if self.serial:
            cmd += ["-s", self.serial]
        return cmd

    def shell(self, command: str, check: bool = True) -> str:
        try:
            r = subprocess.run(
                self._base() + ["shell", command],
                capture_output=True, text=True, timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise DeviceError(f"adb not found at {self.adb_path!r}") from e
        except subprocess.TimeoutExpired as e:
            raise DeviceError(f"adb timed out running: {command}") from e
        if check and r.returncode != 0:
            raise DeviceError(f"adb shell failed ({r.returncode}): {r.stderr.strip() or r.stdout.strip()}")
        return r.stdout

    # -- device state ----------------------------------------------------
    def is_connected(self) -> bool:
        try:
            r = subprocess.run(self._base() + ["get-state"], capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
        return r.returncode == 0 and r.stdout.strip() == "device"

    def wake_and_unlock_hint(self) -> None:
        """Turn the screen on. (A secure lock screen must be unlocked by the user.)"""
        out = self.shell("dumpsys power | grep -E 'mWakefulness=|Display Power: state='", check=False)
        if "Awake" not in out and "state=ON" not in out:
            self.shell("input keyevent KEYCODE_WAKEUP", check=False)
            time.sleep(0.6)
        self.shell("wm dismiss-keyguard", check=False)

    def call_state(self) -> int | None:
        """0 = idle, 1 = ringing, 2 = off-hook (dialing / in call)."""
        out = self.shell("dumpsys telephony.registry", check=False)
        m = re.search(r"mCallState=(\d)", out)
        return int(m.group(1)) if m else None

    # -- screen ----------------------------------------------------------
    def dump_ui(self) -> str:
        for attempt in range(3):
            out = self.shell(f"uiautomator dump {self.DUMP_PATH} >/dev/null 2>&1; cat {self.DUMP_PATH}", check=False)
            if "<hierarchy" in out:
                return out[out.find("<?xml") if "<?xml" in out else out.find("<hierarchy"):]
            time.sleep(0.5 + attempt * 0.5)
        raise DeviceError("could not dump the UI hierarchy (is the screen on and unlocked?)")

    def open_dialer(self, package: str | None = None) -> None:
        """Open the phone app's keypad with an EMPTY number field.

        ``android.intent.action.DIAL`` with no data just shows the dialpad, the
        same as tapping the Phone icon; it does not pre-fill or place a call.
        """
        cmd = "am start -W -a android.intent.action.DIAL"
        if package:
            cmd += f" -p {shlex.quote(package)}"
        self.shell(cmd)

    def press(self, x: int, y: int, x2: int, y2: int, duration_ms: int) -> None:
        """A real touch-down/move/touch-up gesture, held for ``duration_ms``.

        ``input swipe`` with a tiny displacement produces a tap with a natural,
        variable contact time instead of the fixed instant tap of ``input tap``.
        """
        self.shell(f"input touchscreen swipe {x} {y} {x2} {y2} {int(duration_ms)}")

    def back(self) -> None:
        self.shell("input keyevent KEYCODE_BACK", check=False)

    def notify(self, title: str, text: str, tag: str = "autodialer") -> None:
        """Post a notification on the phone (Android 10+ ``cmd notification``)."""
        self.shell(
            "cmd notification post -S bigtext -t {} {} {}".format(
                shlex.quote(title), shlex.quote(tag), shlex.quote(text)
            ),
            check=False,
        )
