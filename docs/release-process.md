# 公开版本发布流程

本文描述 Code2KB Agent Toolkit 自身的 GitHub 发布流程。

## 发布前

1. 更新 `VERSION`、`pyproject.toml`、README、`CHANGELOG.md`、路线图和兼容性说明；
2. 分别核对工程发行版本、文件协议兼容标识和使用方项目 `release_id`，只修改本次实际变化的层次；对外摘要按[发布说明模板](release-notes-template.md)核对。协议未变化时，摘要说明现有项目是否需要迁移即可，不把旧协议编号当作本次新能力；
3. 运行版本边界、单元测试、规范编号、一致性夹具、链接、公开内容和空白检查；
4. 创建全新虚拟环境，安装项目并验证 `code2kb --help`；
5. 创建最小示例并运行 `check`；
6. 在项目当前要求的 CI 全部通过后，通过 Pull Request 合并到受保护的 `main`；禁止直接推送发布提交。

发布前的最小回归命令为：

```bash
python3 -B -m unittest discover -s validation/tests -q
python3 -B scripts/check_spec_ids.py
python3 -B scripts/check_conformance.py --check-expected
python3 -B scripts/check_release_surface.py
python3 -B scripts/check_retrieval_scale.py
python3 -B scripts/check_markdown_links.py
python3 -B scripts/check_public_content.py
python3 -B examples/create_demo.py
python3 -m compileall -q validation scripts examples
git diff --check
```

## 发布

开发阶段允许在变更记录、路线图和兼容矩阵中一致标记“待发布”；版本边界检查会核对三者一致性。正式创建标签前，将三处改为正式发行状态并写入发布日期，再完成 PR 和必需 CI。

从 `main` 创建不可移动的 `vX.Y.Z` 标签和同版本 GitHub Release。Release Notes 应说明本次实际改变的层次、兼容性、用户可见变化和已知限制；文件协议未改变时不必在发布摘要重复旧编号，技术兼容矩阵仍保留准确编号。发布说明先进入 Pull Request 接受内容复核，再将同一正文写入 GitHub Release。标签对应 CI 通过后，在全新目录重复快速开始。

发布后复核 GitHub Release 正文、README、路线图和兼容矩阵，清除“候选”等过期状态；这一步检查的是公开表述，不替代协议兼容测试。若协议编号变化，必须同时提供旧格式读取、显式迁移、旧发布物审计以及新旧格式夹具，不能只批量替换版本字符串。

已发布标签禁止移动或覆盖。问题修复使用新版本；凭据泄露时先撤销或轮换凭据，再按 GitHub 敏感数据流程处理历史。

## 只读发行演练：本批已实现的范围

`Release rehearsal (read only)` 是独立工作流，只授予 `contents: read`。与发行准备相关的 Pull Request 会触发它；手动触发入口通常在工作流合并到默认分支后出现。手动输入 `reconcile_public_state` 默认关闭；开启后也只发出公开 GET 请求，不请求 OIDC、不使用 npm 凭据，不创建标签、Release、资产或 npm 版本，也不移动 `latest`。当前未将该演练设为必需合并检查。

演练先运行打包与核对回归，再从指定提交构建 Claude、Codex、DSH 三种归档。它记录并上传：

- `code2kb-claude-X.Y.Z.zip`
- `code2kb-codex-X.Y.Z.zip`
- `code2kb-dsh-X.Y.Z.tgz`
- `release-manifest.json`
- `SHA256SUMS.txt`

清单固定记录版本、完整源提交和每个归档的文件名、大小、SHA256、SHA512 integrity，不包含生成时间。ZIP 使用固定时间、顺序和权限；npm 继续使用标准 `npm pack --ignore-scripts` 并逐个核对归档成员。同一源提交、同一打包工具链下的重复构建须得到相同字节。压缩器或 npm 版本变化不承诺跨工具链字节相同，工作流日志保留实际工具版本。禁止为了“重建相同版本”覆盖已有输出目录或历史发行物。

上传后的独立 job 按本次上传返回的 artifact ID 下载，不按可变的跨运行名称寻找产物；它以构建 job 独立记录的清单 SHA256 为锚，重新检查清单、三种归档的实际字节、内部版本和 DSH 的 `gitHead`、精确文件集合与校验和。这个检查失败会使演练失败，不依赖下载 action 的摘要警告继续执行。

本地等价命令（输出目录须为新目录或空目录）：

```bash
commit=$(git rev-parse HEAD)
bundle=$(mktemp -d)
python3 -B scripts/package_plugins.py --commit "$commit" --output-dir "$bundle"
digest=$(sha256sum "$bundle/release-manifest.json" | cut -d ' ' -f 1)
python3 -B scripts/release_validation.py verify-bundle --bundle-dir "$bundle" --expected-commit "$commit" --manifest-sha256 "$digest"
```

如需公开状态核对，将最后一条命令的 `verify-bundle` 改为 `reconcile`。该命令只读固定 npm registry 和本仓库的公开端点，不携带认证、不跟随重定向，限制响应大小、超时和重试次数：

- npm 同版本已存在时，名称、版本、`gitHead`、integrity 和实际下载归档必须全部匹配；匹配则计划跳过发布，绝不重新发布。
- 同版本不匹配、元数据存在但归档不可下载、读取失败或核对期间 `latest` 改变时，立即停止。网络超时或发布命令退出码不能用来推断“尚未发布”。
- `latest` 仅接受本批范围内的 `X.Y.Z` 正式版本并按数字比较；已有更高版本时绝不计划回退。可能的向前推广也只标为需要单独批准，演练不执行。
- GitHub 标签如已存在，必须解析到清单中的源提交。已有 Release（包括草稿）一律不修改、不补传、不最终发布；资产集合、大小或摘要不同即停止，不能利用重试删除、覆盖或修补历史资产。已有资产这里只核对 GitHub 返回的摘要，不声称独立下载或密码学验证过。
- 每次核对结果只是当时的只读观察，不是未来写入的授权、锁或事务保证。

本批没有更改工程版本，也没有改变 `publish.yml` 的生产触发或权限边界。当前版本已经发行，因此新的准备提交或压缩字节与该历史版本不同时，公开核对应失败；这不是重发当前版本的理由。公开内容检查与路径拒绝列表是打包卫生检查，不替代全面秘密扫描或安全审计。

## 生产接入：仍需单独审阅的后续步骤

以下是下一步设计约束，不是已启用的能力：

1. **唯一归档生产者。** 发行模式下复用 CI 仍运行打包回归；只有强制依赖唯一发行 package job 时才跳过 CI 中重复的归档构建。可采用默认保持现有行为的显式 `workflow_call` 输入，或分离回归与归档 job。当前生产 CI 尚未改动，不能称其已经实现跨工作流“只构建一次”。
2. **标签与版本。** 正式发行仍须检查标签恰为 `v$(cat VERSION)`，源提交属于受保护的 `main`，清单、各插件清单和标签版本一致。标签规则、环境审批和 npm Trusted Publisher 配置是工作流之外的授权边界，不能仅靠标签中可修改的脚本代替。
3. **最小权限分离。** npm publisher 保持 OIDC-only，不 checkout 或执行源码，不安装依赖，不加入长效 npm token；GitHub Release 写入放在另一个仅 `contents: write`、没有 `id-token: write` 的 job。手动演练不进入这些 job。
4. **不盲目重试。** npm 写入前先只读核对；已经精确匹配则跳过，冲突或未知则停止。发布结果不确定时，只进行有界只读等待和字节核对，不重新执行发布。所有版本的生产写入须串行；`latest` 推广前再读当前值并比较，不能只使用之前演练的观察。GitHub concurrency 默认可能替换旧的 pending job，队列策略必须单独验证，不能声称 `cancel-in-progress: false` 已保留全部排队发行。
5. **同一归档，不重建。** 在唯一 package job 生成完整清单与校验和；npm 与 GitHub 使用同一次上传的归档并重新验证独立摘要。GitHub 先创建属于本次发行的全新草稿，上传全部文件，列举并验证精确集合和实际字节后才最终发布。已有标签、Release 或同名资产不自动接管；禁止 `--clobber`、删除后重传、替换资产、移动标签或把历史草稿当作本次新建草稿。
6. **不可变发行。** 先在后续正式版本启用并确认 release immutability，再采用“新草稿 → 完整资产 → 校验 → 发布”。该设置只影响未来发行；不因此修改既有 v2.4.0。npm staged publishing 可作为额外人工 2FA 审批方案，但本批不激活或改变 npm 端设置，也不增加候选版本工作流。

参考：[GitHub 不可变发行](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)、[环境保护](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)、[npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/)、[npm staged publishing](https://docs.npmjs.com/staged-publishing/)。
