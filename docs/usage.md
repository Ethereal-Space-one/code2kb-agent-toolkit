# Code2KB Agent Toolkit 使用指南

**简体中文** · [English](usage.en.md)

本文件面向知识库维护者；AI 使用独立的 [Skill 入口](../skills/extract-app-knowledge/SKILL.md)。操作手顺与 AI 指令都不进入机器人语料。

> 适用于工程 `2.0.0` 待发布版：命令仍为 `code2kb`；源文件协议保持不变，旧品牌发布快照请用生成时对应的工具审计。AI 的执行入口是 [`skills/extract-app-knowledge/SKILL.md`](../skills/extract-app-knowledge/SKILL.md)。

## 工作方式

Code2KB 从一个或多个固定 Git 提交中建立独立的知识项目。先盘点全范围入口，再逐模块提取事实、正文和证据，最后经人工或策略审核生成业务版与研发版。

| 阶段 | 主要产物 | 完成条件 |
| --- | --- | --- |
| 范围盘点 | `知识库配置.json`、`功能大纲.md` | 入口、模块、受众、范围和缺口逐项登记 |
| 模块取证 | `结构化规格.md`、研发材料 | 事实、接口、方法、锚点和未知边界完整 |
| 知识写作 | 业务正文、研发正文、可选业务意图 | 四类问答；业务与技术内容隔离 |
| 影响复核 | impact 队列、结论复核 | 受影响文件逐项清零 |
| 候选审核 | `发布清单.md`、人工或策略审核记录 | 候选摘要和审核依据一致 |
| 发布审计 | 双版、版本清单、当前指针 | `audit-release` 通过并提交 Git |

## 安装

直接运行源码：

```bash
python3 -B validation/knowledge.py --help
```

或安装命令：

```bash
python3 -m pip install -e .
code2kb --help
code2kb --version
```

两种入口调用同一参考实现。

已有旧品牌发布快照时，保留原项目供旧工具审计。新建知识 Git 项目，复用配置、知识源与所需审核材料，经检查后按现有流程发布；不复制旧发布目录，新工具也不会直接覆盖它。

## 新建知识项目

1. 为知识库建立独立 Git 项目。
2. 复制 [`templates/知识库配置.example.json`](../templates/知识库配置.example.json)。
3. 为每个源码仓库填写绝对路径或完整 `${UPPER_CASE_ENV}` 引用，并填写固定提交 SHA。
4. 让 AI 读取 Skill，先建立完整功能大纲。

项目 `content_language` 可选 `zh-CN`（缺省）或 `en`。正文、问答和生成导航使用所选语言；英文业务及研发文件须显式声明 `content_language: en`。AI 交互语言、知识输出语言、源码编程语言分别处理。固定文件名、表头、枚举和 ID 保留；英文流程见[英文使用指南](usage.en.md)。修改语言或翻译正文后仍需刷新候选和重新审核，不能沿用旧批准。

```text
请完整读取 <toolkit-root>/skills/extract-app-knowledge/SKILL.md，
按“当前任务”只加载所需参考文件和模板。
知识项目为 /path/to/knowledge-project，
本次任务是建立全范围功能大纲。
```

## 项目结构

全量或多仓库项目先按[全栈范围盘点](../skills/extract-app-knowledge/references/全栈范围盘点.md)核对仓库、构建单元和依赖版本，再按实际职责选择适配指南。出现跨层调用、消息任务、原生依赖或配置覆盖时，按需读取[跨语言场景取证](../skills/extract-app-knowledge/references/跨语言场景取证.md)；语言标签不决定前后端角色。

调查固定提交中的自有非标准目录时，可显式指定范围：

```bash
code2kb analyze-candidates --project-root /项目 --repository-id source \
  --candidate-schema 0.2 --adapter universal-l1 --scope vendor/internal
```

显式范围可越过其祖先的默认目录过滤，范围下新增的依赖／生成目录仍会跳过。安全限制和固定提交边界不变；完整语义见 [Adapter 契约](adapter-contract.md)。这里输出的是待复核文件候选，入口及业务结论继续按源码取证。

```text
知识项目/
├── 知识库配置.json
├── 知识源/功能大纲.md
├── 知识源/<业务域>/<模块>/
│   ├── 模块概览.md、功能与范围.md、业务流程.md
│   ├── 规则与限制.md、常见问答.md、业务意图.md       # 按证据创建
│   ├── 技术实现.md、接口与调用.md、方法与源码.md     # 按证据创建
│   └── 结构化规格.md、待确认事项.md、发布清单.md
├── 运行证据/                                           # 可选
├── 自动审核策略/、自动审核记录/、自动审核报告/          # 策略审核时使用
└── 发布/
```

不创建空正文。业务证据只保存脱敏摘录和原始材料摘要，不复制敏感原文。

为新候选执行 `prepare` 前，须在模块《结构化规格》的“大纲覆盖核对”表逐项处置归属本模块的已登记入口；已取证关联事实 ID，待核查或范围外写原因。旧发布的审计不受此要求影响。

## 常用命令

```bash
code2kb check --project-root /项目
code2kb impact --project-root /项目 --module-id example.module
code2kb confirm-claims --project-root /项目 --module-id example.module
code2kb prepare --project-root /项目 --module-id example.module \
  --business-topics '用户操作、处理结果' \
  --business-unknowns '运行环境表现' \
  --business-keywords '订单、查询' \
  --engineering-topics '调用链与处理方法' \
  --engineering-unknowns '部署差异' \
  --engineering-keywords '订单、查询、实现'
```

### 审批前选择审核方式

`prepare` 生成模块候选包后，先查看《发布清单》的正文、审核依据、未知项及摘要，再为**每个模块**选一种审核方式。两条路径写入不同的审核状态和溯源，均须在 `publish` 前完成：

| 方式 | 适用条件 | 命令与结果 |
| --- | --- | --- |
| 人工审核 | 人已审阅候选包并明确批准其发布边界 | `approve` → `reviewed`；记录实际审核人、日期与批准原话 |
| 预授权策略审核 | 项目已启用有效策略，本次审核记录覆盖候选摘要、模块和风险，且未命中人工门禁 | `policy-review` → `policy_reviewed`；记录策略、执行者和审核证据 |

策略审核不是让 AI 自行决定批准；`policy-review` 只校验已提交的策略及本次记录，不调用审核模型。策略缺失、过期、超范围或命中人工门禁时保持 `draft`，交人工审阅；不能把 AI 名称填成实际审核人来绕过门禁。即使配置启用了策略，仍可为某个模块选择人工审核；不需要新增项目级审核模式字段。任何候选正文或审核依据变化后，都须重新 `prepare --refresh` 并重审该模块。

人工明确授权后记录审核：

```bash
code2kb approve --project-root /项目 --module-id example.module \
  --reviewed-by '实际审核人' --reviewed-at 2026-10-20 \
  --approval-note '审核人确认的发布范围原文'
```

启用预授权策略时，使用 `1.2` 审核记录，先把策略和审核记录提交到项目 Git；若有 `external.*` 检查，还须把脱敏后的 JSON 报告放在项目 `自动审核报告/` 并提交。报告可参考[示例信封](../templates/自动审核报告.example.json)：`subject_digest` 取本次 `prepare` 返回的候选摘要，`module_id` 与 `tool` 分别指向本模块及对应 `external.*` 检查，`status` 与记录中的 `result` 相同，`generated_at` 为真实带时区生成时间且不晚于记录的 `completed_at`。记录的 `external_reports` 中填写报告的 `path`、原始字节 `sha256`，同一检查的 `report_sha256` 必须一致。工具核对身份、状态和摘要，不判断报告结论真假。历史 `1.0/1.1` 记录仍可核对，不能用于新增批准。随后执行：

```bash
code2kb policy-review --project-root /项目 --module-id example.module \
  --evidence-file 自动审核记录/run-id/example.module.json \
  --executed-by ci-bot
```


### 可选：独立验证者（1.2）

策略审核默认只核对记录与摘要。若希望由另一方（另一个 AI 会话、CI 服务或人）逐条检查“结论是否被所引源码支持”，在策略中使用 `1.1`，参考[示例策略](../templates/自动审核策略-验证者.example.json)。流程如下：

1. 作者 AI 完成 `prepare`。任何人都可以运行只读命令生成验证包，验证者**只拿这份包**，看不到作者的推理：

```bash
code2kb evidence-pack --project-root /项目 --module-id example.module --kind claim_entailment
```

`--kind` 还可取 `qa_replay`（回放问答自测）和 `leak_probe`（检查业务文件是否泄露源码细节）。包内的每一项已带固定提交的源码片段、结论文字摘要和片段摘要。

2. 首次使用某个验证者前先校准：工具从项目自己的 `CODE_VERIFIED` 事实生成含注入错误的题目，答案键保存在项目目录之外，不让验证者读到：

```bash
code2kb verifier-calibrate --project-root /项目 --key-out /项目之外/答案键.json > 校准题.json
# 验证者对校准题作答，得到 答案.json，形如 {"verifier": {"id": "..."}, "items": [{"item_id": "CAL-0001", "verdict": "supported"}]}
code2kb verifier-calibrate --project-root /项目 --pack 校准题.json --key /项目之外/答案键.json --answers 答案.json
```

校准报告写入 `自动审核报告/校准/`；提交到 Git 后才可被引用。

3. 验证者按[示例信封](../templates/验证者报告.example.json)填写报告：原样带回每项的摘要，给出 `verdict`，非通过结论必须写原因，并在 `calibration` 中引用其校准报告。报告与审核记录一并提交后运行 `policy-review`。

工具会重新计算应查项，拒绝缺项、重复项、改动过的结论文字或片段、与候选不符的摘要，以及与作者、执行者或策略授权人相同的验证者身份；策略还可设定校准的最低抓取率、最高误报率和有效期。规格结论含“权限”“归属”“金额”“名额”“指标”“状态”时，风险等级不得低于 `high`，且须启用 `semantic_quality`。这些检查**不判断结论真假**，也不证明验证者在真实项目上不会漏判；验证者只要给出不通过的结论，策略审核就会被拒绝，该模块保持草稿。

发布和审计：

```bash
code2kb publish --project-root /项目 --release-id example-v1
code2kb audit-release --project-root /项目
```

准确参数和回退方式见[发布与维护](../skills/extract-app-knowledge/references/发布与维护.md)。

## 可选检索扩展

基础双版发布后，可按[检索扩展契约](retrieval-contract.md)构建单主题单元，并按[离线评测手顺](retrieval-evaluation.md)运行问题集。评测通过后才有 `发布/当前检索版本.json`；失败不改变基础版本指针。下次基础发布可显式使用 `publish --with-retrieval --retrieval-suite` 把检索门禁纳入同一临时快照。

面向业务问答时，基础业务版提供已发布正文；外部 FTS／向量索引可导入经过检索评测与审计的业务检索单元，再把召回证据交给问答模型。内部规格、待确认事项和研发单元不进入业务机器人语料。若直接拆分基础业务版建立自有索引，分块边界、受众隔离、版本切换与检索评测由使用方负责；本项目的检索扩展审计不覆盖这条自定义路径。

检索扩展通过审计后，可从**当前检索版本**只读查询候选证据：

```bash
code2kb retrieval-query --project-root /项目 --query "订单查询失败时会怎样" --audience business --top-k 3
```

返回 JSON 含 `release_id`、检索清单摘要、命中单元原文、单元路径及双版正文出处。`business` 只读取业务单元；`engineering` 可读取业务与研发单元。输出的 `answerability: not_assessed` 表示尚未判断证据能否回答问题；无命中也不自动构成最终拒答。此命令不修改发布物，也不生成机器人回复。未通过检索门禁或审计失败的发布物不可查询。

`compact` 项目在根目录放独立 `Code2KB工程配置.json`，保留现有知识规范文件类型；它不能靠省略必要条件或未知来缩短正文。

## 重要边界

可选的持久运行账本、批次任务、恢复命令及 Claude Code 薄适配见[0.6 本地接续执行器](0.6.0-runner.md)。旧知识项目无需启用账本。

- `check` 验证结构和固定锚点，不证明自然语言正确。
- `confirm-claims` 记录已经完成的语义复核，不执行语义判断。
- `policy-review` 验证策略和记录，不调用审核模型。
- 缺少运行证据时，研发正文保持 `source_only`。
- 未闭环业务意图只能留在内部规格和待确认事项。
- 业务用户只检索业务版；研发用户才检索研发版。
