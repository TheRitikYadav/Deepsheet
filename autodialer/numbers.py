"""Phone-number normalisation and comparison."""

from __future__ import annotations

import re

# Characters that can actually be entered on a dialpad.
DIALABLE = set("0123456789*#+")

_STRIP = re.compile(r"[\s\-(). ‐-―‪-‮⁦-⁩]")


class InvalidNumber(ValueError):
    pass


def to_dial_sequence(number: str) -> str:
    """Return the exact key sequence that must be pressed for ``number``.

    Formatting characters (spaces, dashes, brackets, dots) are dropped. A ``+``
    is only allowed as the first character. Anything else is rejected rather
    than silently ignored, so we never dial something the caller did not ask
    for.
    """
    if number is None:
        raise InvalidNumber("phone number is missing")
    cleaned = _STRIP.sub("", str(number))
    if not cleaned:
        raise InvalidNumber("phone number is empty")
    bad = sorted({c for c in cleaned if c not in DIALABLE})
    if bad:
        raise InvalidNumber(f"phone number contains invalid characters: {''.join(bad)!r}")
    if "+" in cleaned[1:]:
        raise InvalidNumber("'+' is only allowed at the start of the number")
    if not any(c.isdigit() for c in cleaned):
        raise InvalidNumber("phone number has no digits")
    if len(cleaned) > 20:
        raise InvalidNumber("phone number is too long")
    return cleaned


def normalise_display(text: str | None) -> str:
    """Normalise what the dialer shows on screen so it can be compared.

    Dialers auto-format numbers (``98765 43210``, ``(555) 123-4567``) and may
    wrap them in invisible bidi marks; all of that is stripped.
    """
    if not text:
        return ""
    return "".join(c for c in _STRIP.sub("", text) if c in DIALABLE)


def numbers_match(expected_sequence: str, displayed_text: str | None) -> bool:
    """Exact comparison of the requested key sequence and the on-screen number."""
    return normalise_display(displayed_text) == expected_sequence
