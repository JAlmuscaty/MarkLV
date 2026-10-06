"""Silence Jarvis for the length of a phone call.

The microphone must not be streamed and nothing queued for the speakers may
play. The flag is checked on the audio threads, so a plugin can set it without
touching the window.
"""

import threading

_hold = threading.Event()
_on_end: list = []


def active() -> bool:
    return _hold.is_set()


def begin() -> None:
    _hold.set()


def on_end(fn) -> None:
    """Run fn on the thread that clears the hold, once, when a call finishes."""
    if fn not in _on_end:
        _on_end.append(fn)


def end() -> None:
    was = _hold.is_set()
    _hold.clear()
    if not was:
        return
    for fn in list(_on_end):
        try:
            fn()
        except Exception:
            pass
