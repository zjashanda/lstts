# 任务格式

本地示例：
```json
{
  "text": "你好、欢迎；再见，朋友",
  "speaker": "D:/voices",
  "emotion": "D:/emotion/happy.wav",
  "output": "D:/audio-output"
}
```

text 与 text_file 必须二选一；speaker 与 cloud 必须二选一，两者都不写时使用默认音色。

默认音色（不写 speaker/cloud 时）：
- `gender`: `male`（默认）→ 付小春；`female` → 小宁；`both` → 付小春 + 小宁。
- 该映射固定在 `scripts/synthesize.py` 的 `DEFAULT_VOICES`，不要按信息表顺序临时挑人。

```json
{ "text": "打开空调", "gender": "both" }
```

云端按姓名精确指定（不做顺序兜底，匹配数不等于 1 直接报错）：
```json
{ "text": "打开空调", "cloud": [ { "name": "付小春" }, { "name": "小宁" } ] }
```

`output` 省略时输出到**当前工作目录/index_tts_output**；用 run-hidden.ps1 时其 `-WorkDir` 即当前工作目录，默认取调用者所在目录。

可选控制项：
- `max_text_tokens`：正整数，默认 70；估算超过该值的单条文本会按句读标点自动切成多段。设为 0 关闭。中文约 1 字 1 token，西文按词折算。
- `validate_audio`：布尔，默认 true；校验返回 WAV 的时长、静音和削波。
- `output`：默认当前工作目录下的 index_tts_output。

```json
{
  "text": "很长的段落……",
  "speaker": "D:/voices",
  "max_text_tokens": 70,
  "validate_audio": true
}
```

云端示例：
```json
{
  "text_file": "D:/input.xlsx",
  "cloud": [
    {"gender": "male", "age": "adult", "count": 2},
    {"gender": "female", "age": "elder", "count": 1, "provinces": ["广东"]}
  ]
}
```

gender: male/female/all，缺省 male；age: adult/elder/all，缺省 adult。count 为正整数或“全部”。provinces 缺省不限，指定时按信息表“省份”精确匹配。多组条件若选中重复对象，报错要求调整，避免重复计数。

TXT 依次按 UTF-8（允许 BOM）、GB18030、UTF-16 读取，不能有制表符。XLSX/XLS 读取首个工作表，以第一行为表头，必须包含“文本”；“合成数量”列可存在但任何行（含文本为空的行）都不得填写数量。所有来源统一按换行、顿号、中英文分号拆分，忽略空片段，不按其他标点拆分；仅当单条估算超过 max_text_tokens 时，才按句读标点二次切分。

配置位于 references：index_tts.json 使用 base_url/token/request_timeout；oss.json 使用 access_key_id/access_key_secret/endpoint/bucket/prefix/metadata_file。脚本不输出这些值。其中 base_url 也可由环境变量 `LSTTS_TTS_URL`（旧名 `LSTEST_TTS_URL`）提供，优先级高于配置文件。

输出为 output/时间戳_任务名/，音频按音色分目录；云端参考保存在该任务的“参考音频”目录；合成结果.xlsx 记录每条文本的成功、超时、失败、下载失败、音频校验失败或中止。没有音频的行路径为空。前 13 列为固定字段，末尾追加“音频时长(秒)”“峰值(dBFS)”“校验结论”。每次请求仅一条文本，串行执行。request_timeout 默认 10，单位秒；超时主动断连后继续下一条；中断时立即停止提交并在 finally 补写一次报告，不再补写剩余条目。
