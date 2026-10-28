# 历史视频内容生产工作台

用于管理历史视频的选题、资料与主张、稿件审核、配音交接、剪辑计划、交付版本及制作预算。支持多个候选选题供选择，选定后补充个人想法，并将内容要求带入创作和审核。

这是本地命令行工作台，不是全自动视频生成服务。创作、联网研究、独立审稿、网页配音和视频剪辑需由人工或外部工具实际执行，再导入记录。附带可选的 Qwen3-TTS 工具；主工作流无需下载模型。

## 每次启动阅读建议

每次运行工作台会显示素材检索与故事筛选建议：优先名人关联的具体故事，结合地方志、笔记野史、文集书信等资料，从故事卡筛出候选供使用者选择。建议无需确认；普通命令的提示写入 stderr，stdout 仍保留 JSON。

完整阅读：[素材检索与故事选题建议](docs/story-sourcing.md)。无需初始化也可运行 `./scripts/history-workflow startup-guide`；`--help` 同样显示建议。

## 快速开始

需要 Python 3.12。接收媒体、测量音视频时需要 ffmpeg/ffprobe。

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-workflow.txt
./scripts/history-workflow init --output-dir "$HOME/Desktop/历史故事长篇"
./scripts/history-workflow topic-options examples/topic-options.json
./scripts/history-workflow topic-select history-topics-001 --minimum 120 --maximum 180
```

最后一步显示候选内容，输入编号后可补充个人想法。后续可用 `idea 集名 想法.txt` 继续追加。Windows 可使用 `.venv/Scripts/python -m history_workflow` 替代 shell 入口。

- [完整工作流与输入格式](docs/workflow-v5.md)
- [可选本地配音工具](docs/local-tts.md)
- [上游接口记录](docs/upstream.md)

程序和运行数据保存在工作区；桌面仅放交付资料。`production/`、`reports/`、音视频、模型、字体及凭据不提交到仓库。用户自己的资料和生成内容由使用者保管。

## 验证

```sh
.venv/bin/python -m pytest tests/test_workflow.py tests/test_budget.py tests/test_topics.py tests/test_guidance.py -q
```

测试使用合成数据，验证状态失效、审核门槛、选题选择、追加想法、素材交接和预算计算，不证明历史真实性、音质或最终视听质量。TTS 测试需要安装完整可选环境。

启动预算按口播稿有效字数估算视频时长，不用上传音频时长替代；人工网页配音的生成耗时和费用排除。没有模型用量回执或单价时，算力成本保留未知，不把运行时间等同算力费用。

## 许可证

代码采用 [MIT](LICENSE)。第三方依赖、模型、字体及使用者导入的素材遵循各自许可证；MIT 不授予这些第三方内容的权利。

`reference/` 保留工作流设计与空白模板作为初始化输入；其中的历史设计描述不代表当前已实现能力，实际行为以本 README 和工作流使用说明为准。
