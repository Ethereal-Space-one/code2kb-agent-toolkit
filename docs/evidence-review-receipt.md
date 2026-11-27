# 从源码证据到可对账的回执

三个独立的检查分别回答：「这句话有依据吗？」「这次应该重看哪里？」「哪一端真的发布了？」任何一步都不能代替人工批准。

## 1. 让一个尚未看过答案的 Agent 提取或复核

用当前源码安装的 Python 环境，选 **extract** 让 Agent 从头提取整数业务门槛；选 **review** 让它判断给出的结论是否成立。每次生成两次真实临时 Git 提交与 10 个合成对照，不用真实客户仓库、API 密钥或模型调用。随机种子只保存在评分方。公开的生成器不是私有保留题库。

```bash
trial=$(mktemp -d)
mkdir "$trial/reviewer" "$trial/grader"
python3 -m validation.evidence_trial prepare --task extract \
  --pack "$trial/reviewer/questions.json" --key "$trial/grader/key.json"
```

只给另一段全新会话 **questions.json 和 prepare 打印的 file_sha256**，不要给它评分目录、生成器或本地全盘访问。请它在不查其他资料的前提下按包内说明答题，保存为 reviewer/answers.json。引用必须匹配本题、函数和目标提交；没有证据时不能猜。评分接受打印的规范 JSON 摘要或实际文件字节摘要，并记录使用哪一种。

```bash
python3 -m validation.evidence_trial score --pack "$trial/reviewer/questions.json" \
  --key "$trial/grader/key.json" --answers "$trial/reviewer/answers.json"
```

分项报告同时列出正常题、错误版本、错误片段和无证据题；提取题还加入新旧版本混放，审阅题则加入有证据直接反驳的情况。全答未知不能满分。退出码 0 全部正确、1 有错答、2 输入无效。此分数不是生产准确率、模型间排名或自动审核资格，不能把生成器或测试中的标准答案充当独立审阅。

## 2. 用变更范围分派业务规则复核，而非重写整个知识库

先运行[全项目预览](source-upgrade-preview.md)，保留计划摘要，然后用同一源码和知识目录复算：

```bash
code2kb preview-upgrade --project-root "$KB" --all-modules --plan \
  --repository-id backend --new-commit "$NEW_COMMIT"
code2kb preview-upgrade --project-root "$KB" --all-modules --plan --review-queue \
  --repository-id backend --new-commit "$NEW_COMMIT" --expect-plan-sha256 "$PLAN_SHA"
```

第二条输出每个模块的工作单：从实际改动行、已核对的关系路径到事实、受影响正文和下游主题。先看 disposition，再看模块的 rule_scope：

- named_rules_and_topics：把列出的事实和主题交给该模块复核者；consumer_topics：跨模块只核对下游主题。
- baseline_only：没有发现需重新解释的语义规则，但仍按 baseline 列表迁移固定提交、重建证据、刷新原有批准。all_module_rules 表示该模块无法细分。
- all_rules：整项目复核。比如同一文件内另有改动超出已验证行段、变化触及没有已核对关联的事实、新增/删除/位移行、缺少归属、关系未解、运行证据过期或工作区不干净。先解决 uncovered_diff_paths、untraced_changed_facts、fallback_reasons，不要用空事实列表放行。

执行后应重新走原来的确认证据、prepare、审核和发布步骤。工单是只读的复核范围，不会重写事实、继承批准或替人确认新版本。依赖范围只涵盖已有记录，不声称发现了所有隐式调用。

## 3. 维护者：按同一个提交开具发布回执

从完整的源码仓库执行；指定完整 Git 提交。连续手顺不是发布命令：

```bash
python3 -B scripts/release_receipt.py --expected-commit "$COMMIT"
python3 -B scripts/release_receipt.py --expected-commit "$COMMIT" \
  --bundle-dir "$BUNDLE" --manifest-sha256 "$INDEPENDENT_MANIFEST_SHA256" \
  --online --ci-run "$MAIN_PUSH_RUN_ID"
```

离线时只核对本地固定提交和可选归档，CI、npm 和 GitHub 显示 pending。线上模式仅限公开 GET。使用**相同提交、main 推送产生的 CI**，不接受 PR、Dependabot 或其他仓库的成功记录；指定运行尝试的 CI Gate 和依赖作业必须全部成功。npm 核对同版本、gitHead、版号标签、实际 tarball 和摘要，latest 仅观察不推广。GitHub 核对标签、正式且不可变的 Release 和服务端资产摘要；这是元数据核对，不声称独立下载过每一份 GitHub 资产。缺失、不可见、读取失败和已知失败不会记为发布成功。退出码 0 表示所有列出的观察均通过；2 表示仍待证；1 表示阻断或输入有误。回执不替代签名、生产 CI、平台权限或所有者发版授权。

## English quick reference

1. Run the blind trial in the installed Python environment. Give only the question packet and its file SHA-256 to a fresh reviewer. Use **extract** to derive numeric rules (or abstain), **review** to judge proposed claims. Score separately; synthetic results are not production performance.
2. Generate the pinned upgrade plan, then replay its digest with **--review-queue**. Dispatch the listed facts and consumer topics; refresh baseline evidence and approvals separately. Unaccounted hunks, unverified dependencies and unresolved ownership require broader review.
3. From the source checkout, observe the exact main-push CI run, local package bytes, public npm bytes and GitHub asset metadata. Offline or absent proofs remain pending. Nothing in these commands publishes, promotes or authorizes a release.
