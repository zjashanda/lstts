---
name: lstts
description: 'Use ONLY when the user requests IndexTTS/indexTTS 语音合成、音色克隆、情感参考合成，或使用云端音色库合成语音。支持独立 CLI 与 lstts-core Python API。'
---

# IndexTTS 语音合成

本 Skill 保留独立 CLI，同时提供可 pip 安装的 `lstts-core` 包。TTS 的 HTTP、配置、音频校验和声音资源以 `lstts_core` 为单一来源；`scripts/synthesize.py` 只是 CLI 包装层。

## 独立使用

```powershell
python scripts\synthesize.py --job <job.json> --preview
python scripts\synthesize.py --job <job.json>
```

保持原有 `--job` JSON 合同和 JSONL 事件流：`preview`、`progress`、`item_result`、`complete`。退出码：0 成功，1 任务级错误，2 部分/全部音频失败，130 中止。Windows 运行仍使用 `scripts/run-hidden.ps1`，避免桌面弹出终端。

## Python API

```python
from lstts_core import inspect_wav, load_config, resolve_voice, synthesize_batch, synthesize_one

config = load_config()
voice = resolve_voice("付小春")
result = synthesize_one("你好，世界", "output/hello.wav", voice=voice, config=config)
```

API 保持安静：不打印、不解析 CLI、不 `sys.exit`。`openpyxl`、`xlrd`、`oss2` 仅在相关功能执行时导入。

## 安装

```powershell
pip install "lstts-core @ git+https://github.com/zjashanda/lstts.git@main"
```

## 配置与环境变量

配置位置和完整优先级见 [references/environment.md](references/environment.md)。主环境变量如下：

| 变量 | 用途 |
|---|---|
| `LSTTS_TTS_TOKEN` | IndexTTS token |
| `ACCESS_KEY_ID` | OSS AccessKey ID |
| `ACCESS_KEY_SECRET` | OSS AccessKey Secret |

`LSTEST_TTS_TOKEN` 作为旧 token 变量继续接受，但优先级低于 `LSTTS_TTS_TOKEN`。OSS key 是环境变量优先于配置文件。URL、endpoint、bucket、prefix、请求超时、metadata 文件名和路径写在配置文件中，不新增对应环境变量。历史 `LSTEST_TTS_URL`、`LSTEST_TTS_TIMEOUT`、`LSTEST_TTS_CONFIG`、`LSTEST_VOICE_DIR` 仍可读取以兼容旧调用，但不作为主配置方式。

## 输入与声音

支持直接文本、TXT/XLSX/XLS、本地声音文件或目录、OSS 云端声音筛选和单个情感参考音频。内置声音为 `付小春`、`小宁`，资源位于 `scripts/lstts_core/voices/`，通过 `importlib.resources` 解析，源码树和 wheel 安装均可用。

不要把 token、AccessKey 写入任务 JSON、日志、报告或对话。
