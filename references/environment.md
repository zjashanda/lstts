# lstts-core 配置与环境变量

## 服务地址（base_url）

优先级（高 → 低）：

1. `LSTTS_TTS_URL`
2. `LSTEST_TTS_URL`（兼容旧名）
3. `LSTEST_TTS_CONFIG` 指向的配置文件
4. `~/.lstest/tts.json`
5. `<lstts>/references/index_tts.json`

新机器只需设置 `LSTTS_TTS_URL`，不必手写配置文件；配置文件仍是兜底。变量为空或纯空白视为未设置。CLI（`scripts/synthesize.py`）与 `lstts_core` API 使用同一套优先级。

两者都没有时，`load_config()` 仍返回配置字典（不含 `base_url`），实际合成会抛出可读错误：

```text
缺少 IndexTTS 服务地址：请设置环境变量 LSTTS_TTS_URL（兼容旧名 LSTEST_TTS_URL），或在 <路径> 写入 {"base_url": "<服务地址>"}
```

## 其他配置

- OSS 配置优先级：`~/.lstest/oss.json` > `<lstts>/references/oss.json`。
- 请求超时、OSS endpoint、bucket、prefix、metadata 文件名和路径都放在配置文件中，不为这些字段增加环境变量。
- 环境变量中的 token 和 AccessKey 只读入内存，绝不打印或写回文件。

| 变量 | 用途 | 优先级 |
|---|---|---|
| `LSTTS_TTS_URL` | IndexTTS 服务地址 | 最高，覆盖所有配置文件 |
| `LSTEST_TTS_URL` | IndexTTS 服务地址旧名 | 低于 `LSTTS_TTS_URL`，高于配置文件 |
| `LSTTS_TTS_TOKEN` | IndexTTS token | 高于 `LSTEST_TTS_TOKEN` 和配置文件 `token` |
| `LSTEST_TTS_TOKEN` | IndexTTS token 旧名 | 低于 `LSTTS_TTS_TOKEN`，高于配置文件 |
| `ACCESS_KEY_ID` | OSS AccessKey ID | 高于 OSS 配置文件值 |
| `ACCESS_KEY_SECRET` | OSS AccessKey Secret | 高于 OSS 配置文件值 |

`LSTEST_TTS_CONFIG` 仍可用于指定旧配置文件路径，`LSTEST_VOICE_DIR` 仍可作为旧声音目录覆盖。
