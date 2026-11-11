![Code2KB Agent Toolkit：源码窗口、证据便笺与萌芽知识书页组成的标题插画](assets/readme/header.svg)

# Code2KB Agent Toolkit

**简体中文** · [English](README.en.md)

**让 AI 把代码里的业务规则，整理成机器人可以检索的知识。**

把源码仓库、提取范围和这套工具交给你现有的 AI 编码助手。

AI 沿代码整理功能、流程、限制和问答；`code2kb` 检查证据记录、审核状态和发布文件，帮助你得到可维护的业务与研发知识。

[适合谁](#适合谁使用) · [知识产物](#知识产物) · [快速开始](#快速开始) · [常见问题](#常见问题) · [文档](#文档)

![Code2KB：源码经 AI 取证、写作与审核，生成知识文件，供外部 FTS 或向量索引及机器人问答使用](assets/readme/overview.svg)

<br>

## 适合谁使用

- **业务系统维护者**：把反复翻代码解释的规则，整理为可查询的知识。

- **知识库与机器人开发者**：从已有系统提取功能、流程和限制，作为问答语料。

- **项目交接与文档维护者**：把说明与固定源码版本关联，保留实现依据和待确认项。

首次使用可以选一个明确的小模块。先让 AI 说明约定范围和缺口，再提取其中的知识，不必一开始就处理整个系统。

<br>

## 知识产物

| 产物 | 包含什么 | 怎么使用 |
| --- | --- | --- |
| **业务版** | 功能说明、操作流程、规则限制、常见问答 | 给业务人员阅读，或作为业务机器人语料 |
| **研发版** | 同一份业务正文，加上实现、接口、方法与源码依据 | 给开发者核对和维护 |
| **内部知识源** | 功能大纲、结构化事实、草稿与待确认事项 | 维护知识，不导入业务机器人 |
| **可选检索版** | 从已发布正文整理的主题单元，保留条件、例外、未知和出处 | 评测、审计后交给外部 FTS 或向量索引 |

输出形式示意，依据仓库内的[订单示例](conformance/english/knowledge.md)，不是线上运行结论：

> **问：登录后能查看所有订单吗？**
>
> 答：该示例中，登录用户只能查看分配区域内的订单。实际区域分配和线上表现尚未验证，不能据此认定某个账号一定有权查看。

接入问答系统时，链路为 **业务知识 → FTS／向量召回 → 问答模型组织答案**。使用方提供索引服务、问答模型和机器人部署。

经过评测的检索版有单独的审计路径；直接拆分业务版建立自有索引时，由使用方检查分块、受众隔离和版本切换。

<br>

## 插件安装

| 宿主 | 安装方式 |
| --- | --- |
| DeepSeek Harness | 在插件页搜索 `code2kb-dsh`，或运行 `dsh plugin --profile desktop add code2kb-dsh` |
| Claude Code | 从含插件清单的检出启动 `claude --plugin-dir .` |
| Codex | 从含插件清单的检出运行 `codex plugin marketplace add .`，再运行 `codex plugin add code2kb@code2kb` |

在新会话中请 Agent 用 Code2KB 提取源码知识。插件内置 Skill 和 CLI，运行仍需要 Git 和 Python 3.9+。参见[插件安装与打包](docs/plugin-installation.md)。

<br>

## 快速开始

准备 **Git、Python 3.9+** 和能够读取本机仓库的 AI 编码助手。修改类命令需要 `fcntl` 文件锁，可在 Linux／macOS 等提供该模块的平台运行；其他平台可运行只读检查。

### 1. 安装工具，指定源码

建议使用独立虚拟环境。曾安装旧包的用户，在原环境先执行 `python3 -m pip uninstall code2kb-spec`，避免两个包共用同一命令。

```bash
git clone https://github.com/Ethereal-Space-one/code2kb-agent-toolkit.git
cd code2kb-agent-toolkit
python3 -m pip install -e .
git init /path/to/knowledge-project
cp templates/知识库配置.example.json /path/to/knowledge-project/知识库配置.json
git -C /path/to/source-repo rev-parse HEAD
```

知识项目和源码仓库分开保存。编辑 `知识库配置.json`：删去不用的示例仓库，填入每个源码仓库的绝对路径 `path` 与固定提交 `commit`。知识正文默认中文，英文输出设置 `content_language: en`，见[英文指南](docs/usage.en.md)。

<br>

### 2. 把任务交给 AI

替换下面的路径和范围，发送给你的 AI 编码助手：

```text
请读取 <toolkit-root>/skills/extract-app-knowledge/SKILL.md，选择中文执行指引。
在 /path/to/knowledge-project 建立业务知识库。
本次约定范围：〈整个项目，或明确的单个模块〉。
先规划模块、入口和缺口，再读取配置中的固定源码提交，逐模块取证和写作。
正文保留适用条件、失败和未知；不能把代码推断写成线上已验证结果。
先完成检查和待审候选，按选定审核方式推进；发布、推送或接入机器人前核对本次授权。
```

AI 按阶段读取所需指引和模板。模型与执行环境来自你使用的编码助手，CLI 负责检查和生成发布文件。

<br>

### 3. 检查、审核并发布

```bash
code2kb check --project-root /path/to/knowledge-project
```

让 AI 完成实际复核，再按 `impact → confirm-claims → prepare` 准备候选。随后选择：

- **人工审核**：实际审核人批准内容与边界后，用 `approve` 记录决定。

- **预授权策略审核**：已有有效策略和本次审核记录时，用 `policy-review` 核对；命中人工门禁则保持草稿。

审核通过、发布输入提交到知识项目 Git，并取得本次发布授权后，执行：

```bash
code2kb publish --project-root /path/to/knowledge-project --release-id my-kb-v1
code2kb audit-release --project-root /path/to/knowledge-project
```

`check` 通过不等于批准，也不证明自然语言结论正确。[完整使用手顺](docs/usage.md)包含配置、审核与可选检索步骤。

多模块交付可先用 `preflight` 只读检查单模块结构，再按[批次手顺](skills/extract-app-knowledge/references/长任务续跑.md)统一检查稳定终稿，减少重复获取空队列；审核和发布要求不变。这是 2.0 的主分支补充，原 `v2.0.0` 下载快照不含此命令，需更新到包含该补充的 `main` 提交。

<details>
<summary>先看看文件结构：运行内置示例</summary>

```bash
python3 -B examples/create_demo.py
```

脚本建立临时源码与知识项目，运行检查并打印路径；它不调用模型生成完整知识库。[PetClinic 案例](conformance/public-source/petclinic/README.md)另有发布与实际 FTS5 召回记录，验证范围是证据定位，尚未验证机器人最终回答。

</details>

<br>

## 常见问题

**它与直接让 AI 总结代码有什么不同？**

这里提供可接续的工作步骤、固定源码依据、条件与未知记录，以及审核发布工具。是否值得这些额外步骤，可以先用一个模块判断；工具本身不证明 AI 写得正确。

<br>

**需要阅读全部规范吗？**

使用者先看使用指南，把 Skill 入口交给 AI。格式细节由模板和规范提供，AI 按任务读取；维护工具或扩展格式时再深入规范。

<br>

**中英文分别支持什么？**

人读指南与 AI 指引分开；知识正文可选中文或英文。固定文件名、内部表头和 ID 保留，部分诊断仍为中文。语言声明检查一致性，正文是否符合目标语言仍需复核。

<br>

**产物怎样交给机器人？**

业务机器人读取已发布的业务知识或已评测的业务检索单元。内部规格、过程文件和本工具的操作指令不进入语料。索引和机器人接入由使用方完成，见[检索契约](docs/retrieval-contract.md)。

<br>

## 按需扩展

- **全栈取证**：[按实际系统职责盘点](skills/extract-app-knowledge/references/全栈范围盘点.md)，调查跨语言调用、消息任务、原生组件与配置覆盖；[公开案例](conformance/full-stack/README.md)检查条件与未知的保留。

- **长任务接续**：[任务账本和恢复](docs/0.6.0-runner.md)，提供 Claude Code／Codex 任务指令适配。

- **源码变更复核**：[比较固定版本](docs/1.0.0-public-contract.md)，输出待维护者复核的知识范围。

- **入口扫描**：[适配器](docs/adapter-contract.md)提供待复核候选；无专用分析器时采用文件级盘点。

<details>
<summary>可选：独立验证、扫描示例与详细流程图</summary>

### 独立验证（1.2）

`evidence-pack` 导出结论及源码片段，交给另一位验证者复核。验证者由使用方运行，工具核对候选、覆盖和摘要。策略可要求先用 `verifier-calibrate` 校准；成绩不证明真实项目判断正确率。[查看手顺](docs/usage.md#可选独立验证者12)。

![独立验证者检查候选，策略核对报告；不通过保持草稿](assets/readme/independent-review.svg)

扫描自有非标准目录时，替换仓库 ID 后执行：

```bash
code2kb analyze-candidates --project-root /path/to/knowledge-project \
  --repository-id source_a --candidate-schema 0.2 \
  --adapter universal-l1 --scope vendor/internal
```

显式范围可以选中默认过滤目录内的自有源码，范围下的依赖目录仍会过滤；候选不自动成为事实。

以下图中的代码和编号用于说明结构：

<br>

**01 · 源码盘点**

![源码盘点与适配器候选](assets/readme/source-adapters.svg)

*源码盘点与适配器候选。*
<br>

**02 · 依据与事实**

![固定源码依据与事实](assets/readme/evidence.svg)

*固定源码依据与事实。*
<br>

**03 · 两种知识视图**

![业务版与研发版](assets/readme/two-views.svg)

*业务版与研发版。*
<br>

**04 · 可选检索**

![可选检索单元、评测与审计](assets/readme/retrieval.svg)

*可选检索单元、评测与审计。*
<br>

**05 · 源码升级复核**

![源码升级后的只读复核计划](assets/readme/upgrade-review.svg)

*源码升级后的只读复核计划。*

</details>

<br>

## 文档

| 你想做什么 | 入口 |
| --- | --- |
| 开始使用 | [中文指南](docs/usage.md) · [English guide](docs/usage.en.md) |
| 给 AI 下达任务 | [Skill 入口](skills/extract-app-knowledge/SKILL.md) |
| 理解知识文件格式 | [知识文件规范](SPEC.md) |
| 导入检索系统 | [检索契约](docs/retrieval-contract.md) |
| 判断工具保证到哪里 | [保证范围](docs/assurance-matrix.md) |

当前工程版本：`2.2.0`。查看[插件分发发布说明](docs/2.2.0-release-notes.md)或 [2.2.0 Release](https://github.com/Ethereal-Space-one/code2kb-agent-toolkit/releases/tag/v2.2.0)。

本项目由 Code2KB Spec 更名为 **Code2KB Agent Toolkit**，仓库和 Python 包标识统一为 `code2kb-agent-toolkit`，命令仍为 `code2kb`。

不提供旧名称兼容或自动迁移：旧版发布物请使用其生成时对应的工具审计；已有知识源经检查后可继续维护并重新发布。更名不会自动更新机器人或索引。详见[更名说明](docs/agent-toolkit-rebrand-plan.md)与[版本管理](docs/versioning.md)。

已有旧品牌发布目录时，保留原项目；在新的知识 Git 项目中复用配置、知识源及所需审核材料，经检查后发布。新工具会阻止直接覆盖旧品牌快照。

源码不能单独证明线上表现或业务政策；没有证据的部分保留未知。

[反馈问题](https://github.com/Ethereal-Space-one/code2kb-agent-toolkit/issues) · [参与贡献](CONTRIBUTING.md) · [Apache License 2.0](LICENSE)

