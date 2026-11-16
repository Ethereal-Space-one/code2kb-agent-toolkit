# English extraction workflow

**Reader: the executing AI. Use English for the conversation. Keep these instructions out of knowledge content and retrieval corpora.**

Read the [core contract](core.md), then load the shared contract for the current stage. For a full project, follow each stage in order and load its details when needed.

| Current task | Shared contract |
| --- | --- |
| Scope and entry inventory | [Inventory](inventory.md) |
| Pinned source evidence and specifications | [Module evidence](extract.md) |
| Business and engineering knowledge | [Authoring](author.md) |
| Question checks, impact review and candidate preparation | [Quality evaluation](evaluate.md) |
| Approval, publication, audit and rollback | [Release and maintenance](release.md) |

The shared contracts use Chinese text and apply to both output languages. Follow the project's `content_language` (`zh-CN` by default or `en`) and preserve the [fixed protocol identifiers](../../../spec/09-固定章节与标识符.md). For setup and CLI examples use the [English guide](../../../docs/usage.en.md). For cross-session handoff use the [resume procedure](../references/长任务续跑.md#空白上下文接手) and verify current project files and Git state.

Load optional extensions only when the task or project configuration calls for them.

## Optional UI behavior evidence

When the task asks about controls, their state meanings or interaction changes, read the [UI behavior contract](../../../docs/ui-behavior-contract.md). From the pinned source, trace visibility, enabled and busy conditions separately, then dynamic labels, event guards, state writes and asynchronous success, failure and retry. Distinguish same-label controls by their page or panel scope. Opening a local dialog is not sending a request; hiding a control is not server authorization; a returned request is not verified persistence. Preserve unknown paths instead of inventing transitions.

Establish existing fact IDs first, then opt into the single `## 界面交互规格` JSON section only when needed. Keep the literal heading and machine fields even in English output; do not create an empty placeholder section. Write reader-facing conclusions into the existing rules and FAQ files and keep source navigation in engineering content. Internal JSON is not a business retrieval corpus. The [synthetic source and expected-answer matrix](../../../conformance/ui-behavior/README.md) illustrate limited static behavior, not publication approval or observed production behavior.

## Review and publish

Use the [release contract](release.md). For policy review or independent verification, use the [review procedure](../references/发布与维护.md#从提取到模块批准).

## Optional batch review

For a multi-module handoff, follow the [batch procedure](../references/长任务续跑.md#可选批次方式) and its input-validity rules. For optional retrieval readiness, use the [release and retrieval procedure](../references/发布与维护.md#交稿预检与批次收口).
