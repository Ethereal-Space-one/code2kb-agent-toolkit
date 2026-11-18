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

## 不具备发布权限的演练

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

这套工程改造不升产品版本，不移动或重发 v2.4.0。当前版本已经发行，因此新的准备提交或压缩字节与该历史版本不同时，公开核对应失败；这不是重发当前版本的理由。公开内容检查与路径拒绝列表是打包卫生检查，不替代全面秘密扫描或安全审计。

### 怎么验证两个发布端拿到的是同一批文件？

同一次只读工作流还会建一个没有远端的临时仓库，生成 `999.<run_id>.<attempt>` 的合成版本和一份明确标记演练的发行说明。这个提交只用来打包，不推送、不打标签，不改原仓库的 `VERSION`。在独立 job 以本次上传的 **artifact ID** 下载，再分别运行生产工作流里的验包、npm 和 GitHub 操作。远端由本地模拟服务替代：只检查它们**会收到哪些字节、会执行几次写入、何时必须中止**。模拟不是对 npm OIDC、GitHub 令牌可见性、环境保护或线上不可变设置的实测。

原来的真实提交打包、上传后复核、可选的公开 GET 核对仍可单独使用。两种演练都没有生产环境、OIDC 或内容写权限。测试可在本地从仓库根目录运行：`python3 -B -m unittest discover -s .github/tests -p test_release_promotion.py -v`。

## 未来正式标签走什么路径？

**触发与授权分开。** 生产入口仍是 `.github/workflows/publish.yml` 的新标签推送，不是演练或手动 dispatch。它只接受本仓库、第一次运行、比 2.4.0 更新的正式 `vX.Y.Z`；不接受移动／强推、删除、旧版本或重新运行的标签。标签、`VERSION`、源提交与受保护的 `main` 祖先必须一致。正常 push/PR 的 CI 仍构建全部插件；标签 CI 仍跑同样的矩阵、打包回归、macOS 冒烟与 CI Gate，只把最终归档的构建交给它强制依赖的那个发行打包 job。归档只从该次调用的固定提交生产一次，两端不重新打包。

**所有者在真实发行前逐项办理；本次不代办：**

1. 按发布前清单合并版本与文档，将经审阅的正文放在 `docs/X.Y.Z-release-notes.md`。确认这个确切 SHA 在受保护的 `main` 上；不要提前创建标签。
2. 检查仓库的 [Release immutability 设置](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)已启用、标签受到不可移动规则保护，并核对 `npm-release` 环境及 npm Trusted Publisher 仍指向本仓库的 `publish.yml`。能给出管理员只读证据的人应先确认设置；带 `contents: write` 的发布令牌没有管理读取权限，工作流**不能**把 404 当作已启用，也不会申请管理员 PAT。发布后检查 `immutable=true` 不是发布前验证的替代品。
3. 仅在确实准备发布时，由所有者将仓库 Actions 变量 `RELEASE_ARMED_REF` 设置为**一个确切的** `vX.Y.Z@<完整40位提交SHA>`，然后创建该新标签。默认没有匹配值就不能发布。一次只授权一个版本；完成、取消或失败后清除授权并留下记录。全局 concurrency 串行跨版本运行，但默认队列只保留一个 pending，新请求可能替换旧请求；它不是持久 FIFO。
4. 确认 GitHub 草稿可见、npm 可以使用现有 OIDC 受信身份。自动化在本地模拟过这些分支，**尚未使用真实的未来版本、该写令牌或该 OIDC 身份做线上验证**。不要为了测试本 PR 而改变这些设置、重建旧标签或走真实发布流程。

**交接。** 完整发行集合恰好为三个归档、`release-manifest.json` 和 `SHA256SUMS.txt`。生产者分别固定清单和校验文件 SHA256。消费者按同一不可变 artifact ID 下载，在自己的空白 runner 逐文件核对名称、大小、内容、版本与提交，并从校验过的 Claude ZIP 读取该版本的发布说明，仅作为数据使用。写入 job 不 checkout 源码、不执行归档脚本、不安装包依赖。任何写入前、GitHub 正式发布前都会再次核对标签。外部管理员若能绕过标签保护，跨服务流程本身不能提供原子事务。

| 顺序 | 可以做什么 | 必须停在哪里 |
| --- | --- | --- |
| GitHub 前置核对 | 用具有 push 可见性的独立 GitHub 令牌仅 GET、分页检查所有草稿和公开 Release | 不能确认 push 可见性、无法读完整清单，或同标签已存在任何发行记录，均在 npm 写入前停止；匿名 404 不算草稿不存在。 |
| npm | `npm-release` 环境，只有 `id-token: write`；只对固定 npm registry 的 `code2kb-dsh` 上传那一个已校验的 tgz，一次、不执行脚本。创建版号专用 dist-tag，例如 `release-2.5.0`，不改变 `latest`。 | 比较现有版本、`gitHead`、integrity、下载字节、版号标签和当前 `latest`。已完全一致则跳过；缺失、冲突、变动或身份不明不可当已成功。新版本须高于当前 `latest`。这里没有 `npm dist-tag` 操作。 |
| GitHub Release | 单独的 `contents: write` job，不获 OIDC。再次拒绝既有同标签记录；只创建全新草稿，并只按本次创建响应中的数值 ID 写入与检查。五份文件均上传后，对照资产精确名单、长度、摘要及实际下载字节和审阅正文，才转为正式版；不指定为 GitHub Latest，随后复核公开字节和不可变状态。 | 不接管草稿、不补传历史文件、不覆盖、不删、不移动标签。任一处失败都报告停止；不会把同名草稿或另一次运行的 ID 当作自己的。 |

**使用方注意。** 新版本发布后可按确切版号安装，例：`npm install code2kb-dsh@2.5.0`（仅说明格式，不代表 2.5.0 已存在）。裸包名仍跟随原有 `latest`。如未来需要向前推广，所有者必须**另行批准**，先重新读取当前状态、核对已公开的两个目的地和目标归档，不能回退现有更高版本。本仓库没有增加推广命令、长期认证令牌或 staged-publishing 配置。

**失败恢复不是重跑。** npm 命令超时／返回非零后只做有界只读核对，绝不重新发送发布。读取超时、返回异常、读回不匹配或标签改变均须人工核对。若 npm 已成功而 GitHub 失败，npm 版号可能已永久占用，GitHub 可能已有未完成草稿；若最终响应丢失，GitHub 发行也可能实际已公开。保留本次 ID、五份文件、两份摘要及 Actions 记录，先只读核对两端；禁止再次触发写入、重建同版本、移动标签、覆盖资产或盲删草稿。由所有者单独决定恢复或用新版本修正。任何服务中断都不等价于“尚未发布”。

参考：[GitHub 不可变发行](https://docs.github.com/en/code-security/concepts/supply-chain-security/immutable-releases)、[环境保护](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)、[npm Trusted Publishing](https://docs.npmjs.com/trusted-publishers/)。
