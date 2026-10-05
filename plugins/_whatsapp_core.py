"""Drive the WhatsApp window on this PC.

The voice-call control is clicked on its own rectangle. When WhatsApp does not
expose that control, a reading of the window returns the telephone icon's
pixel and that point is clicked. A corner of the window is never assumed.
"""

from __future__ import annotations

import json
import re
import subprocess
import time

_VOICE_NAMES = (
    "voice call",
    "audio call",
    "phone call",
    "sesli arama",
    "sesli ara",
)
_VIDEO_MARKS = ("video", "görüntülü", "goruntulu", "camera")
_DECLINE_NAMES = (
    "decline",
    "reject",
    "reddet",
    "aramayı reddet",
    "aramayi reddet",
    "decline call",
)
_CALL_MARKS = (
    "end call",
    "hang up",
    "aramayı sonlandır",
    "aramayi sonlandir",
    "ringing",
    "calling",
    "aranıyor",
    "araniyor",
    "çalıyor",
    "caliyor",
    "incoming voice",
    "incoming video",
    "gelen arama",
)
_SEARCH_NAMES = (
    "search or start a new chat",
    "ara veya yeni sohbet başlat",
    "ara veya yeni sohbet baslat",
)
_MESSAGE_NAMES = (
    "type a message",
    "bir mesaj yazın",
    "bir mesaj yazin",
)
_BUSY_MESSAGE = "I'm busy right now. I'll call you later."
# True when WhatsApp was already playing audio before this call was placed,
# so an always-on session is not mistaken for the call itself.
_AUDIO_WAS_ACTIVE = False


def get():
    """(transport, reason). send_message uses this. None means WhatsApp is not up."""
    try:
        app = WhatsApp()
    except Exception as exc:
        return None, str(exc)
    if not app.available():
        return None, "WhatsApp is not open and could not be started."
    return app, ""


class WhatsApp:
    def available(self) -> bool:
        return self._window(wait=2.0) is not None or self._launch()

    def send_message_to(self, receiver: str, message: str) -> tuple[bool, str]:
        win = self._require_window()
        if win is None:
            return False, "WhatsApp is not open."
        opened, why = self._open_chat(win, receiver)
        if not opened:
            return False, why
        win = self._window() or win
        if not self._chat_visible(win, receiver):
            return False, f"WhatsApp did not open a chat named {receiver}."
        return self._type_and_send(win, message)

    def start_voice_call(self, contact: str) -> tuple[bool, str]:
        global _AUDIO_WAS_ACTIVE
        _AUDIO_WAS_ACTIVE = self._whatsapp_audio_active()
        win = self._require_window()
        if win is None:
            return False, "WhatsApp is not open."
        opened, why = self._open_chat(win, contact)
        if not opened:
            return False, why
        win = self._window() or win
        self._raise(win)
        ctrl = self._find_named(win, _VOICE_NAMES, reject=_VIDEO_MARKS)
        if ctrl is not None:
            if not self._chat_visible(win, contact):
                return False, f"WhatsApp did not open a chat named {contact}."
            point = self._click_control(ctrl)
            return True, (
                f"Voice call button at {point[0]}, {point[1]} "
                "(the button named voice call)."
            )
        point, how = self._icon_point(
            win,
            (
                "This is a WhatsApp window. The open chat should be with "
                f"{contact!r}. Find the voice call button: the telephone handset "
                "in that chat's header. It is not the video camera. "
                "Reply with JSON only: "
                '{"found": true, "chat_matches": true, "x": <pixels from the left>, '
                '"y": <pixels from the top>}. '
                'If this is not that chat, or the handset is not visible, reply '
                '{"found": false, "chat_matches": false}.'
            ),
        )
        if point is None:
            return False, how
        self._click_screen(point[0], point[1])
        return True, f"Voice call button at {point[0]}, {point[1]} ({how})."

    def decline_incoming(self) -> tuple[bool, str, str]:
        """(ok, detail, caller name)."""
        win = self._call_surface()
        if win is None:
            return False, "There is no incoming WhatsApp call on screen.", ""
        self._raise(win)
        caller = self._caller_name(win)
        ctrl = self._find_named(win, _DECLINE_NAMES, reject=_VOICE_NAMES)
        if ctrl is not None:
            self._click_control(ctrl)
            return True, "Declined the incoming call.", caller
        point, how = self._icon_point(
            win,
            (
                "This is a WhatsApp incoming voice or video call. Find the Decline "
                "button (it may say Decline, Reject, or Reddet). Do not choose "
                "Accept. Reply with JSON only: "
                '{"found": true, "x": <pixels from the left>, "y": <pixels from the top>, '
                '"caller": "<the caller\'s name>"}. '
                'If there is no incoming call, reply {"found": false}.'
            ),
        )
        if point is None:
            return False, how, caller
        self._click_screen(point[0], point[1])
        if not caller and how.startswith("caller:"):
            caller = how.split(":", 1)[1].strip()
            how = "the decline button"
        return True, f"Declined the incoming call ({how}).", caller

    def call_in_progress(self) -> bool:
        win = self._window()
        if win is not None:
            blob = " ".join(self._texts(win)).lower()
            if any(mark in blob for mark in _CALL_MARKS):
                return True
        # A session that was already running before we clicked is not this call.
        return self._whatsapp_audio_active() and not _AUDIO_WAS_ACTIVE

    def _require_window(self):
        win = self._window(wait=1.0)
        if win is not None:
            self._raise(win)
            return win
        if self._launch():
            win = self._window(wait=8.0)
            if win is not None:
                self._raise(win)
            return win
        return None

    def _launch(self) -> bool:
        try:
            subprocess.Popen(
                ["cmd", "/c", "start", "", "whatsapp:"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            return False
        return self._window(wait=8.0) is not None

    def _window(self, wait: float = 0.0):
        from pywinauto import Desktop

        deadline = time.time() + max(0.0, wait)
        while True:
            for win in Desktop(backend="uia").windows():
                title = (win.window_text() or "").strip().lower()
                if title.startswith("whatsapp"):
                    return win
            if time.time() >= deadline:
                return None
            time.sleep(0.4)

    def _call_surface(self):
        from pywinauto import Desktop

        for win in Desktop(backend="uia").windows():
            title = (win.window_text() or "").strip().lower()
            if "whatsapp" not in title and "arama" not in title and "call" not in title:
                continue
            if self._find_named(win, _DECLINE_NAMES, reject=()):
                return win
            blob = " ".join(self._texts(win)).lower()
            if any(mark in blob for mark in ("incoming", "gelen arama", "ringing", "aranıyor", "araniyor")):
                return win
        return self._window()

    def _raise(self, win) -> None:
        try:
            if win.is_minimized():
                win.restore()
        except Exception:
            pass
        try:
            win.set_focus()
        except Exception:
            pass
        time.sleep(0.3)

    def _open_chat(self, win, name: str) -> tuple[bool, str]:
        name = (name or "").strip()
        if not name:
            return False, "No contact name was given."
        self._raise(win)
        box = self._find_named(win, _SEARCH_NAMES, reject=())
        if box is None:
            box = self._first_edit(win)
        if box is not None:
            try:
                box.click_input()
            except Exception:
                pass
        else:
            try:
                win.type_keys("^f")
            except Exception:
                return False, "I could not find WhatsApp's search box."
        time.sleep(0.2)
        self._replace_field(name)
        time.sleep(0.8)
        try:
            win.type_keys("{ENTER}")
        except Exception:
            return False, f"I could not open the chat with {name}."
        time.sleep(0.6)
        return True, ""

    def _chat_is(self, win, name: str) -> bool:
        """True when the open chat's readable text contains this contact."""
        blob = " ".join(self._texts(win)).lower()
        return name.strip().lower() in blob

    def _type_and_send(self, win, message: str) -> tuple[bool, str]:
        message = (message or "").strip()
        if not message:
            return False, "There is no message to send."
        self._raise(win)
        box = self._find_named(win, _MESSAGE_NAMES, reject=())
        if box is None:
            edits = self._edits(win)
            box = edits[-1] if edits else None
        if box is not None:
            try:
                box.click_input()
            except Exception:
                pass
        self._replace_field(message)
        time.sleep(0.2)
        before = ""
        if box is not None:
            try:
                before = (box.window_text() or "").strip()
            except Exception:
                before = ""
        try:
            win.type_keys("{ENTER}")
        except Exception:
            return False, "I could not press Enter to send the message."
        time.sleep(0.4)
        if box is not None:
            try:
                after = (box.window_text() or "").strip()
            except Exception:
                after = None
            if after is not None and before:
                if message.lower() in after.lower():
                    return False, "The message is still in the box, so it was not sent."
                return True, ""
        if self._message_visible(win, message):
            return True, ""
        return False, "I could not confirm WhatsApp sent the message."

    def _chat_visible(self, win, name: str) -> bool:
        if self._chat_is(win, name):
            return True
        data = self._ask_window(
            win,
            "This is a WhatsApp window. Is the open conversation with "
            f"{name!r}? Reply with JSON only: "
            '{"chat_matches": true} or {"chat_matches": false}.',
        )
        return bool(data and data.get("chat_matches") is True)

    def _message_visible(self, win, message: str) -> bool:
        data = self._ask_window(
            win,
            "This is a WhatsApp chat. Is this text the latest outgoing message, "
            f"shown as sent: {message!r}? Reply with JSON only: "
            '{"sent": true} or {"sent": false}.',
        )
        return bool(data and data.get("sent") is True)

    def screen_says_call(self) -> bool:
        """True when the WhatsApp window itself shows a ringing or live call."""
        win = self._window()
        if win is None:
            return False
        data = self._ask_window(
            win,
            "This is a WhatsApp window. Is a voice or video call ringing or "
            "connected right now (an end-call button, a timer, or 'ringing')? "
            'Reply with JSON only: {"calling": true} or {"calling": false}.',
        )
        return bool(data and data.get("calling") is True)

    def _ask_window(self, win, prompt: str) -> dict | None:
        import io

        from google.genai import types
        from PIL import ImageGrab

        from core import gemini

        try:
            rect = win.rectangle()
            image = ImageGrab.grab(bbox=(rect.left, rect.top, rect.right, rect.bottom))
        except Exception:
            return None
        shown = image.copy()
        shown.thumbnail((1280, 800))
        self._last_scale = (
            rect.left,
            rect.top,
            image.size[0] / shown.size[0],
            image.size[1] / shown.size[1],
            shown.size,
        )
        buf = io.BytesIO()
        shown.convert("RGB").save(buf, format="JPEG", quality=85)
        part = types.Part.from_bytes(data=buf.getvalue(), mime_type="image/jpeg")
        try:
            reply = gemini.call([prompt, part], tier=gemini.SMART, timeout_ms=40_000)
        except Exception:
            return None
        raw = (getattr(reply, "text", None) or "").strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
        return data if isinstance(data, dict) else None

    def _icon_point(self, win, prompt: str) -> tuple[tuple[int, int] | None, str]:
        """Pixel of a control inside this window, from a reading of the window."""
        data = self._ask_window(win, prompt)
        if not data:
            return None, "I could not identify the button on the WhatsApp window."
        if not data.get("found") or data.get("chat_matches") is False:
            return None, "The button is not on that WhatsApp chat."
        scale = getattr(self, "_last_scale", None)
        if scale is None:
            return None, "I could not identify the button on the WhatsApp window."
        left, top, scale_x, scale_y, shown_size = scale
        try:
            x = int(data["x"])
            y = int(data["y"])
        except (KeyError, TypeError, ValueError):
            return None, "I could not identify the button on the WhatsApp window."
        if not (0 <= x <= shown_size[0] and 0 <= y <= shown_size[1]):
            return None, "The button location was off the window."
        caller = str(data.get("caller") or "").strip()
        how = f"caller:{caller}" if caller else "the icon identified in the window"
        return (int(left + x * scale_x), int(top + y * scale_y)), how

    def _find_named(self, win, names: tuple[str, ...], reject: tuple[str, ...]):
        wanted = tuple(n.lower() for n in names)
        blocked = tuple(n.lower() for n in reject)
        try:
            controls = win.descendants()
        except Exception:
            return None
        for ctrl in controls:
            try:
                text = (ctrl.window_text() or "").strip().lower()
            except Exception:
                continue
            if not text or any(mark in text for mark in blocked):
                continue
            if any(text == name or text.startswith(name) for name in wanted):
                return ctrl
        return None

    def _edits(self, win) -> list:
        try:
            return list(win.descendants(control_type="Edit"))
        except Exception:
            return []

    def _first_edit(self, win):
        edits = self._edits(win)
        return edits[0] if edits else None

    def _texts(self, win) -> list[str]:
        out = []
        try:
            controls = win.descendants()
        except Exception:
            return out
        for ctrl in controls:
            try:
                text = (ctrl.window_text() or "").strip()
            except Exception:
                continue
            if text:
                out.append(text)
        return out

    def _caller_name(self, win) -> str:
        skip = set(_DECLINE_NAMES) | set(_VOICE_NAMES) | {
            "accept", "kabul", "answer", "whatsapp", "video call", "görüntülü arama",
        }
        for text in self._texts(win):
            low = text.lower()
            if low in skip or any(mark in low for mark in _VIDEO_MARKS):
                continue
            if any(mark in low for mark in _CALL_MARKS):
                continue
            if 1 < len(text) < 60:
                return text
        return ""

    def _click_control(self, ctrl) -> tuple[int, int]:
        rect = ctrl.rectangle()
        point = (int((rect.left + rect.right) / 2), int((rect.top + rect.bottom) / 2))
        try:
            ctrl.click_input()
        except Exception:
            self._click_screen(point[0], point[1])
        return point

    def _click_screen(self, x: int, y: int) -> None:
        import ctypes
        user32 = ctypes.windll.user32
        user32.SetCursorPos(int(x), int(y))
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        user32.mouse_event(0x0004, 0, 0, 0, 0)

    def _replace_field(self, text: str) -> None:
        import pyautogui
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "a")
        pyautogui.hotkey("ctrl", "v")

    def _whatsapp_audio_active(self) -> bool:
        """True while WhatsApp itself is playing or capturing audio."""
        try:
            from pycaw.pycaw import AudioUtilities
        except Exception:
            return False
        try:
            sessions = AudioUtilities.GetAllSessions()
        except Exception:
            return False
        for session in sessions:
            proc = getattr(session, "Process", None)
            if proc is None:
                continue
            try:
                name = (proc.name() or "").lower()
            except Exception:
                continue
            if "whatsapp" not in name:
                continue
            state = getattr(session, "State", None)
            if state is None:
                state = getattr(session, "state", None)
            if state == 1:
                return True
        return False
