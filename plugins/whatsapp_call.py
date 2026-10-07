"""Place, decline, and answer-by-text WhatsApp calls from the desktop app.

Outgoing calls use the voice-call button itself. While a call is ringing or
connected, Jarvis neither speaks nor listens.
"""

from __future__ import annotations

import threading

PLUGIN = {
    "name": "whatsapp_call",
    "description": (
        "WhatsApp calls on the desktop app. Use this — not send_message and not "
        "the browser — when the user wants to call someone on WhatsApp, decline "
        "an incoming WhatsApp voice or video call, or decline and tell that "
        "person they are busy and will call later. "
        "action='call' clicks the voice call icon in that person's chat. "
        "action='decline' clicks Decline on the incoming voice or video call that "
        "is ringing right now. "
        "action='decline_all' arms continuous watching. Use it as soon as the user "
        "says to decline incoming calls, reject every call, or don't answer "
        "calls — even if nobody is ringing at that moment, and even if Jarvis "
        "is muted. He keeps looking at the screen and declines each new call "
        "until they say to stop. Do not wait for a call to be ringing. "
        "action='allow_calls' stops that. Use it when they say to take calls "
        "again or stop declining. "
        "action='decline_and_message' declines the call that is ringing, then "
        "sends a message that the user is busy and will call later. "
        "Pass the contact name in 'contact'. During an outgoing call Jarvis stays "
        "silent until the call ends; do not keep talking after you start it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "call | decline | decline_all | allow_calls | decline_and_message",
            },
            "contact": {
                "type": "STRING",
                "description": "The person's name as it appears in WhatsApp.",
            },
            "message": {
                "type": "STRING",
                "description": "Optional text for decline_and_message. Default says the user is busy and will call later.",
            },
        },
        "required": ["action"],
    },
    "behavior": "NON_BLOCKING",
}

_BUSY = "I'm busy right now. I'll call you later."


def _quiet(player) -> None:
    from core import call_hold
    call_hold.begin()
    try:
        hook = getattr(player, "on_interrupt", None)
        if hook:
            hook()
    except Exception:
        pass


def _watch_until_call_ends() -> None:
    """Drop the silence once the call is gone, even if WhatsApp's audio stays open."""
    from core import call_hold
    from plugins import _whatsapp_core as wa

    try:
        app = wa.WhatsApp()
    except Exception:
        call_hold.end()
        return

    # The ring needs a moment to appear. If it never does, don't stay mute.
    seen = False
    for attempt in range(8):
        time_sleep(1.0)
        try:
            live = app.call_in_progress()
        except Exception:
            live = False
        if not live and attempt == 7:
            try:
                live = app.screen_says_call()
            except Exception:
                live = False
        if live:
            seen = True
            break
    if not seen:
        call_hold.end()
        return

    quiet_passes = 0
    audio_only = 0
    for _ in range(7200):
        time_sleep(1.0)
        try:
            on_screen = app.ui_says_call()
        except Exception:
            on_screen = False
        try:
            audible = app.call_in_progress()
        except Exception:
            audible = False
        if on_screen:
            quiet_passes = 0
            audio_only = 0
            continue
        if audible:
            quiet_passes = 0
            audio_only += 1
            # Audio alone can stick after hang-up. Look at the window before
            # staying silent for the rest of the evening.
            if audio_only >= 12:
                audio_only = 0
                try:
                    if not app.screen_says_call():
                        break
                except Exception:
                    break
            continue
        quiet_passes += 1
        if quiet_passes >= 3:
            break
    call_hold.end()


_DECLINE_ALL = threading.Event()
_DECLINE_THREAD: threading.Thread | None = None
_DECLINE_LOCK = threading.Lock()


def _decline_flag():
    from core.drive_scope import save_dir
    return save_dir() / "decline_incoming_calls.txt"


def _ensure_decline_thread() -> None:
    global _DECLINE_THREAD
    with _DECLINE_LOCK:
        if _DECLINE_THREAD is not None and _DECLINE_THREAD.is_alive():
            return
        _DECLINE_THREAD = threading.Thread(
            target=_decline_all_loop, daemon=True, name="whatsapp-decline-all"
        )
        _DECLINE_THREAD.start()


def _set_decline_all(on: bool) -> None:
    path = _decline_flag()
    if on:
        path.write_text("on", encoding="utf-8")
        _DECLINE_ALL.set()
        _ensure_decline_thread()
        return
    _DECLINE_ALL.clear()
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass


def _decline_all_loop() -> None:
    """Keep looking at the screen and decline each incoming call.

    Mute does not stop this. A call does not have to be ringing when the
    order is given; the next one is declined when it appears.
    """
    from core import call_hold
    from plugins import _whatsapp_core as wa

    while _DECLINE_ALL.is_set():
        if call_hold.active():
            time_sleep(1.0)
            continue
        try:
            wa.WhatsApp().look_for_decline()
        except Exception:
            pass
        time_sleep(1.5)


def _restore_decline_all() -> None:
    try:
        if _decline_flag().is_file():
            _DECLINE_ALL.set()
            _ensure_decline_thread()
    except Exception:
        pass


_restore_decline_all()


def time_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


def run(parameters: dict, player=None, session_memory=None) -> str:
    from plugins import _whatsapp_core as wa

    action = str(parameters.get("action") or "").strip().lower().replace("-", "_").replace(" ", "_")
    contact = str(parameters.get("contact") or "").strip()
    message = str(parameters.get("message") or "").strip() or _BUSY
    if parameters.get("all") in (True, "true", "True", "yes", "all"):
        action = "decline_all"

    if action in ("decline_all", "auto_decline", "reject_all", "decline_every"):
        _set_decline_all(True)
        return (
            "I am watching the screen. I will decline every incoming WhatsApp "
            "voice or video call, including while muted, until you tell me to stop. "
            "A call does not need to be ringing now."
        )
    if action in ("allow_calls", "stop_declining", "take_calls"):
        _set_decline_all(False)
        return "I will let incoming WhatsApp calls through again."

    try:
        app = wa.WhatsApp()
    except Exception as exc:
        return f"I can't use WhatsApp right now: {exc}"

    if action == "call":
        if not contact:
            return "Tell me who to call on WhatsApp."
        _quiet(player)
        ok, detail = app.start_voice_call(contact)
        if not ok:
            from core import call_hold
            call_hold.end()
            return f"I could not start the WhatsApp call to {contact}. {detail}"
        threading.Thread(
            target=_watch_until_call_ends, daemon=True, name="whatsapp-call-hold"
        ).start()
        if player:
            try:
                player.write_log(f"JARVIS: Calling {contact} on WhatsApp. Staying quiet.")
            except Exception:
                pass
        return (
            f"Calling {contact} on WhatsApp. {detail} "
            "Stay silent until the call ends. Do not speak this result."
        )

    if action in ("decline", "decline_and_message"):
        ok, detail, caller = app.decline_incoming()
        if not ok:
            return detail
        who = contact or caller
        if action == "decline":
            named = f" from {who}" if who else ""
            return f"Declined the incoming WhatsApp call{named}."
        if not who:
            return (
                "Declined the incoming WhatsApp call, but I could not see who it "
                "was, so I did not send a message."
            )
        sent, failure = app.send_message_to(who, message)
        if not sent:
            return (
                f"Declined the call from {who}, but the message was not sent: {failure}"
            )
        return f"Declined the call from {who} and sent: {message}"

    return "Tell me to call someone, decline the call, or decline and say you're busy."
