"""声音资源解析。"""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path

VOICE_SUFFIXES = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}


def _package_voice(name: str) -> Path | None:
    resource = importlib.resources.files("lstts_core").joinpath("voices", f"{name}.wav")
    if resource.is_file():
        return Path(resource)
    return None


def resolve_voice(value: str | Path) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError("voice cannot be empty")
    direct = Path(text).expanduser()
    if direct.is_file() and direct.suffix.lower() in VOICE_SUFFIXES:
        return direct.resolve()
    configured = os.environ.get("LSTEST_VOICE_DIR")
    roots = ([Path(configured).expanduser()] if configured else []) + [Path.home() / ".lstest" / "voices"]
    for root in roots:
        for candidate in (root / f"{text}.wav", root / f"{text}{direct.suffix}"):
            if candidate.is_file():
                return candidate.resolve()
    package_path = _package_voice(text)
    if package_path:
        return package_path
    raise RuntimeError(f"voice reference not found: {text}")
