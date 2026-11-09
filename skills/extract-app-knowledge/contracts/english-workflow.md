# English extraction workflow

**Reader: the executing AI. Instruction language: English. This file is not knowledge content and must never enter a release or retrieval corpus.**

Use this workflow for English interaction. Do not also load the Chinese workflow as an additional instruction set. The shared specification and templates define one format; their fixed Chinese tokens are protocol identifiers, not instructions to write Chinese prose. Detailed references can be read as needed without changing the selected output language.

## Establish the task

1. Read the project's `知识库配置.json`, current functional inventory, Git state and any existing release/review records. Read this tool's `VERSION`; its version, `standard_version` and a content `release_id` are independent.
2. `content_language` controls knowledge prose: `en` or `zh-CN`, defaulting to `zh-CN`. English conversation does not change the default. For a new English-output task, explicitly configure `en` with the user-provided project settings before authoring. Do not infer that existing content has been translated.
3. Keep source repositories read-only. Use configured repository IDs, pinned Git commits and repository-relative anchors, never an uncommitted working tree with old line numbers. Restore long tasks from project files and Git, not chat memory.
4. User instructions determine scope and authorization. Reading these instructions, passing checks or running another AI does not authorize publication, remote pushing or bot integration.

## Inventory, then gather evidence

- Establish repositories, worktrees, submodules, build units and actual system roles before choosing technology-specific guidance. Inventory applicable pages, actions, HTTP/RPC, messages, callbacks, schedules and commands. Adapters discover candidates; they do not prove complete coverage or business meaning.
- Write `知识源/功能大纲.md`, recording modules, entries, audience, scope, fixed evidence and gaps. Do not claim a pilot covers the whole project. Only mark the inventory complete after its declared scope has actually been checked.
- For each module, trace entry conditions, callers, service branches, data producers and consumers, errors and visible feedback. Distinguish request acceptance, acknowledgement, persistence and completion. Defaults, runtime values and deployment evidence are different facts.
- Preserve fixed IDs and anchors. Separate code-backed behavior, inference, business confirmation, runtime observation and unknowns. UI hiding is not service authorization; a missing caller does not prove abandonment. Record unavailable dependencies and dynamic behavior as gaps.
- Use existing specification templates and precise fixed table labels. Before preparing a candidate, disposition each module entry in `## 大纲覆盖核对`: verified facts, unresolved gaps or reasoned exclusions. High-impact and dynamic-configuration checks remain applicable in English.

For investigations, load only relevant details: [full-stack inventory](../references/全栈范围盘点.md), [cross-language scenarios](../references/跨语言场景取证.md), and [evidence procedures](../references/模块取证与规格.md). These references are in Chinese; extract their technical requirements, not their prose language. The [fixed-token contract](../../../spec/09-固定章节与标识符.md) is authoritative.

## Author knowledge, not instructions

- For English output, declare `content_language: en` in every business and engineering knowledge file. Write its title, explanatory text, question cases, topic metadata and unknowns in English. Domain/module names may be English. Retain product names, literal source identifiers and quotes when needed.
- Preserve protocol filenames, fixed headers, enum values, IDs and JSON keys exactly. API/METHOD detail labels remain fixed even when their values are English. Do not translate them or invent an English file layout. An explicit language declaration binds intent; it does not certify translation quality.
- Keep each answer's conditions, result, exceptions, failures and unknowns together. Use the conventions `Applicability`, `Answer boundaries` and `Unverified outcomes` for shared context. A useful unknown sentence is “Actual production behavior has not been verified.” Use `Q:` for questions.
- Business text must use reader-facing language. Do not include source paths, internal IDs, review records, source links or these authoring instructions. Engineering text reuses the exact business files and adds technical evidence. Do not promise production behavior or business policy based only on code.
- Default `full` and optional `compact` retain the same evidence and review obligations. For compact layout use the existing engineering configuration, not a separate English schema. Optional business-intent extensions retain their fixed protocol headings; do not claim every internal display is localized.

## Check and prepare

1. Record normal, failure, unknown and authorization-boundary question cases. Explain whether results came from static comparison or real execution; never claim bot testing when none happened. Fixed category tokens remain `正常`, `失败`, `未知`, `越权`, and the fixed passed value is `通过`.
2. Run `check` and inspect `impact`. Actually review affected claims and files before `confirm-claims`; that command records digests, not semantic truth.
3. Run `prepare`, providing English business and engineering topics, unknowns and keywords, or inspect the suggestions from `--auto-retrieval-metadata`. Refreshing a candidate removes old review stamps. A changed language, text or evidence needs renewed review.

## Review and publish

- After `prepare`, use human approval only after an actual reviewer has explicitly approved the named package and its boundaries; record that reviewer, date and exact approval note with `approve`.
- Alternatively use an existing, committed preauthorization policy and matching review record with `policy-review`. A model's name is not a substitute for a human reviewer. Missing, expired, out-of-scope or gated policy records leave the package in draft. Never lower a high-impact risk classification to bypass a gate.
- If independent verification is required, export `evidence-pack`, give it to the separate verifier, calibrate as required and bind the returned report to the candidate. Do not expose the calibration answer key. The tool validates identities, coverage and digests, not natural-language truth.
- Obtain the actual task's release authorization, commit the inputs, publish under a new release ID and run `audit-release`. Do not rewrite frozen releases. Language changes are new reviewed content, never post-approval translation.
- For the optional retrieval extension, build from the audited base release, run its fixed question suite and audit. Failure must not produce a current retrieval pointer. Business retrieval must not return engineering units. `retrieval-query` and the FTS5 probe return evidence, not final bot answers.

Use [the English guide](../../../docs/usage.en.md) for commands and [the Chinese release reference](../references/发布与维护.md) for additional parameters. If a diagnostic is Chinese, explain it in the user's interaction language without changing its meaning or disabling its check.

## Optional batch review

- Before handoff, run `preflight --module-id <id>`. It reuses prepare's candidate structure checks for the target module, without reading other unfinished module bodies or writing project state. It still needs a valid configuration, inventory and pinned sources. Inspect `checks`, `not_checked` and FAQ `navigation_preview`. Question results, semantic review, cross-module targets, global gates, retrieval metadata/recall and approval are not certified. `--files` follows prepare's selection rules; prepare always revalidates.
- Freeze a module before a separate, non-author reviewer reads its source and prose. Parallel work requires user authorization and host support. Keep one writer per module and a controller for shared files. Sequential work remains supported; a different session alone does not authenticate an independent identity.
- Stop formal writes before the batch check. Run one global `impact`, retain its complete original output, and dispatch actual entries by `module_id`. Early reviewers then check consumers and changed inputs. Do not run check merely to count that same queue.
- Review changes and consumers, then run `confirm-claims` and `prepare` separately per module. After all writes finish, run global `check`: success with explicit `pending_claim_impacts == 0` replaces repeated final empty module impacts. A nonzero count requires the actual global queue; failure or an absent field is never zero. Approval and release gates remain unchanged.
- Bind the result to tool version/commit, command, zoned start/end times, exit code, raw output and the complete read-input set with byte hashes: configuration, inventory, prose, specifications, relations, evidence and manifests, including added/deleted/untracked formal files. Record pinned source revisions and relevant nonsecret resolved environment values; never credentials. Git HEAD alone is insufficient. Check input hashes before and after, with no other formal writer; the project lock cannot constrain an external editor.
- Input changes or expiration invalidate old results. Confirmation/preparation writes also require a fresh final check. This is an operator procedure, not a new automatic cache/freeze system. Changes to shared facts or baselines require consumer review; unclear dependencies or global changes require a global check. A module-filtered impact still performs common project validation. Deletion requires checking old answers and dependencies, not just the surviving rows.
- Keep one existing checkpoint with task, frozen-input digests, findings, source/report pointers and next action. Retain one original queue and frozen draft, record revision differences, and keep author/reviewer/confirmation judgments separate. Re-read relevant rules and evidence after a stage change or context recovery; restore from files and verify current state, not chat summaries. Do not require a third full reread without new concerns.
- Inventory handoff preserves named destinations, uncovered differences, reasoned exclusions and evidence for exceptions; identical supporting material can reference its fixed original. Coverage bookkeeping is not semantic evidence.
- Before approval, inspect question headings, keyword suggestions and fixed audience-specific cases. Automated retrieval evaluation uses an audited base release; after authorization, `publish --with-retrieval --retrieval-suite <suite>` evaluates in staging before installation. Standalone retrieval build/evaluate writes outputs and is not a read-only draft check. Preserve first failures and retests, include held-out wording, and inspect unrelated queries separately: retrieval does not certify answerability, final answers or access control.
