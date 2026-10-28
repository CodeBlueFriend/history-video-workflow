# 故事线历史与重复检查

人物可以重复，核心故事线不能重复。历史只保存正式制作的故事和补录的正式旧作；已立项但未完成的正式项目单列为占用记录。样片和测试项目完全排除，避免换个标题、叙述视角或措辞又制作同一条故事。

## 使用步骤

```sh
# 每次选题前先看历史：
./scripts/history-workflow story-history
# 检查一份故事线档案，输出JSON结果：
./scripts/history-workflow story-check examples/story.json
# 正常导入候选、选择立项，程序自动检查：
./scripts/history-workflow topic-options examples/topic-options.json
./scripts/history-workflow topic-select history-topics-001 B
# 直接立项也需提供故事线档案：
./scripts/history-workflow new '本集标题' --story-file examples/story.json --minimum 900 --maximum 2400
```

`story-check`是只读检查：命令成功表示检查完成，是否重复看返回的`status`。实际导入候选、选择立项和锁稿会拦截明确重复。候选导入时检查历史和同批候选；选中时重新检查，防止候选保存后被另一个项目先使用。

## 故事线档案

每个候选的`story`字段必填，结构示例见[候选输入](../examples/topic-options.json)和[单独故事档案](../examples/story.json)：

```json
{
  "storyline_id": "hongmen-liubang-escape",
  "characters": ["刘邦", "项羽", "项伯", "张良"],
  "core_event": "鸿门宴前后刘邦从项羽威胁下脱身",
  "conflict": "项羽准备进攻，刘邦需要解除杀身危险",
  "turning_points": ["项伯夜访并说情", "项庄舞剑受到阻挡", "刘邦借故离席"],
  "outcome": "刘邦回营，张良留下辞谢",
  "aliases": ["鸿门宴刘邦脱身"]
}
```

- `storyline_id`：同一事件保持稳定编号，不能为逃避重复而重命名。
- `characters`：记录人物，**不以此字段作为重复判据**。同一个人物讲不同事件可以立项。
- `core_event`、`conflict`、`turning_points`、`outcome`：描述核心事件及情节发展，不能只填“励志”“权谋”等宽泛标签。
- `aliases`：同一故事线的其他编号或事件名称，用来识别不同叫法。人物别名不放在这里。
- `distinctness_note`：发现相近故事时，核对历史后写明核心事件、冲突和转折的实质区别。它只处理疑似重复，不能放行明确重复。

举例：刘邦的鸿门宴脱身与入关约法可以是两条故事。分别从刘邦、项伯或张良的视角重讲同一段鸿门宴脱身经过，仍需按故事线判断，不能因为主角换了就当作新故事。

## 检查结果与边界

| 状态 | 含义与处理 |
|---|---|
| `DUPLICATE` | 编号、核心事件或事件别名相同，或完整情节文字相同；禁止新立项。已有内容返修继续原项目。 |
| `REVIEW_REQUIRED` | 情节文字相近；阅读命中的历史档案，确认是否真正不同，并填写`distinctness_note`。 |
| `NO_MATCH_FOUND` | 本地规则未命中，不能据此宣称语义上绝无重复；选题审核仍须对照历史。 |
| `MISSING_PROFILE` | 旧候选或通过旧版接口建立的项目未填写档案，需要补录。 |

程序做规范化文本匹配及三字符片段相似度检查，不调用语义模型。换词改写、繁简转换、同义情节和不同粒度的故事可能漏检；人物、主题或时代接近也可能造成疑似提示。因此创作助手和审核者仍须比较核心事件及情节发展。旧档案缺失时，`unprofiled_episodes`会列出查重盲区。

## 旧作品补录与历史保存

补录工作台以外的正式旧作品，用`story-record record.json`。记录必须包含`id`、`title`、`status`、`evidence`和上述`story`，工作台旧集还可填写`episode`。状态应如实填写，例如`PRODUCED`或`PUBLISHED`；样片和测试记录禁止导入历史。记录编号不可覆盖。

`story-record`记录已经发生的历史，因此允许补录现实中重复的旧作；它不会创建新项目，这些记录都会参与后续重复检查。

```sh
./scripts/history-workflow story-record old-record.json
# 为旧集补上档案，或修改当前故事线：
./scripts/history-workflow story-profile EP001_本集标题 story.json
# 已锁稿时需说明内容变化原因：
./scripts/history-workflow story-profile EP001_本集标题 story.json --reopen-reason '调整核心故事'
```

`story-profile`是内容修改，会使旧审核、锁稿、素材有效性和下游结果失效；修改前的故事线保留在历史中。只想补登记已经完成的旧作，可用`story-record`保存真实来源，避免变更旧集状态。

外部补录记录保存在运行目录`01_选题库/故事线历史.json`。新立项的故事线随每集`00_项目记录/工作台状态.json`自动保存，`story-history`返回`records`（正式制作历史）与`active_records`（正式项目占用记录），重复检查使用两者。样片、测试及其修改前的故事线均不参与。备份时保存整个运行目录；这些个人历史不会自动上传公开Git仓库。

新CLI入口要求故事线档案；旧版Python调用仍可建立无档案项目以兼容旧数据，但会返回`MISSING_PROFILE`。这类项目需先补录后才能完成可靠查重。旧候选批次缺少`story`时，保留原批次，另存含故事线档案的新批次后再选择。


## 样片与测试排除

创建样片时显式传入`--sample`，项目保存`production_kind: SAMPLE`；正式项目默认为`FORMAL`。

```sh
./scripts/history-workflow new '测试样片' --story-file examples/story.json --sample
./scripts/history-workflow topic-select history-topics-001 A --sample
```

整批候选用于样片时，可在批次JSON顶层填写`"production_kind":"SAMPLE"`。样片不计入已制作历史、不做正式故事占用，也不因正式旧作重复而阻止测试；即使已有导出或验收状态，仍然排除。旧版历史中的`TEST_PRODUCED`等样片状态也会被过滤，新补录会拒绝它们。

旧样片项目需补上`production_kind: SAMPLE`，不根据片名猜测性质；只删除外部历史记录而不标记原项目，可能造成以后再次被扫描到。样片视频、稿件和测试资料可保留在各自项目中。
