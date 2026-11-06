"""可复用的 IndexTTS 合成核心 API。"""

__version__ = "1.0.0"

from .audio import inspect_wav
from .config import load_config
from .client import synthesize_one, synthesize_batch
from .voices import resolve_voice

__all__ = [
    "__version__",
    "load_config",
    "resolve_voice",
    "synthesize_one",
    "synthesize_batch",
    "inspect_wav",
]
