"""配置发现与敏感字段解析。"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# 服务地址：新名优先，旧名兼容；两者都为空时回落到配置文件。
BASE_URL_ENV_ORDER = ("LSTTS_TTS_URL", "LSTEST_TTS_URL")
TOKEN_ENV_ORDER = ("LSTTS_TTS_TOKEN", "LSTEST_TTS_TOKEN")


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"配置文件必须是 JSON 对象：{path}")
    return value


def _skill_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _index_tts_candidates() -> list[Path]:
    """按优先级列出 IndexTTS 配置文件：显式路径 > 用户目录 > skill 内置。"""
    explicit = os.environ.get("LSTEST_TTS_CONFIG")
    candidates = ([Path(explicit).expanduser()] if explicit else [])
    candidates += [Path.home() / ".lstest" / "tts.json", _skill_root() / "references" / "index_tts.json"]
    return candidates


def env_base_url() -> str:
    """返回环境变量中的服务地址；LSTTS_TTS_URL 优先于 LSTEST_TTS_URL。

    空字符串或纯空白视为未设置，避免 `set VAR=` 把配置覆盖成空值。
    """
    for key in BASE_URL_ENV_ORDER:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def env_token() -> str:
    """返回环境变量中的 token；LSTTS_TTS_TOKEN 优先于 LSTEST_TTS_TOKEN。"""
    for key in TOKEN_ENV_ORDER:
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return ""


def base_url_hint() -> str:
    """缺少服务地址时给使用者可执行的指引，而不是裸 KeyError。"""
    explicit = os.environ.get("LSTEST_TTS_CONFIG")
    fallback = Path(explicit).expanduser() if explicit else Path.home() / ".lstest" / "tts.json"
    return (
        "缺少 IndexTTS 服务地址：请设置环境变量 LSTTS_TTS_URL"
        "（兼容旧名 LSTEST_TTS_URL），"
        f'或在 {fallback} 写入 {{"base_url": "<服务地址>"}}'
    )


def load_config(name: str = "index_tts.json", path: str | Path | None = None) -> dict[str, Any]:
    """加载配置；返回值不打印、不持久化 token 或 AccessKey。"""
    if name not in {"index_tts.json", "oss.json"}:
        raise ValueError("只支持 index_tts.json 或 oss.json")
    if path is not None:
        payload = _read(Path(path).expanduser())
    elif name == "index_tts.json":
        payload = {}
        for candidate in _index_tts_candidates():
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
        url = env_base_url()
        if url:
            payload["base_url"] = url
        token = env_token()
        if token:
            payload["token"] = token
        payload.setdefault("request_timeout", 10)
    else:
        for key in ("ACCESS_KEY_ID", "ACCESS_KEY_SECRET"):
            if os.environ.get(key):
                payload[key.lower()] = os.environ[key]
    return payload
