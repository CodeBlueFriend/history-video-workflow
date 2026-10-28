# 官方接口核对记录

核对日期：2026-10-28。

- 官方仓库：https://github.com/QwenLM/Qwen3-TTS
- 核对 commit：`022e286b98fbec7e1e916cb940cdf532cd9f488e`
- README：https://github.com/QwenLM/Qwen3-TTS/blob/022e286b98fbec7e1e916cb940cdf532cd9f488e/README.md
- Python 包：`qwen-tts==0.1.1`；官方建议 Python 3.12 独立环境。
- 包装器源码：`qwen_tts/inference/qwen3_tts_model.py`。

本项目使用 `Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign` 设计，`Qwen/Qwen3-TTS-12Hz-0.6B-Base` 克隆。对应模型的精确 Hugging Face commit 记录在 configs/default.json，下载后全部从本地 snapshot 加载，以避免上游 main 移动、processor 与权重版本不一致。

VoiceDesign 使用 `generate_voice_design(text, language, instruct, non_streaming_mode=True, **generation)`。
Base 先调用 `create_voice_clone_prompt(ref_audio, ref_text, x_vector_only_mode=False)`，再调用 `generate_voice_clone(text, language, voice_clone_prompt, non_streaming_mode=True, **generation)`。

当前接口明确列出的通用采样参数包括 do_sample、top_k、top_p、temperature、repetition_penalty、max_new_tokens。代码没有向 Base 传 instruct、speaker 或虚构 speed 参数。CustomVoice 使用预置 speaker；本工程没有将它混入设计与克隆链路。

持久复用依靠 WAV + UTF-8 参考文本 + 元数据。每个新进程重新提取声音特征，同一进程内缓存 prompt。没有将种子当作声音身份，没有依赖跨版本 pickle。

MPS 使用 eager attention，起始 float32。官方示例的 CUDA、BF16、FlashAttention 不是本机必选项。模型实测失败必须记录，不能仅凭 torch.backends.mps.is_available() 宣称推理兼容。
