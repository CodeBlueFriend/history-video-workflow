# 历史视频内容生产工作台

用于管理历史视频的选题、资料与主张、稿件审核、配音交接、剪辑计划、交付版本及制作预算。支持多个候选选题供选择，选定后补充个人想法，并将内容要求带入创作和审核。

这是本地命令行工作台，不是全自动视频生成服务。创作、联网研究、独立审稿、网页配音和视频剪辑需由人工或外部工具实际执行，再导入记录。附带可选的 Qwen3-TTS 工具；主工作流无需下载模型。

## 每次启动阅读建议

每次运行工作台会显示素材检索与故事筛选建议：优先名人关联的具体故事，结合地方志、笔记野史、文集书信等资料，从故事卡筛出候选供使用者选择。建议无需确认；普通命令的提示写入 stderr，stdout 仍保留 JSON。

完整阅读：[素材检索与故事选题建议](docs/story-sourcing.md)。无需初始化也可运行 `./scripts/history-workflow startup-guide`；`--help` 同样显示建议。

## 今日头条文字版

正式视频验收后增加专项文章改写：从锁稿整理成完整阅读稿，交付Markdown、带复制按钮的HTML排版预览及结构化JSON，与封面和视频发布资料一起保存。CLI建立改写任务、校验版本并排版，创作助手完成实际改写和审核；当前手动上传，后续可基于同一数据接自动上传适配器。详见[文字版工作流](docs/toutiao-article.md)。

## 发布文案与视频标签

每集锁稿后自动建立发布包草稿。创作助手从锁稿提炼简介和悬念，通过 `publication-package 集名 --file 文案.json` 生成一份各平台发布资料汇总及结构化JSON，封面放在同包的封面目录。发布标题与视频完整标题逐字一致，吸引句单列为可选副标题文案；改标题、改稿或修改生成文件后，`publication-check` 会要求重新生成。程序只准备资料，不执行发布。详见[发布文案包说明](docs/publishing.md)。

默认支持抖音、B站、西瓜视频、今日头条、微信视频号、快手、YouTube、小红书、支付宝、拼多多。每周保存本地热点快照，结合锁稿和账号定位筛选相关标签，保留采用/排除依据；缺失、过期及无关热点不会直接采用。每集默认交付四套通用封面：竖屏3:4、9:16，横屏4:3、16:9。见[标签与每周执行流程](docs/platform-tags.md)及[官方推荐规则与出处](docs/platform-recommendations.md)。

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

- [故事线历史与重复检查](docs/story-history.md)（人物可重复，故事线不能重复，样片与测试排除）
- [说书式口播编写规则](docs/workflow-v5.md#说书式口播编写)（背景铺垫、人物入场、情境二创与口播/考据分开）
- [完整工作流与输入格式](docs/workflow-v5.md)（含通用比例封面规格与像素验证）
- [可选本地配音工具](docs/local-tts.md)
- [上游接口记录](docs/upstream.md)

程序和运行数据保存在工作区；桌面仅放交付资料。`production/`、`reports/`、音视频、模型、字体及凭据不提交到仓库。用户自己的资料和生成内容由使用者保管。

## 验证

```sh
.venv/bin/python -m pytest tests/test_workflow.py tests/test_budget.py tests/test_topics.py tests/test_guidance.py tests/test_story_history.py -q
```

测试使用合成数据，验证状态失效、审核门槛、选题选择、追加想法、素材交接和预算计算，不证明历史真实性、音质或最终视听质量。TTS 测试需要安装完整可选环境。

启动预算按口播稿有效字数估算视频时长，不用上传音频时长替代；人工网页配音的生成耗时和费用排除。没有模型用量回执或单价时，算力成本保留未知，不把运行时间等同算力费用。

## 许可证

代码采用 [MIT](LICENSE)。第三方依赖、模型、字体及使用者导入的素材遵循各自许可证；MIT 不授予这些第三方内容的权利。

`reference/` 保留工作流设计与空白模板作为初始化输入；其中的历史设计描述不代表当前已实现能力，实际行为以本 README 和工作流使用说明为准。

## 时长与正文配图

新正式集默认15—60分钟，最大一小时。正文配图预算提高到每分钟约1.5张、最低12张；开场、核心事件、转折和结局要分别规划关键图片，并校验其与段落及实际镜头的对应关系。详见[画面资源规划](docs/visual-planning.md)。
