from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

from lstts_core import legacy as _legacy
from lstts_core.legacy import *

_ORIGINAL_CLOUD_RECORDS = _legacy.cloud_records


def _sync_legacy_globals() -> None:
    names = (
        "emit", "config", "default_cloud", "audio_file", "local_records", "cloud_records",
        "inspect_audio", "request_audio", "save_audio", "write_report", "unique_label", "texts_from",
    )
    for name in names:
        setattr(_legacy, name, globals()[name])


def run(job, preview=False):
    _sync_legacy_globals()
    return _legacy.run(job, preview)


def cloud_records(selections):
    _sync_legacy_globals()
    return _ORIGINAL_CLOUD_RECORDS(selections)


def main():
    parser = argparse.ArgumentParser(description="独立 IndexTTS 合成客户端")
    parser.add_argument("--job", required=True, type=Path)
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    try:
        job = json.loads(args.job.read_text(encoding="utf-8-sig"))
        if not isinstance(job, dict):
            raise ValueError("任务 JSON 必须为对象。")
        return run(job, args.preview)
    except KeyboardInterrupt:
        emit(event="error", message="任务已中止。")
        return 130
    except Exception as exc:
        emit(event="error", message=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
