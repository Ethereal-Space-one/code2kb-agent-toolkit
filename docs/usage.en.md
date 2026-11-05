# Code2KB Agent Toolkit usage guide

[简体中文](usage.md) · **English**

**For knowledge maintainers.** Give the [Skill entry](../skills/extract-app-knowledge/SKILL.md) to your AI coding agent; this guide explains your setup and decisions. Neither document belongs in a bot's knowledge corpus.

> Applies to the unreleased `2.0.0` toolkit. The command remains `code2kb`. Audit old-brand releases using the version that generated them; see the [rename notes](agent-toolkit-rebrand-plan.md).

## What English support covers

Use English instructions and generate English business knowledge, engineering explanations, navigation and retrieval text. One project has one output language; conversation language and source programming language are independent.

Protocol filenames, fixed internal tables, enums and IDs remain literal, often Chinese. Your agent fills them using the shared templates; you do not need to translate them. Some CLI diagnostics and detailed reference documents remain Chinese. This is not full terminal localization or an automatic translation of an existing knowledge base.

## 1. Install and configure a project

Requires Git, Python 3.9+ and your own AI coding agent with access to local repositories. Mutating commands need `fcntl` on platforms such as Linux/macOS.

```bash
git clone https://github.com/Ethereal-Space-one/code2kb-agent-toolkit.git code2kb-agent-toolkit
cd code2kb-agent-toolkit
python3 -m pip install -e .
git init /path/to/knowledge-project
cp templates/知识库配置.example.json /path/to/knowledge-project/知识库配置.json
git -C /path/to/source-repo rev-parse HEAD
```

Keep the knowledge project separate from your source. Edit `知识库配置.json`: set `content_language` to `en`, remove unused example repositories, and replace each `path` and `commit` with your actual absolute path and pinned SHA. Also write `boundary_notes` in English or remove these optional example notes.

Minimal configuration, with placeholders to replace:

```json
{
  "standard_version": "c2kb-file/1",
  "knowledge_source_root": "知识源",
  "content_language": "en",
  "repositories": {
    "source": {"path": "/absolute/path/to/source", "commit": "REPLACE_WITH_FIXED_SHA"}
  }
}
```

Absent `content_language` means `zh-CN`. Supported values are exactly `zh-CN` and `en`. This capability needs a CLI that supports the new metadata; older tools may reject it.

## 2. Start the agent

Copy this task and replace the paths:

```text
Read <toolkit-root>/skills/extract-app-knowledge/SKILL.md and select its English AI workflow.
Use English for interaction. Build knowledge in /path/to/knowledge-project with content_language=en.
Read the configured pinned source revisions. First plan the scope, modules, entry inventory and gaps, then gather evidence and write each module.
Preserve conditions, failure branches and unknowns. Fixed protocol filenames, table labels and IDs must not be translated.
Complete the checks and prepare review candidates. Do not publish, push or connect a bot without authorization for that action.
```

The agent investigates repositories and system roles, builds the inventory, follows the actual business paths and writes knowledge. You supply scope and business context that cannot be established from code. Do not provide credentials merely to make an unknown disappear.

An English knowledge file still uses the fixed filename `常见问答.md` (FAQ):

```markdown
---
module_id: example.order.lookup
document_type: faq
review_status: draft
applicability: current
content_language: en
---

# Order lookup

## Q: Can I look up every order?

Only signed-in users can look up orders in their assigned regions. Actual region assignments and production behavior have not been verified.
```

Internal specifications and API tables retain their literal labels. Business text does not include internal IDs, source paths or review instructions. Do not publish these instructions as product knowledge.

## 3. Check and prepare a candidate

After the agent has authored and actually reviewed the content:

```bash
code2kb check --project-root /path/to/knowledge-project
code2kb impact --project-root /path/to/knowledge-project --module-id example.order.lookup
code2kb confirm-claims --project-root /path/to/knowledge-project --module-id example.order.lookup
code2kb prepare --project-root /path/to/knowledge-project \
  --module-id example.order.lookup --auto-retrieval-metadata
```

Inspect suggested topics, keywords and unknowns in the candidate. `impact` must be resolved through real review before `confirm-claims`. A passing structural check is not an approval or proof of semantic accuracy.

To revise text, evidence or language, update the knowledge source, review the impacts and use `prepare --refresh`. Existing approval cannot be reused after the candidate changes. Changing configuration does not translate files or certify their language.

## 4. Choose a review path, then release

- **Human review:** after the actual reviewer has read and approved the named package and its boundaries, record their identity, actual date and exact authorization with `approve --reviewed-by ... --reviewed-at ... --approval-note ...`.
- **Preauthorized policy:** use `policy-review --evidence-file ... --executed-by ...` only with a valid committed policy and matching review record. A failed gate leaves the package in draft. An AI self-check alone is not authorization.

Optional independent verification exports source-and-claim items with `evidence-pack --kind claim_entailment`; `qa_replay` and `leak_probe` are also available. The project owner runs the verifier and supplies its report, with calibration if policy requires it. Ask the agent to follow the [English workflow](../skills/extract-app-knowledge/contracts/english-workflow.md#review-and-publish); the tool does not call a verification model or authenticate a person.

After the chosen review, commit the project inputs and authorize publication:

```bash
git -C /path/to/knowledge-project add <reviewed-input-paths>
git -C /path/to/knowledge-project commit -m "Record reviewed knowledge inputs"
code2kb publish --project-root /path/to/knowledge-project --release-id my-kb-v1
code2kb audit-release --project-root /path/to/knowledge-project
```

`<reviewed-input-paths>` is a placeholder for the files you inspected, not a literal path. Do not stage unrelated or private files. These example commands do not authorize publishing any particular project.

## 5. Retrieve evidence and connect your bot

The base release contains business and engineering views, navigation, a version manifest and a current pointer. Shared business files are identical in both views. Fixed output paths remain unchanged; their visible navigation labels are English.

For the optional audited retrieval extension:

```bash
code2kb retrieval-build --project-root /path/to/knowledge-project --release-id my-kb-v1
code2kb retrieval-evaluate --project-root /path/to/knowledge-project \
  --release-id my-kb-v1 --suite /path/to/english-questions.json
code2kb retrieval-audit --project-root /path/to/knowledge-project --release-id my-kb-v1
code2kb retrieval-query --project-root /path/to/knowledge-project \
  --query "Can I look up any order?" --audience business --top-k 3
```

Have the agent create the question suite using the existing [retrieval contract](retrieval-contract.md), with expected modules, required conditions/unknowns and forbidden disclosures. A failed evaluation leaves retrieval unready. The [self-authored English case](../conformance/english/README.en.md) checks actual SQLite FTS5 evidence retrieval; it does not prove final bot-answer quality.

Import only released business knowledge into a business bot. Your external FTS/vector system retrieves text and your model composes the answer. Keep engineering content, internal specifications, this guide and agent instructions out of that corpus. Code2KB does not deploy your bot or index service.

## Literal protocol tokens

These meanings help you read the output; **do not rename the tokens**:

| Literal token | Meaning |
| --- | --- |
| `知识库配置.json` | Project configuration |
| `知识源/功能大纲.md` | Functional inventory |
| `结构化规格.md` | Internal evidence specification |
| `发布清单.md` | Internal review candidate |
| `模块概览.md` / `常见问答.md` | Overview / FAQ |
| `技术实现.md` | Engineering implementation |
| `发布/业务版` / `发布/研发版` | Business / engineering release views |
| `正常` / `失败` / `未知` / `越权` | Normal / failure / unknown / authorization-boundary test categories |
| `通过` | Passed; the record must say what was actually checked |

The shared [specification](../SPEC.md) remains authoritative. A language declaration and lexical rules cannot certify translation quality, source entailment, business authorization or actual production behavior.
