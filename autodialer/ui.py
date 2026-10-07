"""Parsing of ``uiautomator dump`` XML and locating dialer controls."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

_BOUNDS = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")

# resource-id suffix used by AOSP / Google / Samsung / most OEM dialers.
KEY_ID_SUFFIX = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
    "*": "star", "#": "pound",
}

DIGITS_FIELD_IDS = ("digits", "digits_edit", "dialpad_digits", "edit_text_digits")
CALL_BUTTON_IDS = (
    "dialpad_floating_action_button", "dialpad_voice_call_button",
    "dialButton", "dial_button", "call_button", "dialpad_call_button",
)
DELETE_BUTTON_IDS = ("deleteButton", "delete_button", "dialpad_delete")
CALL_DESC_WORDS = ("call", "dial", "anruf", "llamar", "appeler", "कॉल")


@dataclass(frozen=True)
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> tuple[int, int]:
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    @property
    def area(self) -> int:
        return max(0, self.width) * max(0, self.height)

    @classmethod
    def parse(cls, raw: str) -> "Bounds | None":
        m = _BOUNDS.fullmatch(raw.strip()) if raw else None
        return cls(*map(int, m.groups())) if m else None


@dataclass
class Node:
    resource_id: str
    text: str
    desc: str
    cls: str
    package: str
    clickable: bool
    enabled: bool
    bounds: Bounds | None
    children: list["Node"] = field(default_factory=list)
    parent: "Node | None" = field(default=None, repr=False)

    @property
    def id_suffix(self) -> str:
        return self.resource_id.rsplit("/", 1)[-1] if self.resource_id else ""

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    def clickable_self_or_ancestor(self) -> "Node":
        n: Node | None = self
        while n is not None:
            if n.clickable and n.bounds and n.bounds.area > 0:
                return n
            n = n.parent
        return self


def parse_dump(xml_text: str) -> Node:
    """Parse a uiautomator XML dump into a tree of :class:`Node`."""
    start = xml_text.find("<")
    root_el = ET.fromstring(xml_text[start:] if start > 0 else xml_text)

    def build(el, parent):
        a = el.attrib
        node = Node(
            resource_id=a.get("resource-id", ""),
            text=a.get("text", ""),
            desc=a.get("content-desc", ""),
            cls=a.get("class", ""),
            package=a.get("package", ""),
            clickable=a.get("clickable") == "true",
            enabled=a.get("enabled", "true") == "true",
            bounds=Bounds.parse(a.get("bounds", "")),
            parent=parent,
        )
        node.children = [build(c, node) for c in el if c.tag == "node"]
        return node

    return build(root_el, None)


@dataclass
class DialerScreen:
    """The parts of the dialer we interact with, found on one UI dump."""

    package: str
    keys: dict[str, Bounds]
    digits_field: Node | None
    call_button: Bounds | None
    delete_button: Bounds | None

    def missing_keys(self, sequence: str) -> list[str]:
        need = {("0" if c == "+" else c) for c in sequence}
        return sorted(k for k in need if k not in self.keys)


def _by_suffix(root: Node, suffixes) -> Node | None:
    for n in root.walk():
        if n.id_suffix in suffixes and n.bounds and n.bounds.area > 0:
            return n
    return None


def find_dialer_screen(root: Node, overrides: dict | None = None) -> DialerScreen:
    """Locate the dialpad keys, the number field and the call button.

    ``overrides`` may map ``"keys"`` / ``"digits_field"`` / ``"call_button"`` /
    ``"delete_button"`` to resource-id suffixes for dialers that use
    non-standard ids.
    """
    overrides = overrides or {}
    key_suffix = {**KEY_ID_SUFFIX, **overrides.get("keys", {})}
    keys: dict[str, Bounds] = {}

    # 1. Keys by resource id (fast and reliable on most dialers).
    suffix_to_key = {v: k for k, v in key_suffix.items()}
    for n in root.walk():
        k = suffix_to_key.get(n.id_suffix)
        if k and k not in keys and n.bounds and n.bounds.area > 0:
            keys[k] = n.clickable_self_or_ancestor().bounds

    # 2. Fallback: a TextView whose text is exactly the key label, inside a
    #    clickable container.
    if len(keys) < len(key_suffix):
        for n in root.walk():
            t = n.text.strip()
            if t in key_suffix and t not in keys and n.bounds:
                target = n.clickable_self_or_ancestor()
                if target.clickable and target.bounds:
                    keys[t] = target.bounds

    digits = _by_suffix(root, tuple(overrides.get("digits_field", ())) + DIGITS_FIELD_IDS)
    call = _by_suffix(root, tuple(overrides.get("call_button", ())) + CALL_BUTTON_IDS)
    if call is None:
        for n in root.walk():
            d = n.desc.lower()
            if n.clickable and n.bounds and any(w in d for w in CALL_DESC_WORDS) \
                    and "video" not in d and "delete" not in d:
                call = n
                break
    delete = _by_suffix(root, tuple(overrides.get("delete_button", ())) + DELETE_BUTTON_IDS)

    package = next((n.package for n in root.walk() if n.package), "")
    return DialerScreen(
        package=package,
        keys=keys,
        digits_field=digits,
        call_button=call.clickable_self_or_ancestor().bounds if call else None,
        delete_button=delete.clickable_self_or_ancestor().bounds if delete else None,
    )


def read_digits(root: Node, overrides: dict | None = None) -> str | None:
    """Return the raw text of the dialer's number field, or ``None``."""
    overrides = overrides or {}
    n = _by_suffix(root, tuple(overrides.get("digits_field", ())) + DIGITS_FIELD_IDS)
    return n.text if n is not None else None
