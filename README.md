# Code2KB Spec

**简体中文** · [English](README.en.md)

![Code2KB Spec：从固定源码提交到可审核的知识库](assets/readme/overview.svg)

借助 AI 从固定源码提交提炼业务逻辑，建立**有证据、可审核、可发布**的知识库，供问答机器人检索业务知识。

Code2KB Spec 是一套面向 AI 编码助手的提示词工程与知识文件规范，提供 Skill、模板和 Python 参考工具。AI 按 Skill 阅读源码、取证并写成业务与研发知识；工具检查文件、证据和发布状态。它适合想把代码中的行为整理成可追溯业务知识，再交给机器人问答的团队。

## 工作流程与产物

`固定 Git 提交 → AI 盘点与取证 → 编写知识 → 审核 → 双版发布 → 外部检索与机器人问答`

| 产物 | 内容 | 使用者 |
| --- | --- | --- |
| 知识源 | 功能大纲、模块规格、业务与研发正文、待确认事项 | 知识维护者取证、复核和修订；内部规格及过程文件不进入机器人索引 |
| 发布版本 | 分离的业务版与研发版、版本清单和当前版本指针 | 业务版是业务问答的正文来源；研发版供研发人员追溯实现；清单和指针用于核对版本 |
| 可选检索扩展 | 从已审核正文生成的主题单元及独立审计信息 | 外部 FTS 或向量索引按受众导入相应单元，供机器人召回证据 |

源码升级时，1.0.0 还可生成[只读复核计划](docs/1.0.0-public-contract.md)，帮助定位需重新解释的知识；它不会自动改写知识或批准发布。

<details>
<summary>查看源码取证与双版知识示意（3 张）</summary>

图中的代码、文件名和事实编号仅用于说明结构。

![固定源码提交后盘点入口，适配器只输出待复核候选](assets/readme/source-adapters.svg)

![从固定源码锚点记录可核对的结构化事实](assets/readme/evidence.svg)

![同一业务知识分别进入业务版与研发版](assets/readme/two-views.svg)

</details>

<details>
<summary>查看可选检索与源码升级复核示意（2 张）</summary>

检索扩展只处理已审核的发布知识；升级计划只读，不自动迁移或批准。

![从已审计的发布版生成按主题组织的可选检索单元](assets/readme/retrieval.svg)

![比较固定源码提交并生成只读升级复核计划](assets/readme/upgrade-review.svg)

</details>

## 快速体验

需要 **Git** 和 **Python 3.9+**。内置示例无需准备自己的源码：

```bash
git clone https://github.com/Ethereal-Space-one/code2kb-spec.git
cd code2kb-spec
python3 -B examples/create_demo.py
```

命令会在临时目录创建小型源码仓库和知识项目，运行 `check`，并打印项目路径。示例用于体验文件结构与检查流程，不会自动生成完整知识库。

### 从发布知识到机器人问答

机器人可用外部 FTS 或向量索引召回业务知识，再由问答模型依据命中的正文组织回答。本项目提供的受审计机器索引路径是[可选检索扩展](docs/retrieval-contract.md)：先发布双版知识，再生成、评测并审计业务检索单元；业务机器人只导入业务单元。若使用方直接拆分基础业务版建立自有索引，分块、条件与未知边界保留、受众隔离和版本切换须自行负责；这不属于本项目受审计的索引路径。`retrieval-query` 只返回候选证据，不生成或验证最终答案。

[PetClinic 公开案例](conformance/public-source/petclinic/README.md)演示了这条路径的一段：固定源码中的“按姓氏查询主人”分支被写成业务知识并生成检索单元；[SQLite FTS5 运行记录](conformance/public-source/petclinic/fts5-run.json)显示，“空白姓氏”可召回该单元。这个小样本验证证据定位，不代表机器人回答或线上表现已通过测试。

## 创建自己的知识项目

### 1. 安装并固定源码版本

知识项目应与源码仓库分开存放。从模板创建配置：

```bash
python3 -m pip install -e .
mkdir -p /path/to/knowledge-project
git init /path/to/knowledge-project
cp templates/知识库配置.example.json /path/to/knowledge-project/知识库配置.json
git -C /path/to/source-repo rev-parse HEAD
```

编辑 `知识库配置.json`：删去不用的示例仓库，将每个 `repositories` 条目的 `path` 改为本机源码仓库绝对路径，`commit` 改为对应的固定提交 SHA。

### 2. 盘点入口并编写知识

让 AI 编码助手读取 [Skill](skills/extract-app-knowledge/SKILL.md)。先核对配置与固定提交，建立 `知识源/功能大纲.md`；再按模块取证、写业务与研发正文。例如：

```text
请读取 <code2kb-spec-root>/skills/extract-app-knowledge/SKILL.md。
知识项目是 /path/to/knowledge-project。先核对配置中的固定源码提交，
盘点全范围入口并生成知识源/功能大纲.md；明确登记未知项，
不要把源码推断写成线上运行结果。
```

### 3. 检查、审核与发布

知识源写入后，可随时运行结构检查：

```bash
code2kb check --project-root /path/to/knowledge-project
```

按模块完成影响复核、结论复核、候选准备及授权审核后，再发布并审计：

**审批前选择方式**：人工审核用 `approve`，记录实际审核人的明确批准；自动审核用 `policy-review`，前提是项目已有有效的预授权策略和本次审核记录。策略不覆盖的模块或命中人工门禁的包，保持草稿并交人工审核。两种方式都按模块执行；AI 自检或 `check` 通过不会自动批准。

```bash
code2kb publish --project-root /path/to/knowledge-project --release-id my-kb-v1
code2kb audit-release --project-root /path/to/knowledge-project
```

`check` 通过不等于知识已可发布。`impact`、`confirm-claims`、`prepare` 和审核命令的参数见[使用指南](docs/usage.md)。

## 文档与支持

- [使用指南](docs/usage.md)：完整操作手顺与命令
- [规范](SPEC.md)：文件、证据、审核与发布要求
- [检索扩展](docs/retrieval-contract.md)：可选检索单元与外部索引边界
- [版本与兼容性](docs/versioning.md)：工程版本、知识文件协议和项目发布版本
- [问题反馈](https://github.com/Ethereal-Space-one/code2kb-spec/issues) · [贡献指南](CONTRIBUTING.md) · [变更记录](CHANGELOG.md)

## 使用边界

源码不能单独证明线上运行、业务政策或授权结果；缺少运行证据时须保留未知项。项目不自带具体业务知识、机器人部署、生产 FTS／向量服务或最终回答模型。

当前工程版本：`1.1.0`。新项目默认文件协议为 `c2kb-file/1`；旧 `0.8.3` 项目仍受支持。[保证范围矩阵](docs/assurance-matrix.md)区分工具检查与人工复核。本项目采用 [Apache License 2.0](LICENSE)。
