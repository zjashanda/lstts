"""文本拆分与 token 粗估算。"""

from __future__ import annotations

import re

CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
WORDS = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)?")
SENTENCE = re.compile(r"(?<=[，。！？；：、,.!?;:])\s*")


def split_text(value: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\r\n、；;]+", str(value)) if part.strip()]


def estimate_tokens(text: str) -> int:
    return len(CJK.findall(text)) + round(len(WORDS.findall(text)) * 1.3) + 1


def split_long(text: str, limit: int) -> list[str]:
    if limit <= 0 or estimate_tokens(text) <= limit:
        return [text]
    parts, buffer = [], ""
    for piece in SENTENCE.split(text):
        if not piece:
            continue
        if buffer and estimate_tokens(buffer + piece) > limit:
            parts.append(buffer)
            buffer = piece
        else:
            buffer += piece
        while estimate_tokens(buffer) > limit:
            cut = max(1, len(buffer) * limit // max(1, estimate_tokens(buffer)))
            space = buffer.rfind(" ", 1, cut + 1)
            if space > 0:
                cut = space
            parts.append(buffer[:cut])
            buffer = buffer[cut:]
    if buffer:
        parts.append(buffer)
    return [part.strip() for part in parts if part.strip()]
