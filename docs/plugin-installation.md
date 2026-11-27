# 插件安装与打包

Claude Code、Codex 和 DeepSeek Harness 共用同一份知识提取 Skill 和 Python CLI。运行 CLI 需要 Git 和 Python 3.9+；写入命令需要支持 `fcntl` 的平台，例如 Linux 或 macOS。

## 先选定你要的版本

- **安装已发行的 2.4.1**：[v2.4.1 Release](https://github.com/Ethereal-Space-one/code2kb-agent-toolkit/releases/tag/v2.4.1) 提供插件附件。Claude Code / Codex 也可选干净的 `v2.4.1` 检出；DSH 用 `dsh plugin --profile desktop add code2kb-dsh@2.4.1`。[npm 2.4.1](https://www.npmjs.com/package/code2kb-dsh/v/2.4.1) 使用 `release-2.4.1` 标签。核对裸包名将安装哪一版：`npm view code2kb-dsh dist-tags --json`。验证 2.5.0 的源码改动请走下面的指定提交流程；同一版号可能有不同提交。
- **验证未发布的取证指引**：记录评审对象的完整 Git 提交号，另取该提交的干净检出。不要用 npm 正式包替代，也不要仅核对工程版号或入口 `SKILL.md`；候选提交可沿用旧版号和入口，却已改变其引用的取证、复核契约。

## 从指定提交安装

在上一步选定的干净检出根目录操作：

| 宿主 | 安装及发现 |
| --- | --- |
| Claude Code | 运行 `claude --plugin-dir .`，在该会话中查找 `/code2kb:extract-app-knowledge`。若使用本地 Claude ZIP，先解压到空目录，再将该目录传给 `--plugin-dir`。 |
| Codex | 运行 `codex plugin marketplace add .`，再运行 `codex plugin add code2kb@code2kb --json`。保留返回的 `installedPath`；用 `codex plugin list --marketplace code2kb --json` 查看是否启用，在新会话中查找 `code2kb:extract-app-knowledge`。测试候选时可在单独的临时 `CODEX_HOME` 完成安装和检查，不干扰日常插件。 |
| DeepSeek Harness | 正式版见上。候选版先在下方按目标提交打包，再运行 `dsh plugin --profile desktop add /absolute/path/to/package.tgz`（替换为实际归档的完整路径）。Desktop 按[宿主说明](https://github.com/deepseek-ai/deepseek-harness/blob/master/apps/cli/src/plugin.ts)先启动一次初始化、完全退出后再执行命令；重开后查看 `code2kb` Skill。 |

### 安装后：核对实际使用的 Skill

从含下列脚本的工具仓库运行，不从解压包运行。把 `REV` 换成目标标签或完整提交号，把路径换成**宿主实际使用的工具包根目录**：Codex 取安装返回的 `installedPath`；Claude 取传入 `--plugin-dir` 的目录；DSH 取注册的 `code2kb` 指令在 “Bundled toolkit root” 下给出的路径。

```sh
python3 -B scripts/verify_installed_skill.py --commit REV --installed-root /path/to/host/toolkit
```

命令读 Git 中的提交，不读取工作树作为基准。它按文件核对整个 `skills/extract-app-knowledge/`，缺失、多余或字节不同均返回非零；即使入口文件没变，也能发现过期契约。通过只表示 **Skill 文件一致**，不表示宿主已加载、模型已执行或结论正确；仍须在新会话确认上表中的技能。若同版号缓存仍指向旧内容，用独立测试配置重新安装再核对，不要改 npm 标签。

## 从提交构建

打包机需要 Git、Python 3.9+ 和 npm。将 `REV` 换成要交付的提交或标签，输出目录用新的或空的目录。

```sh
python3 -B scripts/package_plugins.py --commit REV --output-dir /tmp/code2kb-plugins
```

归档只包含指定提交中的打包路径。`release-manifest.json` 记录源提交与归档摘要。Codex 仓库安装用该提交的 marketplace，独立的 Codex ZIP 用于目录送审，不是一个 marketplace。

## 发布设置

- **npm**：为 `code2kb-dsh` 配置 [Trusted Publisher](https://docs.npmjs.com/trusted-publishers/)，绑定本 GitHub 仓库、`publish.yml` 和 `npm-release` 环境。工作流校验 `vX.Y.Z` 与 `VERSION`，并要求该提交已进入 `main`。已在 npm 使用的版本号需在下次发布时随工程版本统一递增。
- **Claude Code**：公开收录按 [Claude Code 插件发布指南](https://code.claude.com/docs/en/plugins/publish) 提交。
- **OpenAI**：使用 [官方插件提交入口](https://developers.openai.com/plugins/deploy/submission)，选择 Skills only，上传 Codex ZIP。本地 Git 和 Python 依赖以 [Desktop only](https://developers.openai.com/plugins/deploy/desktop-only) 声明。

## English

**Install published 2.4.1:** Get the plugin assets from the [v2.4.1 release](https://github.com/Ethereal-Space-one/code2kb-agent-toolkit/releases/tag/v2.4.1), check out `v2.4.1` for Claude Code/Codex, or run `dsh plugin --profile desktop add code2kb-dsh@2.4.1` for DSH. [npm 2.4.1](https://www.npmjs.com/package/code2kb-dsh/v/2.4.1) uses the `release-2.4.1` tag. Check what a bare package name would install with `npm view code2kb-dsh dist-tags --json`. For a review of 2.5.0 source changes, use the exact-commit path below: different commits can share the same version.

For **unreleased extraction instructions**, take a clean checkout of the exact reviewed commit. A candidate can keep the same version and top-level skill file while changing the contracts it loads.

- **Claude Code**: Run `claude --plugin-dir .` from that checkout (or pass the directory extracted from the Claude ZIP). Look for `/code2kb:extract-app-knowledge` in that session.
- **Codex**: Run `codex plugin marketplace add .` followed by `codex plugin add code2kb@code2kb --json`. Save the returned `installedPath`. Check `codex plugin list --marketplace code2kb --json` for an enabled plugin; look for `code2kb:extract-app-knowledge` in a new session. Use a separate temporary `CODEX_HOME` throughout a candidate test to avoid your regular plugin cache.
- **DeepSeek Harness**: Build the exact commit with `python3 -B scripts/package_plugins.py --commit REV --output-dir /tmp/code2kb-plugins` into a new or empty directory. Use `dsh plugin --profile desktop add /absolute/path/to/package.tgz` with the actual tarball path, not a registry package with the same version. For Desktop, initialize the profile by opening the app once and fully quit it before the command. Reopen it and look for `code2kb`.

**Verify the host's copy:** From a toolkit checkout that includes the verifier, run `python3 -B scripts/verify_installed_skill.py --commit REV --installed-root /path/to/host/toolkit`. Use the target tag or full commit, and the host's actual toolkit root: Codex's `installedPath`, the directory passed to Claude, or the “Bundled toolkit root” in DSH's registered skill. This read-only check compares every extraction skill file to Git, not the worktree, and fails on changed, extra or missing files. A match does not prove host activation, model execution or answer quality.

The three builds include a manifest identifying their source commit. Use the checkout's marketplace for local Codex installation; the Codex ZIP is for directory submission. The CLI needs Git and Python 3.9+; write commands require `fcntl`. See the [maintainer release process](release-process.md) for publication.
