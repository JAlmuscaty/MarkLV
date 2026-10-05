"""Silence Jarvis for the length of a phone call.

The microphone must not be streamed and nothing queued for the speakers may
play. The flag is checked on the audio threads, so a plugin can set it without
touching the window.
"""

import threading

_hold = threading.Event()


def active() -> bool:
    return _hold.is_set()


def begin() -> None:
    _hold.set()


def end() -> None:
    _hold.clear()
