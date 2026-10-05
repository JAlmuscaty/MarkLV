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
        "action='decline' clicks Decline on an incoming voice or video call. "
        "action='decline_and_message' declines, then sends a message that the "
        "user is busy and will call later. "
        "Pass the contact name in 'contact'. During an outgoing call Jarvis stays "
        "silent until the call ends; do not keep talking after you start it."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "call | decline | decline_and_message",
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
    "scheduling": "SILENT",
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


def _call_live(app) -> bool:
    try:
        if app.call_in_progress():
            return True
    except Exception:
        return False
    try:
        return app.screen_says_call()
    except Exception:
        return False


def _watch_until_call_ends() -> None:
    """Drop the silence once the call is no longer on screen or on the audio device."""
    from core import call_hold
    from plugins import _whatsapp_core as wa

    try:
        app = wa.WhatsApp()
    except Exception:
        call_hold.end()
        return

    # The ring needs a moment to appear. If it never does, don't stay mute.
    # The picture of the window is only taken once, on the last try.
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
    for _ in range(3600):
        time_sleep(1.0)
        # A picture of the window is the slow check, so only take one after the
        # window and the audio device have both gone quiet for a few seconds.
        try:
            live = app.call_in_progress()
        except Exception:
            live = False
        if live:
            quiet_passes = 0
            continue
        quiet_passes += 1
        if quiet_passes < 4:
            continue
        if _call_live(app):
            quiet_passes = 0
            continue
        break
    call_hold.end()


def time_sleep(seconds: float) -> None:
    import time
    time.sleep(seconds)


def run(parameters: dict, player=None, session_memory=None) -> str:
    from plugins import _whatsapp_core as wa

    action = str(parameters.get("action") or "").strip().lower().replace("-", "_")
    contact = str(parameters.get("contact") or "").strip()
    message = str(parameters.get("message") or "").strip() or _BUSY

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
