"""静默的单条/批量合成 API。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile
from typing import Any, Iterable, Mapping

from . import legacy
from .config import load_config
from .voices import resolve_voice

request_audio = legacy.request_audio


def extract_wav(payload: bytes, destination: str | Path) -> Path:
    target = Path(destination)
    with zipfile.ZipFile(BytesIO(payload)) as archive:
        entries = []
        for item in archive.infolist():
            name = item.filename.replace("\\", "/")
            if name.startswith("/") or ".." in name.split("/") or ":" in name:
                raise RuntimeError("service ZIP contains an unsafe path")
            if not item.is_dir() and Path(name).suffix.lower() == ".wav":
                entries.append(item)
        if len(entries) != 1:
            raise RuntimeError(f"service returned {len(entries)} WAV files, expected 1")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(archive.read(entries[0]))
    return target


def synthesize_one(text: str, output: str | Path, *, voice: str | Path = "付小春", emotion: str | Path | None = None,
                   config: Mapping[str, Any] | None = None, timeout_s: float | None = None,
                   validate_audio: bool = True) -> dict[str, Any]:
    """合成一条文本并返回不含敏感值的结果记录。"""
    cfg = dict(config or load_config())
    cfg["request_timeout"] = timeout_s if timeout_s is not None else cfg.get("request_timeout", 10)
    speaker = resolve_voice(voice)
    emotion_path = resolve_voice(emotion) if emotion else None
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    text_path = target.with_name("." + target.stem + ".request.txt")
    try:
        text_path.write_text(str(text).strip() + "\n", encoding="utf-8")
        payload = request_audio(cfg, speaker, emotion_path, text_path)
        wav = extract_wav(payload, target)
        if validate_audio:
            seconds, peak, fatal, notes = legacy.inspect_audio(target)
            if fatal:
                raise RuntimeError(f"音频校验失败：{fatal}")
        return {"audio_path": str(target), "seconds": seconds if validate_audio else None,
                "peak_dbfs": peak if validate_audio else None, "notes": notes if validate_audio else []}
    finally:
        text_path.unlink(missing_ok=True)


def synthesize_batch(items: Iterable[Mapping[str, Any]], *, output_dir: str | Path,
                     config: Mapping[str, Any] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    results = []
    root = Path(output_dir)
    for index, item in enumerate(items, 1):
        target = root / f"{index:04d}.wav"
        results.append(synthesize_one(str(item.get("text", "")), target, voice=item.get("voice", "付小春"), config=config, **kwargs))
    return results
