# Code2KB — turn source code into evidence-backed knowledge

Use this skill when the user wants to extract business and engineering
knowledge from a source repository into a maintainable, searchable knowledge
base — feature descriptions, flows, rules, limits, and Q&A that a bot can
retrieve — or when they ask to audit, review, or publish an existing Code2KB
knowledge project.

This plugin bundles Code2KB Agent Toolkit. Use Git and Python 3.9+ with the
bundled copy.

## Bundled toolkit root

```
__TOOLKIT_DIR__
```

Key paths inside it:

- `skills/extract-app-knowledge/SKILL.md` — the Code2KB task router (start here)
- `skills/extract-app-knowledge/contracts/` — the executable workflows
  (`chinese-workflow.md`, `english-workflow.md`, `core.md`, ...)
- `skills/extract-app-knowledge/references/` — workflow reference material
- `skills/extract-app-knowledge/extensions/` — optional extensions
- `templates/` — knowledge project templates (e.g. `知识库配置.example.json`)
- `spec/` — knowledge file format specifications
- `docs/` — usage guides (`usage.md`, `usage.en.md`) and contracts
- `validation/` — the bundled Python CLI implementation

## Workflow

1. **Route first.** Read `skills/extract-app-knowledge/SKILL.md` from the
   bundled root. It selects exactly one workflow by the conversation language:
   the Chinese workflow (`contracts/chinese-workflow.md`) or the English
   workflow (`contracts/english-workflow.md`). Follow that one workflow; do not
   merge both.
2. **Set up the knowledge project.** Follow the workflow to create the
   knowledge project (separate from the source repo), copy the config template
   from `templates/`, and pin each source repository to an exact commit
   (`git rev-parse HEAD`). Prefer a small, well-defined module for the first
   extraction.
3. **Extract, then check.** After the AI writes the knowledge files, run the
   bundled CLI (see below) — `check` first, then follow the workflow's review
   path (`impact → confirm-claims → prepare`, then human `approve` or
   `policy-review`).
4. **Publish is separate from approval.** `check` passing does not mean the
   content is approved or that natural-language conclusions are correct. Only
   publish after the review the workflow requires and after confirming the
   user's authorization for this run.

## Bundled CLI

Run the bundled `validation/knowledge.py` with Python 3.9+ (macOS/Linux:
`python3`; Windows: `python`). Pass its absolute path, the action, and
`--project-root` followed by the knowledge project path as separate arguments.
When using a shell, quote the paths for that shell. Commands that write project
files require a platform with `fcntl` file locking.

Actions include: `check`, `preflight`, `impact`, `confirm-claims`, `prepare`,
`approve`, `policy-review`, `publish`, `audit-release`, `analyze-candidates`,
`evidence-snapshot`, `render-facts`, `preview-upgrade`, `relation-audit`,
`retrieval-build`, `retrieval-evaluate`, `evidence-pack`,
`verifier-calibrate`, and run management actions. Pass `--help` to the
bundled CLI for details.

## Guardrails

- Never turn code inference into claims about verified runtime behavior; the
  workflow keeps applicability conditions, failures, and unknowns explicit.
- Protocol filenames, fixed headers, enums, IDs, and JSON keys stay literal —
  they are not prose to translate.
- Knowledge content language follows the project's `content_language`
  (`zh-CN` by default, or `en`), independent of the conversation language.
- Do not publish, push, or wire up a bot without the user's authorization for
  this run.
