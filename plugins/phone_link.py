"""The phone address for this run of Jarvis.

The Cloudflare address changes every time Jarvis starts. It is written to
D:\\Jarvis\\phone_access.txt once the tunnel is up, so a question later in the
session still gets the address that is live now.
"""

import re

PLUGIN = {
    "name": "phone_link",
    "description": (
        "The web address the user must open on their phone to reach Jarvis. "
        "That address changes every time Jarvis is closed and opened again. "
        "Call this when the user asks for the phone link, the remote link, "
        "the link that changes, or how to open Jarvis on their phone. "
        "Say the exact address from the result. Never invent or reuse an old "
        "trycloudflare address."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
}

_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_PASSWORD_RE = re.compile(r"^Password:\s*(\S+)", re.MULTILINE)


def current_link() -> tuple[str, str]:
    """(public address, password). The address is empty until the tunnel is up."""
    from core.drive_scope import save_dir

    path = save_dir() / "phone_access.txt"
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return "", ""
    url = _URL_RE.search(text)
    password = _PASSWORD_RE.search(text)
    return (
        url.group(0) if url else "",
        password.group(1) if password else "",
    )


def run(parameters: dict, player=None, session_memory=None) -> str:
    url, password = current_link()
    if not url:
        return (
            "The phone link is not ready yet. It appears shortly after Jarvis "
            "starts. Ask again in a moment, and call phone_link again then."
        )
    if player:
        try:
            player.write_log(f"JARVIS: Phone link {url}")
        except Exception:
            pass
    password_line = f" The password is {password}." if password else ""
    return (
        f"The phone link right now is {url}.{password_line} "
        "Say that exact address. It changes every time Jarvis is closed and opened."
    )
