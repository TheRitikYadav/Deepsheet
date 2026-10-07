"""Auto-dialer: receives call requests over an HTTP API and dials them on an
Android phone by tapping the dialer's on-screen keypad like a human would.

The call is never placed through ``ACTION_CALL`` or any other internal API.
Every digit is tapped on the real dialer GUI, the number shown on screen is
read back and compared with the requested number, and only if they match is
the green call button tapped.
"""

__version__ = "0.1.0"
