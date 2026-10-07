"""A simulated Android dialer that reacts to touch gestures like the real one."""

from __future__ import annotations

PKG = "com.google.android.dialer"
KEYS = [("1", "one"), ("2", "two"), ("3", "three"), ("4", "four"), ("5", "five"), ("6", "six"),
        ("7", "seven"), ("8", "eight"), ("9", "nine"), ("*", "star"), ("0", "zero"), ("#", "pound")]


class FakePhone:
    def __init__(self, prefilled: str = "", drop_index: int | None = None, wrong_key: dict | None = None,
                 formatter=None, call_state_after_call: int = 2):
        self.digits = prefilled
        self.opened = False
        self.called = False
        self.presses: list[tuple] = []
        self.notifications: list[tuple] = []
        self.drop_index = drop_index          # simulate a missed tap
        self.wrong_key = wrong_key or {}      # simulate a fat-finger: {press_index: "8"}
        self.formatter = formatter or (lambda s: s)
        self._n = 0
        self._state_after = call_state_after_call
        self.key_bounds = {}
        for i, (label, _) in enumerate(KEYS):
            r, c = divmod(i, 3)
            self.key_bounds[label] = (60 + c * 330, 1200 + r * 180, 360 + c * 330, 1360 + r * 180)
        self.call_bounds = (450, 1950, 630, 2130)
        self.delete_bounds = (900, 1980, 1020, 2100)

    # --- device interface ---
    def wake_and_unlock_hint(self):
        pass

    def is_connected(self):
        return True

    def open_dialer(self, package=None):
        self.opened = True

    def call_state(self):
        return self._state_after if self.called else 0

    def notify(self, title, text, tag="x"):
        self.notifications.append((title, text))

    def press(self, x, y, x2, y2, duration_ms):
        self.presses.append((x, y, x2, y2, duration_ms))
        idx = self._n
        self._n += 1
        if _inside(self.call_bounds, x, y):
            self.called = True
            return
        if _inside(self.delete_bounds, x, y):
            self.digits = "" if duration_ms >= 600 else self.digits[:-1]
            return
        for label, b in self.key_bounds.items():
            if _inside(b, x, y):
                if idx == self.drop_index:
                    return
                label = self.wrong_key.get(idx, label)
                if label == "0" and duration_ms >= 600:
                    label = "+"
                self.digits += label
                return
        raise AssertionError(f"tap at {(x, y)} hit nothing")

    def dump_ui(self) -> str:
        nodes = []
        for label, rid in KEYS:
            l, t, r, b = self.key_bounds[label]
            nodes.append(
                f'<node index="0" text="" resource-id="{PKG}:id/{rid}" class="android.widget.FrameLayout" '
                f'package="{PKG}" content-desc="{label}" clickable="true" enabled="true" bounds="[{l},{t}][{r},{b}]">'
                f'<node index="0" text="{label}" resource-id="{PKG}:id/dialpad_key_number" '
                f'class="android.widget.TextView" package="{PKG}" content-desc="" clickable="false" enabled="true" '
                f'bounds="[{l+100},{t+20}][{r-100},{b-60}]" /></node>')
        shown = self.formatter(self.digits).replace("&", "&amp;").replace('"', "&quot;")
        l, t, r, b = self.call_bounds
        dl, dt, dr, db = self.delete_bounds
        return (
            "<?xml version='1.0' encoding='UTF-8' standalone='yes' ?>"
            '<hierarchy rotation="0">'
            f'<node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="{PKG}" '
            'content-desc="" clickable="false" enabled="true" bounds="[0,0][1080,2340]">'
            f'<node index="0" text="{shown}" resource-id="{PKG}:id/digits" class="android.widget.EditText" '
            f'package="{PKG}" content-desc="" clickable="true" enabled="true" bounds="[60,900][1020,1100]" />'
            + "".join(nodes) +
            f'<node index="0" text="" resource-id="{PKG}:id/dialpad_floating_action_button" '
            f'class="android.widget.ImageButton" package="{PKG}" content-desc="dial" clickable="true" '
            f'enabled="true" bounds="[{l},{t}][{r},{b}]" />'
            f'<node index="0" text="" resource-id="{PKG}:id/deleteButton" class="android.widget.ImageButton" '
            f'package="{PKG}" content-desc="backspace" clickable="true" enabled="true" '
            f'bounds="[{dl},{dt}][{dr},{db}]" />'
            "</node></hierarchy>"
        )


def _inside(b, x, y):
    l, t, r, bt = b
    return l <= x < r and t <= y < bt
