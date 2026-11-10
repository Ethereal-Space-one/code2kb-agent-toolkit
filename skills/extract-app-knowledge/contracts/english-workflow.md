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

## Review and publish

Use the [release contract](release.md). For policy review or independent verification, use the [review procedure](../references/发布与维护.md#从提取到模块批准).

## Optional batch review

For a multi-module handoff, follow the [batch procedure](../references/长任务续跑.md#可选批次方式) and its input-validity rules. For optional retrieval readiness, use the [release and retrieval procedure](../references/发布与维护.md#交稿预检与批次收口).
