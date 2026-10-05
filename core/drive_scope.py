"""Filesystem boundary for assistant actions.

User-directed reads, writes, moves and listings have to land on D:.
The check looks at the path as given and again after links are resolved,
so a shortcut or junction on D: that points at C: is refused too.
Named applications may still be launched; this module only gates paths.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ALLOWED_DRIVE = "D"

# D:\foo, \\?\D:\foo, //?/D:/foo
_DRIVE_RE = re.compile(r"^(?:\\\\[?]\\|[?]\\)?([A-Za-z]):[\\/]")
# \\server\C$\foo  and  \\?\UNC\server\C$\foo
_UNC_SHARE_RE = re.compile(
    r"^(?:\\\\[?]\\UNC\\|\\\\)[^\\]+\\([A-Za-z])\$",
    re.IGNORECASE,
)

_KNOWN_FOLDERS = {
    "desktop":   (0xB4BFCC3A, 0xDB2C, 0x424C, (0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41)),
    "documents": (0xFDD39AD0, 0x238F, 0x46AF, (0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7)),
    "downloads": (0x374DE290, 0x123F, 0x4565, (0x91, 0x64, 0x39, 0xC4, 0x92, 0x5E, 0x46, 0x7B)),
    "pictures":  (0x33E28130, 0x4E1C, 0x467A, (0xAE, 0x68, 0x6A, 0x4F, 0x8A, 0x2D, 0x4A, 0x3E)),
    "music":     (0x4BD8D571, 0x6D19, 0x48D3, (0xBE, 0x97, 0x42, 0x22, 0x20, 0x08, 0x0E, 0x43)),
    "videos":    (0x18989B1D, 0x99B5, 0x455B, (0x84, 0x1C, 0xAB, 0x7C, 0x74, 0xE4, 0xDD, 0xFC)),
}

_FOLDER_NAMES = {
    "desktop": "Desktop",
    "documents": "Documents",
    "downloads": "Downloads",
    "pictures": "Pictures",
    "music": "Music",
    "videos": "Videos",
}


def _clean(path: str | Path) -> str:
    return str(path).strip().strip('"').strip("'")


def stated_drive(path: str | Path) -> str | None:
    """Drive letter written in the path, before resolving links."""
    text = _clean(path)
    match = _DRIVE_RE.match(text)
    if match:
        return match.group(1).upper()
    match = _UNC_SHARE_RE.match(text)
    if match:
        return match.group(1).upper()
    return None


# The letter must not be the tail of a word, or "https://" is read as drive S:.
_DRIVE_ANY_RE = re.compile(r"(?<![A-Za-z])(?:\\\\[?]\\|[?]\\)?([A-Za-z]):[\\/]")
_UNC_ANY_RE = re.compile(
    r"(?:\\\\[?]\\UNC\\|\\\\)[^\\]+\\([A-Za-z])\$",
    re.IGNORECASE,
)


def foreign_drive(text: str | Path) -> str | None:
    """A drive letter other than D: mentioned anywhere in the text, or None."""
    raw = _clean(text)
    for pattern in (_DRIVE_ANY_RE, _UNC_ANY_RE):
        for match in pattern.finditer(raw):
            letter = match.group(1).upper()
            if letter != ALLOWED_DRIVE:
                return letter
    return None


def looks_like_filesystem(path: str | Path) -> bool:
    """True for D:\\..., C:\\... and UNC paths. False for app names and URIs."""
    text = _clean(path)
    if not text:
        return False
    if stated_drive(text):
        return True
    return text.startswith("\\\\") or text.startswith("//")


def _resolved(path: str | Path) -> Path | None:
    try:
        return Path(_clean(path)).expanduser().resolve()
    except Exception:
        return None


def _resolved_drive(path: Path) -> str | None:
    drive = path.drive
    if len(drive) >= 2 and drive[1] == ":":
        return drive[0].upper()
    return stated_drive(str(path))


def is_allowed(path: str | Path) -> bool:
    """True only when both the written path and the resolved path are on D:."""
    text = _clean(path)
    if not text:
        return False
    stated = stated_drive(text)
    if stated is not None and stated != ALLOWED_DRIVE:
        return False
    if (text.startswith("\\\\") or text.startswith("//")) and stated != ALLOWED_DRIVE:
        return False
    resolved = _resolved(text)
    if resolved is None:
        return False
    return _resolved_drive(resolved) == ALLOWED_DRIVE


def denial(path: str | Path) -> str:
    letter = stated_drive(path) or _resolved_drive(_resolved(path) or Path(".")) or "?"
    where = f"{letter}:" if letter not in ("?", "") else "another location"
    return (
        f"Access denied: {path} is on {where}. "
        f"File access is limited to the {ALLOWED_DRIVE}: drive."
    )


def root() -> Path:
    return Path(f"{ALLOWED_DRIVE}:\\")


def save_dir() -> Path:
    """Where the assistant writes when the user did not name a folder.

    Uses D:\\Desktop when that folder exists. Otherwise D:\\Jarvis, which
    is created on first use so nothing is dropped on the root of the drive.
    """
    desktop = root() / "Desktop"
    if desktop.is_dir() and is_allowed(desktop):
        return desktop
    folder = root() / "Jarvis"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _known_folder(name: str) -> Path | None:
    """Windows known-folder path, or None. The caller still has to check the drive."""
    spec = _KNOWN_FOLDERS.get(name)
    if spec is None or os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        data1, data2, data3, data4 = spec
        fid = _GUID(data1, data2, data3, (ctypes.c_ubyte * 8)(*data4))
        buf = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(fid), 0, None, ctypes.byref(buf)) != 0:
            return None
        try:
            return Path(buf.value) if buf.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(buf)
    except Exception:
        return None


def shortcut(name: str) -> Path | None:
    """desktop / documents / downloads / home, but only when that folder is on D:.

    The Windows profile folders usually sit on C:. Those stay unreachable.
    A folder the user has redirected onto D:, or a D:\\Desktop they created,
    is used. ``home`` is the root of D:.
    """
    key = (name or "").strip().lower()
    if key == "home":
        return root()
    known = _known_folder(key)
    if known is not None and known.is_dir() and is_allowed(known):
        return known
    folder_name = _FOLDER_NAMES.get(key)
    if not folder_name:
        return None
    candidate = root() / folder_name
    if candidate.is_dir() and is_allowed(candidate):
        return candidate
    return None


class BoundedPath:
    """pathlib stand-in for generated desktop code. Refuses anything off D:."""

    def __init__(self, *args):
        self._p = args[0] if len(args) == 1 and isinstance(args[0], Path) else Path(*args)
        if not is_allowed(self._p):
            raise PermissionError(denial(self._p))

    def __truediv__(self, other):
        return BoundedPath(self._p / other)

    def __fspath__(self):
        if not is_allowed(self._p):
            raise PermissionError(denial(self._p))
        return os.fspath(self._p)

    def __str__(self):
        return str(self._p)

    def __repr__(self):
        return f"Path({str(self._p)!r})"

    def __getattr__(self, name):
        attr = getattr(self._p, name)
        if isinstance(attr, Path):
            return BoundedPath(attr)
        if not callable(attr):
            return attr

        def wrapped(*args, **kwargs):
            if not is_allowed(self._p):
                raise PermissionError(denial(self._p))
            result = attr(*args, **kwargs)
            if name in ("iterdir", "glob", "rglob"):
                return (BoundedPath(item) for item in result)
            if isinstance(result, Path):
                return BoundedPath(result)
            return result

        return wrapped


def _reject_paths(values) -> None:
    for value in values:
        if isinstance(value, (str, Path, BoundedPath)) and (
            isinstance(value, (Path, BoundedPath)) or looks_like_filesystem(value) or "/" in str(value) or "\\" in str(value)
        ):
            target = value._p if isinstance(value, BoundedPath) else value
            if not is_allowed(target):
                raise PermissionError(denial(target))


def guarded_copy2(src, dst, *args, **kwargs):
    import shutil
    _reject_paths((src, dst))
    return shutil.copy2(os.fspath(src), os.fspath(dst), *args, **kwargs)


def guarded_copytree(src, dst, *args, **kwargs):
    import shutil
    _reject_paths((src, dst))
    return shutil.copytree(os.fspath(src), os.fspath(dst), *args, **kwargs)


def guarded_disk_usage(path):
    import shutil
    _reject_paths((path,))
    return shutil.disk_usage(os.fspath(path))


def guarded_os_path():
    """os.path methods that refuse to inspect anything off D:."""

    def _wrap(fn):
        def inner(*args, **kwargs):
            _reject_paths(args)
            return fn(*args, **kwargs)
        return inner

    return type("os_path", (), {
        "exists": _wrap(os.path.exists),
        "isfile": _wrap(os.path.isfile),
        "isdir": _wrap(os.path.isdir),
        "getsize": _wrap(os.path.getsize),
        "getmtime": _wrap(os.path.getmtime),
        "abspath": _wrap(os.path.abspath),
        "dirname": _wrap(os.path.dirname),
        "basename": _wrap(os.path.basename),
        "join": _wrap(os.path.join),
        "split": _wrap(os.path.split),
        "expanduser": _wrap(os.path.expanduser),
    })()
