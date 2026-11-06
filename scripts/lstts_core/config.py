"""配置发现与敏感字段解析。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"配置文件必须是 JSON 对象：{path}")
    return value


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(name: str = "index_tts.json", path: str | Path | None = None) -> dict[str, Any]:
    """加载配置；返回值不打印、不持久化 token 或 AccessKey。"""
    if name not in {"index_tts.json", "oss.json"}:
        raise ValueError("只支持 index_tts.json 或 oss.json")
    if path is not None:
        payload = _read(Path(path).expanduser())
    elif name == "index_tts.json":
        explicit = os.environ.get("LSTEST_TTS_CONFIG")
        candidates = ([Path(explicit).expanduser()] if explicit else [])
        candidates += [Path.home() / ".lstest" / "tts.json", _skill_root() / "references" / name]
        payload = {}
        for candidate in candidates:
            current = _read(candidate)
            if current:
                payload.update(current)
                if current.get("base_url") or current.get("token"):
                    break
    else:
        candidates = [Path.home() / ".lstest" / "oss.json", _skill_root() / "references" / name]
        payload = {}
        for candidate in candidates:
            current = _read(candidate)
            if current:
                payload.update(current)
                break
    if name == "index_tts.json":
        token = os.environ.get("LSTTS_TTS_TOKEN") or os.environ.get("LSTEST_TTS_TOKEN")
        if token:
            payload["token"] = token
        payload.setdefault("request_timeout", 10)
    else:
        for key in ("access_key_id", "access_key_secret"):
            if os.environ.get(key):
                payload[key] = os.environ[key]
    return payload
