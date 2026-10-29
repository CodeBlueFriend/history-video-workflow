# 历史长视频工作台 V5

已经实现本地命令行工作台。它管理内容证据、独立审核记录、版本、素材与外部剪辑交接。历史写作、事实判断、试听和视听验收需要真实执行后导入结果。程序不调用模型，不自动联网检索，不调用 TTS，不进行视频渲染，也不自动发布。

开发代码位于当前项目 `history_workflow`，原 `history_tts` 工程保留。程序、配置、模板和工作记录位于当前工作区，默认运行数据目录为 `production`。桌面 `~/Desktop/历史故事长篇` 仅接收生产的视频资料，按集名和版本保存稿件、配音、图片、封面、剪辑文档、工程及成片，不放项目程序。此规则按用户最新说明覆盖附件中“桌面为项目根目录”的约定。测试数据单独保存在项目 `reports/workflow-synthetic`，不会写入正式选题或冒充用户声音。

## 启动

每次正常执行命令时，工作台会在 stderr 显示[素材检索与故事选题建议](story-sourcing.md)，供使用者阅读；stdout 保留命令 JSON。建议项不会新增确认步骤或自动检索。`--help` 同样显示，可在初始化前用 `./scripts/history-workflow startup-guide` 单独查看。

在本项目目录执行：

```sh
uv pip install --python .venv/bin/python -r requirements-workflow.txt
./scripts/history-workflow --help
./scripts/history-workflow init
./scripts/history-workflow new '本集选题' --story-file examples/story.json --minimum 120 --maximum 180
./scripts/history-workflow list
```

不使用已有 TTS 环境时，可先 `uv venv --python 3.12 .venv`，再安装上述轻量依赖；无需下载语音模型。初始化只在工作区补缺失模板，不向桌面复制模板。也可在所有命令前加 `--root '/选择的项目根目录'`。macOS 使用系统桌面定位，Windows 使用注册表重定向路径，Linux 使用 XDG 桌面配置；无法识别时报错要求使用 `init --output-dir` 指定生产资料输出路径。

新建集名由程序分配，例如 `EP001_本集选题`。下文以这个名称为例，替换成实际输出。JSON 为 UTF-8；传入的媒体文件路径使用绝对路径。命令退出码 0 表示成功，2 表示错误或阻断，详细原因输出在 stderr。所有修改命令采用操作系统锁，状态采用临时文件加原子替换，失败后可重新执行；命令不要并行修改同一项目。

## 内容与独立审核

```sh
./scripts/history-workflow topic topic.json
./scripts/history-workflow public-source public-source.json
./scripts/history-workflow content EP001_本集选题 source source.json
./scripts/history-workflow content EP001_本集选题 claim claim.json
./scripts/history-workflow content EP001_本集选题 timeline timeline.json
./scripts/history-workflow content EP001_本集选题 disputes disputes.json
./scripts/history-workflow content EP001_本集选题 outline outline.txt
./scripts/history-workflow content EP001_本集选题 script script.json
./scripts/history-workflow review-packet EP001_本集选题 fact
./scripts/history-workflow review EP001_本集选题 review.json
./scripts/history-workflow resolve EP001_本集选题 resolution.json
./scripts/history-workflow timing EP001_本集选题 timing.json
./scripts/history-workflow check EP001_本集选题
./scripts/history-workflow lock EP001_本集选题
```

`topic`、`public-source` 最少包含 `id`、`title`，其他字段可补核心问题、范围、人物、取舍和来源定位。公共来源索引仅用于目录，采用时仍需导入本集来源快照。

来源示例（未知作者、版本和时间不可猜测）：

```json
{"id":"SRC001","title":"实际读到的材料","genre":"笔记","locator":"卷章页码","excerpt":"实际摘录","access":"USER_PROVIDED","obtained_at":"2026-10-28","author":"实际作者","url":"材料链接"}
```

`access` 允许 READ、USER_PROVIDED、UNREAD、RESTRICTED；后两种不能支持已锁稿主张。体裁不会自动判定真伪。

```json
{"id":"C001","text":"本集关键主张","sources":["SRC001"],"reliability":"LIMITED","allowed_expression":"保留归因和限制的表述","reason":"对证据与反证的判断理由","paragraphs":["P001"]}
```

可靠程度为 SUPPORTED、LIMITED、DISPUTED、UNVERIFIED；UNVERIFIED 阻止锁稿。`timeline`、`disputes` 导入 JSON 数组，可保存事件、时间、来源、人物认知和冲突记录。文稿为 `{"text":"第一段。\n\n第二段。","author":"作者或创作任务标识"}`，空行划分 P001 等段落。大纲是纯文本。

独立审核角色：evidence、outline、fact、narrative、oral、coherence、clean。逐角色输出独立任务包，包含来源、主张、目标稿、必要事实与量表，不包含作者自评。由人工或另一个实际审核任务执行，再导入结果；程序不会假装启动了审稿模型。当前实现对这些审核均绑定同一最终输入版本，内容变化后需要重新核对，属于保守失效策略。

审核 JSON 结构：

```json
{
  "role":"fact", "input_hash":"从review-packet输出取得", "reviewer":"独立审稿人",
  "evidence":"实际核对位置、范围和结论依据", "conclusion":"PASS", "issues":[],
  "scores":{
    "accuracy":{"score":30,"reason":"实际评分依据"},
    "causality":{"score":20,"reason":"实际评分依据"},
    "structure":{"score":20,"reason":"实际评分依据"},
    "oral":{"score":15,"reason":"实际评分依据"},
    "originality":{"score":10,"reason":"实际评分依据"},
    "title":{"score":5,"reason":"实际评分依据"}
  }
}
```

此处高分只是字段形状，不可复制作为实际审核。coherence 额外要求 `checks`，包含 time、identity、knowledge、causality、transition、repetition、promise 的具体复核记录。审核人不能与作者同名，记录完整、总分至少85且阻断问题清零才允许锁稿。身份字符串隔离不能证明审核真正独立，仍须组织实际独立任务。

问题最少字段为 id、paragraph、quote、severity、factual、description、evidence、repair、acceptance。严重度 P0/P1/P2/P3；factual 必须布尔值。复审文件包含 id、input_hash、reviewer、evidence、outcome；FIXED 还需 before、after、repair；ACCEPTED 仅适用于非事实 P1，需 user_acceptance；RETAINED 仅适用于非事实 P2/P3，需 reason。FAILED 连续累计两轮后，下一次处理必须有 user_decision。原编号历史不会因换稿或再次导入清空；问题是否被恶意换名仍须总控审查。

改锁稿时先运行 status/check 看现有依赖，确认影响后通过 `content ... --reopen-reason '已确认的重开范围与理由'` 记录授权。程序不会代替用户授权。当前会保守失效全部正文配音和剪辑，不做自动语义级局部复用；旧原件和历史快照仍保留。

## 时长与网页配音

```json
{"rate":180,"readings":{"208":"二百零八"},"extra_pause":0,"net_intro_outro":0,"audio_tolerance":0.05}
```

未提供样音时语速明确标为 ASSUMED。数字与拉丁缩写必须在 readings 中给计划读法；按规范化汉字计数。5400字、180字/分钟等于1800秒。额外停顿大于0时必须设置 `pause_excluded_from_sample:true`，防止重复计入样音已包含的停顿。

真实校准再添加 sample_file、sample_text、voice、settings；程序读取样音实际时长，保存副本，计算实际语速。voice/settings 必须与后续网页包一致。文件格式 WAV 可直接读取；其他音频和视频依赖系统 ffprobe，仅用于探测。旁白按预估音频时长及 audio_tolerance 比例验收，成片独立按本集区间验收。

```sh
./scripts/history-workflow audio-package EP001_本集选题 voice.json
```

```json
{"voice":"用户已选MiniMax音色的名称或ID","settings":{"model":"实际网页模型","speed":1},"limit":1000,"pronunciation":{"需修正词":"朗读替换"}}
```

limit 必须填写当前网页真实上限。输出 A001 等 TXT、任务映射与独立字幕原文。当前按段落及上限作无损切分，超长段落可能在句中切开，请在准备前整理自然段并核对衔接；不会承诺自动理解所有中文断句。修改音色、设置或文本包后旧音频失效。网页生成、试听、下载由用户完成。

## 素材与镜头

```sh
./scripts/history-workflow asset EP001_本集选题 asset.json
./scripts/history-workflow verify-asset EP001_本集选题 asset-review.json
./scripts/history-workflow plan EP001_本集选题 plan.json
./scripts/history-workflow document EP001_本集选题 TIMED
```

素材字段：kind（audio/image/cover/music/sfx）、id（A001/IMG001/COVER001/M001/FX001）、file、source、rights、confirmed_mapping:true。image 还需单一 scene 和 paragraphs。路径复制到本集，文件名含内容哈希，原件不覆盖。音频自动探测秒数，图片探测尺寸。封面可在额外字段中登记参考、底图、标题方案和编辑文件信息；需要独立保存的附件可使用不同 COVER 编号导入，最终采用封面须单独通过审核。

素材审核：id、sha256（取自 status）、reviewer、evidence、checks。必需检查项：

| 类型 | checks 的必填 true 项 |
|---|---|
| audio | no_omission, no_repeat, no_truncation, voice_preserved |
| image | identity, era, safe_motion, subtitle_space |
| cover | consistency, readability, identity, rights |
| music/sfx | rights, audibility |

镜头计划包含 responsible、shots 数组、transitions 数组。每个镜头至少记录 id:K001、image:IMG001、paragraphs、motion、purpose、check_method。可以先保留未知时间；输出 TIMED/交接时必须补 start/end（秒）、time_basis:AUDIO_VERIFIED、anchor_evidence、start_crop/end_crop 和 safety_review。裁切建议采用 `[x,y,width,height]` 归一化窗口，实际软件参数可放额外字段；当前只校验记录齐备，不自动判定运动路径视觉安全。

转场需 from、to、type、overlap、semantic_reason、audio_continuity、ghosting_review。程序按区间并集校验全旁白覆盖，允许有明确记录的重叠；重叠不在旁白时长里重复加减。静止镜头使用 motion:static，exception 需 reason、alternatives、resume、reviewer，以及 no_safe_motion/narration_continues/no_cut_point/accepted 均为 true。所有静止都要求复审，因此超过6秒也不会未经审核放行。

只换封面会失效封面审核与交接，不失效配音；换音频会失效时间轴；换图片需重新审核画面与运动。图片预算为建议，当前不自动挑选六张图，也不自动生成图片或关键帧。

## 工具核验 交接与成片

```sh
./scripts/history-workflow capabilities capabilities.json
./scripts/history-workflow handoff EP001_本集选题
./scripts/history-workflow export EP001_本集选题 export.json
./scripts/history-workflow accept EP001_本集选题 final-review.json
```

工具核验包含 name、version、tester，checks 各项为 `{"passed":true,"evidence":"实际测试证据及样段位置"}`。必填项：original_audio、motion_crop、transitions、subtitle_correction、long_video、archive、short_sample、single_image_test。没有真实测试不能填 true。当前没有对接任何剪辑工具接口，程序不根据广告宣称可导入。

handoff 要求全部当前音频、计划、图片和封面检查通过，冻结 Word/TXT、素材对应表、修改记录及结构快照，并打包本集普通文件 ZIP 到根目录“交接归档”。所有文件使用相对路径。冻结文档的哈希在导出登记时复核，手填 Word 后应先同步结构记录、重新生成和冻结。

export 文件包含 file（实际视频路径）、executed_by、settings（真实设置对象），以及 project_file 或 project_url。程序复制视频/工程或记录云链接，实测视频秒数；状态只进入 PREVIEW_REVIEW。

accept 文件包含 video_hash、reviewer、evidence、execution_matches_document:true，checks 中 content、audio、subtitles、identity、cover、motion、transitions、full_playback、archive_restore 均须在实际检查后填写 true。实际成片时长达标、文档已回填并核对一致后生成 FINAL 文档和 FINAL_ACCEPTED 状态。

## 数据与恢复

唯一机器状态为每集 `00_项目记录/工作台状态.json`；该文件包含完整台账与当前指针。`00_项目记录/历史版本` 保存每次状态快照；剪辑文档各版有各自结构快照和文件哈希。原设计的空模板 JSON 仅作参考，程序不会将其空状态当作真实运行结果。

中断后重新运行 status/check，再继续所需步骤，不需要恢复旧聊天。进程退出会释放系统文件锁。失败可能留下未引用素材或文档目录，原件不会自动清理。手工恢复旧状态时，先备份完整集，再用指定历史快照替换当前状态；复查引用文件与哈希后继续。暂未提供自动回滚按钮和跨文件事务数据库。

## 验证与限制

```sh
.venv/bin/python -m pytest -q
.venv/bin/python scripts/workflow_demo.py /tmp/history-workflow-synthetic
```

demo 明确生成合成资料、纯色图片和120秒正弦信号，审核记录是程序测试断言。它不证明历史准确、用户音质、单图疲劳、转场效果或真实外部剪辑完成。真实2—3分钟节目、30—60秒运动转场、单图3—5分钟及30分钟长片均待实际制作。

运行验证和当前未完成项见 `reports/workflow-validation.md`。当前交付以可运行 CLI 与文件交接为界面；没有网页界面、模型调用、联网材料采集、自动剪辑适配或发布功能。

## 桌面生产资料输出

运行目录和输出目录完全分开。`--root` 指工作区运行目录；`init --output-dir` 指生产资料目的地。初始化不把项目文件放到输出目录。

通过 CLI 完成锁稿、准备配音包、导入/审核素材、生成剪辑文档、冻结交接、登记导出和成片验收后，会自动将当前生产资料复制到输出目录的 `集名/r版本_唯一编号` 下。仅复制当前版本文件，不复制程序、配置、模板和运行日志；制作中素材会在生产资料清单中显示本集状态，不冒充已验收成片。

可用 `./scripts/history-workflow deliver EP001_本集选题` 手工重试或再次导出。每次写入独立目录并校验文件哈希，不覆盖你之前的资料和备注。桌面不可写时，工作区操作仍已保存，命令会显示 delivery_error 和重试方法。

## 锁稿后的并行生产

锁稿后，配音、正文背景图、封面是可以独立推进的工作。图片按锁稿内容和来源设计，导入图片/封面不要求音频已生成或验收。等待音频期间应推进画面设计、生成和审查；真实音频回来后才确定镜头秒点、字幕对齐和时轴覆盖。已增加图片先于音频导入的回归测试。

用户先自行制作完整口播音频时，可用 `receive-audio EP001_本集选题 receipt.json` 接收。JSON包含file、source、rights、confirmed_mapping:true，可选voice和settings。程序建立覆盖完整锁稿的A001任务、保留原文件并测时；未确认的音色/设置保持空值，不把文件名推断当作实测配置。重复接收有既定任务时拒绝覆盖，应使用asset按编号导入。接收成功不等于试听通过。

## 启动预算与制作总结（2026-10-28）

新增 `preflight 集名`、`run-start 集名`、`run-finish 集名 receipt.json`。启动预估只按口播稿有效汉字数，默认180字/分钟、范围160—220，另计4.5秒片头片尾；不读取音频时长。手动网页配音暂不计入制作时间和成本。已有稿件的制作命令会自动在stderr输出并归档启动预估，stdout仍为原命令JSON；status/check为只读。首次导入稿件后运行preflight/run-start。

`production/00_项目配置/制作预算配置.json` 保存计划语速、工作量假设、单价和实测耗时基准。未知价格/耗时填null，不能当零。token倍率与图片尝试倍率是可调预算假设，不是实际调用用量。单位耗时齐全时输出串行耗时估算，不能冒充并行墙钟耗时。当前预算覆盖完整制作，不是增量修订报价。

结束回执示例：`{"excluded_manual_audio_and_wait_seconds":0,"usage":{},"evidence":null}`。有真实回执时可提供usage中的input_tokens、output_tokens、image_attempts、render_minutes、local_compute_seconds；有用量时必须提供evidence。所有计费项目同时有用量和单价才给出实际总费用，缺项保持未知。墙钟时间不等于CPU/GPU耗时。预算不会改变锁稿或剪辑对齐状态，字幕和画面实际执行仍需真实音轨。

## 候选选题、选择与个人想法

立项时先提供至少3个不同方向的内容（程序允许2—10个），每项说明标题、内容范围和叙事角度，并填写`story`故事线档案（编号、人物、核心事件、冲突、转折、结局）。由创作助手或人工准备候选，程序负责展示、选择、保存；它不会假装已经联网研究或调用生成模型。可用 `examples/topic-options.json` 作为输入样例。

```sh
./scripts/history-workflow topic-options examples/topic-options.json
./scripts/history-workflow topic-list history-topics-001
# 交互显示选项，输入候选编号，再填写个人想法：
./scripts/history-workflow topic-select history-topics-001 --minimum 120 --maximum 180
# 自动化调用必须明确编号：
./scripts/history-workflow topic-select history-topics-001 B --idea '重点讲执行中的矛盾' --minimum 120 --maximum 180
# 选定后继续追加，替换为上一步实际返回的集名：
./scripts/history-workflow idea EP001_张居正改革的代价 我的想法.txt
```

候选批次不可覆盖，修改候选用新批次编号。立项保存完整候选快照、批次哈希和个人想法时间记录；选题角度与想法写入 `工作台状态.json` 的 `creative_brief`，创作时必须先读该字段。独立审核包也包含它，检查稿件是否落实要求，但不把用户想法当作史实证据。

追加想法会失效旧审核、锁稿、时长估算、素材有效性及下游交接/成片验收状态。已锁稿时需 `--reopen-reason '修改原因'`，旧文件与历史快照仍保留。旧版 `new` 直接立项入口继续兼容；通常优先使用候选选择流程。

## 故事线历史

人物允许重复，故事线不可重复。选题前用`story-history`查看历史；候选导入、选择立项及锁稿时检查故事线。直接`new`需`--story-file`。已完成的正式内容进入历史，制作中的正式项目单列占用记录；样片和测试用`--sample`标记，完全排除。正式旧作品可用`story-record`补录。完整格式、疑似重复处理及旧数据迁移见[故事线历史与重复检查](story-history.md)。

## 通用比例封面与统一发布包

每集锁稿后默认制作四套通用封面：横屏16:9（1920×1080）、横屏4:3（1440×1080）、竖屏3:4（1080×1440）、竖屏9:16（1080×1920）。文件名按画幅命名，不绑定平台。封面可与手动网页配音并行推进，逐套构图和实测，不能拉伸或裁掉文字、人物。

配置保存在`production/00_项目配置/封面规格配置.json`，新集快照到`cover_plan`。旧集用`cover-plan 集名 --refresh`显式更新并保留历史。`cover-status`按实际素材审核和尺寸检查，不能用计划冒充图片齐备。默认封面预算4张；四种画幅均需实际图片验收。

| 封面 | cover_target | 文件名 |
|---|---|---|
| 通用横屏16:9 | `LANDSCAPE_16_9` | `通用横屏封面16比9.png` |
| 通用横屏4:3 | `LANDSCAPE_4_3` | `通用横屏封面4比3.png` |
| 通用竖屏3:4 | `PORTRAIT_3_4` | `通用竖屏封面3比4.png` |
| 通用竖屏9:16 | `PORTRAIT_9_16` | `通用竖屏封面9比16.png` |

旧`BILIBILI`、`DOUYIN`、`DOUYIN_LANDSCAPE`分别兼容16:9、3:4、4:3，不改历史素材含义。每个平台可从已生成比例中选择，发布时检查实际裁切。封面、主副标题、对应平台文案和标签归入同一发布包，文字合并为`发布资料汇总.md`；见[标签与发布包流程](platform-tags.md)。

封面文字只显示主标题，有副标题时可同时显示副标题；不自动增加其他说明。不得出现“明人笔记里的两幕”“历史情境示意”“历史情景示意”等来源或情境标签，也不加页脚、角标、装饰小字。资料与二创边界放在项目资料及发布说明中。默认规则保存在封面配置的`text_policy`，生成提示词须包含允许的确切文字，成图后逐字目检；像素校验不等于文字已经通过OCR检查。

## 说书式口播编写

默认先铺垫时间、张力与名人背景，人物登场时解释身份、关系和难题，再按行动及后果缓缓展开。开场不要突然出现听众不认识的人，也不要先把不同遭遇和结局报完。二创用于叙事安排、情境、动作与选择代价，保留史实骨架；不能只改写古文或用反问、比喻、重复解释凑时长。

来源、论文、考据与原页核查放配套资料，口播不反复报书名、作者和转引层级。仍要以故事语言交代会影响理解的限定，如刑讯供词未查实。逐段将事实、笔记传闻、推演、情境重构分层记录，向观众提供改编说明，不能把无据密谈、动机或罪证变成确定事实。

`production/00_项目配置/文稿编写规则.json` 为项目默认规则，新集快照至`writing_rules`并绑定资料/稿件版本哈希；前置与最终独立审核包均携带规则，要求审查背景铺垫、人物入场、故事推进、口语和二创边界。旧集不自动改写，明确采用新规则后重新审核。程序传递创作约束，不自动生成稿件，也不以关键字扫描冒称完成叙事审核。
