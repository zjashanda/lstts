"""WAV 读取、保存与基本校验。"""

from __future__ import annotations

import math
import sys
import wave
from array import array
from pathlib import Path
from typing import Any


def inspect_wav(path: str | Path, *, strict: bool = False) -> dict[str, Any]:
    path = Path(path)
    with wave.open(str(path), "rb") as handle:
        rate, frames, width, channels = handle.getframerate(), handle.getnframes(), handle.getsampwidth(), handle.getnchannels()
        data = handle.readframes(frames)
    duration = frames / rate if rate else 0.0
    peak_db = -120.0
    mean_db = -120.0
    if width == 2 and data:
        samples = array("h")
        samples.frombytes(data[:len(data) - len(data) % 2])
        if sys.byteorder == "big":
            samples.byteswap()
        peak = max(abs(min(samples)), abs(max(samples))) if samples else 0
        square = sum(value * value for value in samples) / len(samples) if samples else 0
        peak_db = 20 * math.log10(peak / 32768) if peak else -120.0
        mean_db = 10 * math.log10(square / (32768 ** 2)) if square else -120.0
    metadata = {
        "container": "wav", "codec": {1: "pcm_u8", 2: "pcm_s16le", 3: "pcm_s24le", 4: "pcm_s32le"}.get(width, f"pcm_{width * 8}"),
        "sample_rate": rate, "channels": channels, "duration_seconds": round(duration, 6),
        "mean_volume_db": round(mean_db, 1), "peak_volume_db": round(peak_db, 1),
    }
    if strict and not (width == 2 and duration > 0.2 and mean_db > -60.0 and peak_db <= 0.0):
        raise RuntimeError(f"IndexTTS output validation failed: metadata={metadata}")
    return metadata
