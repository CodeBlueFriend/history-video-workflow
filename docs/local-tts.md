# 中文历史故事本地配音

本工程采用 Qwen3-TTS：VoiceDesign 生成候选 → 保存参考音频和文字 → Base 克隆长稿。全部在本机运行，无收费语音 API。模型质量需在使用者环境中实测。

## 环境与安装

在项目根目录运行命令。使用独立 `.venv`，不修改系统 Python。复现环境使用：

```bash
./scripts/setup.sh
.venv/bin/history-tts doctor --output reports/environment.json
```

需要 `uv`、Python 3.12 与 `ffmpeg`。`requirements.lock` 固定 Python 依赖；`pyproject.toml` 是直接依赖。默认选择 MPS，float32，eager；CPU 回退需显式修改配置中的 device 为 cpu，避免静默变成极慢任务。CPU 保持 float32。CUDA 机器可以单独配置，当前未验证。

`qwen-tts` 导入时可能提示缺少 FlashAttention 或 SoX。本工程不启用 FlashAttention，音频后处理使用 FFmpeg；如果未来功能实际调用 SoX，需另装二进制，不能把 Python sox 包当作可执行程序。

## 下载和模型位置

```bash
.venv/bin/history-tts download
```

模型默认保存在 `~/.cache/history-tts/models`，不在 Git 中；在 `configs/default.json` 的 model_cache 修改。模型 commit 已固定，后续生成只访问本地模型。支持 models.design.path / models.base.path 指定本地目录，同时必须填写明确 revision。官方也提供 ModelScope 下载方式，见 [官方文档](https://github.com/QwenLM/Qwen3-TTS)。

网络阻塞时可禁用 Hugging Face Xet 后重试（缓存断点保留）：

```bash
HF_HUB_DISABLE_XET=1 .venv/bin/history-tts download
```

ModelScope 加速下载并校验官方固定版本（本机已安装 modelscope，锁文件包含依赖）：

```bash
./scripts/download_modelscope.sh
```

脚本逐文件校验与固定 Hugging Face commit 的 SHA-256 / Git blob 哈希一致后，才将本地目录写入配置。不一致则中止，不冒充同版本。

所有相对配置路径均相对于配置文件所在目录，命令行稿件和输出路径相对于当前工作目录。

## 三种候选与试听

```bash
.venv/bin/history-tts design
open voices/steady/reference.wav
open voices/warm/reference.wav
open voices/weathered/reference.wav
```

候选共用 `examples/voice_audition.txt`，约一分钟目标长度，实际时长由模型决定。包含普通旁白、情绪转折、公元208年和曹操、鲁肃、周瑜、诸葛亮、荆州等专名。单独生成可加 `--only steady`。同配置已有成功音色自动跳过；配置改变时拒绝覆盖，保留长期参考。若希望重新设计，复制配置，将 voices_dir 改为一个新目录。

`voices/<编号>/` 保存 reference.wav、reference.txt、original.txt、voice.json、generation.jsonl。元数据记录模型版本、运行精度、描述、采样参数、种子、音频哈希、耗时和质量检查。暂时默认 steady；最终以人工试听为准。

逐字对照 reference.wav 与 reference.txt，若存在错读/漏读应修改文本为音频真实转写，或弃用该样音。确认准确后运行：

```bash
.venv/bin/history-tts confirm-reference steady
.venv/bin/history-tts set-default warm
```

自动生成并不证明音频内容与输入逐字一致。未确认仍允许流程试跑，任务清单会记录该状态。

## 配音、恢复与局部重生成

```bash
.venv/bin/history-tts speak examples/multi.txt --voice steady --output runs/demo
.venv/bin/history-tts speak examples/restart.txt --voice steady --output runs/restart
```

第二条在独立进程重新加载同一参考，生成新文本，不重新设计音色。

主动暂停、恢复：

```bash
.venv/bin/history-tts speak examples/multi.txt --voice steady --output runs/resume --limit 1
.venv/bin/history-tts speak examples/multi.txt --voice steady --output runs/resume
```

也可 Ctrl-C 中断，再执行原命令。已完成段落通过内容及文件哈希校验后复用。每段最多重试两次（共三次尝试），错误记录在 JSONL 和 manifest。模型加载失败也会报告，不会写成功状态。

先查看 `runs/demo/manifest.json` 中真实段号，然后：

```bash
.venv/bin/history-tts regen --output runs/demo --segments p00002
# 改稿后，使用原输出目录再执行 speak：
.venv/bin/history-tts speak examples/multi.txt --voice steady --output runs/demo --regenerate p00002
```

段号首次按顺序分配。修改/插入后，文字未变的段保留旧编号，新文字获得新编号；重复段按出现顺序匹配。播放顺序始终看 order，不能按编号排序。句子按完整句末标点合并，超过 max_chars 的单句仍保持完整；超过600字的无句末长句要求人工补标点。

文本变化只失效相关段落；参考音频/文字、模型版本、采样参数、运行精度、响度目标变化使相关音频失效；只改停顿重新拼接即可。原稿每个版本保留在 sources/；original.txt 是当前快照。发音规则放在 configs/pronunciation.json，最长短语匹配、单遍替换，不修改原稿。review_only 的拼音仅是试听检查提示，不是模型 SSML 控制。

## 输出与视频接口

每个任务目录包含：

- narration.wav：完整旁白，24 kHz、单声道、16-bit PCM。
- segments/：统一响度后的分段音频；raw/：模型原始音频。
- original.txt、spoken.txt、sources/：原稿、实际送入模型的朗读文本、原稿历史快照。
- manifest.json：每段原文、朗读文字、字符位置和替换映射、编号、顺序、音色、状态、文件路径、音频质量、实际样本数、起止时间、耗时。
- generation.jsonl：重试、缓存命中、失败及总耗时日志。

响度使用 FFmpeg EBU R128 两遍测量，目标 -20 LUFS、真峰值 -2 dB；输出记录实测值。短音频/极端动态不保证恰好达到目标，请查看 loudness。段间停顿默认0.45秒。未实现语速调整，不改音高。失败/暂停时不留下旧的完整 narration.wav 冒充新结果；源分段保留用于恢复。同一输出目录禁止并发写入。

时间线来自实际解码样本数，不包含伪造字词时间戳。强制对齐接口预留在 manifest.alignment：未来消费 narration.wav + original.txt + spoken.txt + 分段映射，输出经过验证的字词时间戳。当前不输出逐字字幕。

## 检查与限制

```bash
.venv/bin/pytest -q
```

基础设施测试使用合成正弦信号验证恢复、局部重生成、有限重试、插入后稳定编号、缓存损坏、参考/发音规则变化、精确拼接样本数和空/静音拒绝。它们不证明 TTS 音质或模型兼容性。

程序检查空音频、NaN、全静音、异常静音段、峰值、可疑字数/时长、接近 token 上限。明显漏读、重复、语义与历史专名发音仍需逐段试听；未部署 ASR，不能声称已自动识别内容错误。未在自身环境验证前，不建议直接投产15—60分钟。

微调、图片、视频合成和字词强制对齐作为后续扩展，不在本次实现范围。
