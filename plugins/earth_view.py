"""Live Earth on the display: a globe you can drag, planes, earthquakes, and the ISS.

The picture is streamed. Nothing larger than this file is stored for it.
"""

import socket
import webbrowser

PLUGIN = {
    "name": "earth_view",
    "description": (
        "Opens a live view of Earth on the display. Use when the user asks to "
        "see the Earth, the planet, a globe, planes in the sky, earthquakes, or "
        "the International Space Station. They can drag the globe and switch to "
        "a satellite view. Do not use this for a street address or directions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "behavior": "NON_BLOCKING",
}

_EARTH_URL = "http://127.0.0.1:8002/earth"


def _earth_is_up() -> bool:
    try:
        with socket.create_connection(("127.0.0.1", 8002), timeout=0.4):
            return True
    except OSError:
        return False


def run(parameters: dict, player=None, session_memory=None) -> str:
    if not _earth_is_up():
        return "The Earth view is not up yet, sir. It starts with Jarvis."
    try:
        webbrowser.open(_EARTH_URL)
    except Exception as e:
        return f"I could not open the Earth view, sir. {e}"
    if player:
        try:
            player.write_log("JARVIS: Live Earth is on the display.")
        except Exception:
            pass
    return (
        "Certainly sir. I have put a live view of the planet on your display. "
        "You can drag the globe, and turn planes, earthquakes, and the station on or off."
    )
