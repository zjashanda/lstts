# lstts

Use ONLY when the user requests IndexTTS/indexTTS 语音合成、音色克隆、情感参考合成，或使用云端音色库合成语音。支持独立 CLI 与 lstts-core Python API。

## Skill layout

- `pyproject.toml`
- `references/environment.md`
- `references/index_tts.json`
- `references/input-format.md`
- `references/oss.json`
- `requirements.txt`
- `scripts/lstts_core/__init__.py`
- `scripts/lstts_core/audio.py`
- `scripts/lstts_core/client.py`
- `scripts/lstts_core/config.py`
- `scripts/lstts_core/legacy.py`
- `scripts/lstts_core/report.py`
- `scripts/lstts_core/text.py`
- `scripts/lstts_core/voices/付小春.wav`
- `scripts/lstts_core/voices/小宁.wav`
- `scripts/lstts_core/voices.py`
- `scripts/run-hidden.ps1`
- `scripts/synthesize.py`
- `SKILL.md`
- `tests/test_synthesize.py`

## Install the skill

Copy this folder into:

```text
~/.codex/skills/lstts
~/.config/opencode/skills/lstts
```

Then restart Codex or OpenCode.

## Usage and workflow

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

## 被其他 Skill 复用与更新

其他 Skill 通过 Git 安装：

```powershell
pip install "lstts-core @ git+https://github.com/zjashanda/lstts.git@main"
```

更新时只需更新本仓库，然后在消费方 venv 中执行：

```powershell
pip install -U --force-reinstall --no-cache-dir "lstts-core @ git+https://github.com/zjashanda/lstts.git@main"
```

- 不需要修改消费方 Skill 代码。
- 多个 Skill 共用 venv 时执行一次即可。
- 固定版本时把 `@main` 换成对应 tag，例如 `@v1.0.0`。
- 检查版本：

```powershell
python -c "import lstts_core; print(lstts_core.__version__)"
```

## 配置与环境变量

配置位置和完整优先级见 [references/environment.md](references/environment.md)。主环境变量如下：

| 变量 | 用途 |
|---|---|
| `LSTTS_TTS_URL` | IndexTTS 服务地址（优先级最高，配置文件兜底） |
| `LSTTS_TTS_TOKEN` | IndexTTS token |
| `ACCESS_KEY_ID` | OSS AccessKey ID |
| `ACCESS_KEY_SECRET` | OSS AccessKey Secret |

服务地址优先级：`LSTTS_TTS_URL` > `LSTEST_TTS_URL`（旧名）> `LSTEST_TTS_CONFIG` 指向的文件 > `~/.lstest/tts.json` > `references/index_tts.json`。新机器只设置 `LSTTS_TTS_URL` 即可合成，不必手写配置文件；配置文件仍是兜底。token 优先级：`LSTTS_TTS_TOKEN` > `LSTEST_TTS_TOKEN` > 配置文件 `token`。OSS key 是环境变量优先于配置文件。请求超时、OSS endpoint、bucket、prefix、metadata 文件名和路径写在配置文件中。缺少服务地址时，CLI 与 API 都会报出"设置哪个变量、改哪个文件"的指引，而不是裸 `KeyError`。

## 输入与声音

支持直接文本、TXT/XLSX/XLS、本地声音文件或目录、OSS 云端声音筛选和单个情感参考音频。内置声音为 `付小春`、`小宁`，资源位于 `scripts/lstts_core/voices/`，通过 `importlib.resources` 解析，源码树和 wheel 安装均可用。

不要把 token、AccessKey 写入任务 JSON、日志、报告或对话。
