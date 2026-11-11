# 插件安装与打包

Claude Code 和 Codex 共用同一份知识提取 Skill、规范和 Python CLI。DeepSeek Harness 通过 npm 插件注册同一套工作流。CLI 需要 Git 和 Python 3.9+。写入命令需要支持 `fcntl` 的平台，例如 Linux 或 macOS。

## 从检出安装

使用包含插件清单的干净 Git 检出。从仓库根目录执行对应命令。

- **Claude Code**：运行 `claude --plugin-dir .`，在会话中调用 `/code2kb:extract-app-knowledge`。也可向 Claude Code 的 marketplace 添加该检出，再安装 `code2kb@code2kb`。
- **Codex**：运行 `codex plugin marketplace add .` 和 `codex plugin add code2kb@code2kb`，再开一个会话使用 `extract-app-knowledge`。
- **DeepSeek Harness**：运行 `dsh plugin --profile desktop add code2kb-dsh`，再开一个会话使用 `code2kb`。

## 从提交构建

打包机需要 Git、Python 3.9+ 和 npm。将下例的 `HEAD` 换成要交付的提交或标签，输出目录使用新目录。

```sh
python3 -B scripts/package_plugins.py --commit HEAD --output-dir /tmp/code2kb-plugins
```

命令生成 DSH 的 `.tgz` 和 Claude Code、Codex 各自的 `.zip`。归档只包含指定提交中的打包路径。Claude Code 可直接用 `--plugin-dir` 加载其 ZIP。Codex 仓库安装使用该提交的 marketplace，OpenAI 官方目录送审使用 Codex ZIP。

## 发布设置

- **npm**：为 `code2kb-dsh` 配置 [Trusted Publisher](https://docs.npmjs.com/trusted-publishers/)，绑定本 GitHub 仓库、`publish.yml` 和 `npm-release` 环境。工作流校验 `vX.Y.Z` 与 `VERSION`，并要求该提交已进入 `main`。已在 npm 使用的版本号需在下次发布时随工程版本统一递增。
- **Claude Code**：公开收录按 [Claude Code 插件发布指南](https://code.claude.com/docs/en/plugins/publish) 提交。
- **OpenAI**：使用 [官方插件提交入口](https://developers.openai.com/plugins/deploy/submission)，选择 Skills only，上传 Codex ZIP。本地 Git 和 Python 依赖以 [Desktop only](https://developers.openai.com/plugins/deploy/desktop-only) 声明。

## English

Code2KB bundles its extraction skill and CLI for all three hosts. The CLI needs Git and Python 3.9+. Write commands require a platform with `fcntl`, such as Linux or macOS.

- **Claude Code**: Start `claude --plugin-dir .` from a clean checkout with the plugin manifest, or pass the Claude ZIP. Invoke `/code2kb:extract-app-knowledge`.
- **Codex**: From a clean checkout with the marketplace manifest, run `codex plugin marketplace add .`, then `codex plugin add code2kb@code2kb`. Start a new session and use `extract-app-knowledge`.
- **DeepSeek Harness**: Run `dsh plugin --profile desktop add code2kb-dsh` and use the `code2kb` skill in a new session.

Build the three archives with `python3 -B scripts/package_plugins.py --commit HEAD --output-dir /tmp/code2kb-plugins`. Replace `HEAD` with the desired release commit or tag. For npm releases, configure [Trusted Publishing](https://docs.npmjs.com/trusted-publishers/) for `publish.yml` and the `npm-release` environment. Use the [Claude Code](https://code.claude.com/docs/en/plugins/publish) and [OpenAI](https://developers.openai.com/plugins/deploy/submission) submission guides for public directory listings. The OpenAI package is Desktop only.
