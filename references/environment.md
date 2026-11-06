# lstts-core 配置与环境变量

## 配置文件

- TTS 配置优先级：`LSTEST_TTS_CONFIG`（兼容旧显式路径）> `~/.lstest/tts.json` > `<lstts>/references/index_tts.json`。
- OSS 配置优先级：`~/.lstest/oss.json` > `<lstts>/references/oss.json`。
- URL、请求超时、OSS endpoint、bucket、prefix、metadata 文件名和路径都放在配置文件中，不为这些字段增加环境变量。
- 环境变量中的 token 和 AccessKey 只读入内存，绝不打印或写回文件。

| 变量 | 用途 | 优先级 |
|---|---|---|
| `LSTTS_TTS_TOKEN` | IndexTTS token | 高于 `LSTEST_TTS_TOKEN` 和配置文件 `token` |
| `ACCESS_KEY_ID` | OSS AccessKey ID | 高于 OSS 配置文件值 |
| `ACCESS_KEY_SECRET` | OSS AccessKey Secret | 高于 OSS 配置文件值 |

`LSTEST_TTS_TOKEN` 仍被接受，仅作为 `LSTTS_TTS_TOKEN` 缺省时的兼容来源。

历史变量 `LSTEST_TTS_URL`、`LSTEST_TTS_TIMEOUT`、`LSTEST_TTS_CONFIG`、`LSTEST_VOICE_DIR` 仍可读取以兼容旧调用，但不作为主配置方式。URL、超时和路径请写入配置文件；`LSTEST_TTS_CONFIG` 仅用于指定旧配置文件路径，`LSTEST_VOICE_DIR` 仅用于旧声音目录覆盖。
