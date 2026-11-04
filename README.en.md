# Code2KB Spec

[简体中文](README.md) · **English**

**Use AI to turn code into business knowledge your bot can answer from.**

Code2KB Spec combines an Agent Skill, an open knowledge specification, and a Python CLI into a reviewable knowledge-production workflow. Your coding agent reads source code and extracts business and implementation logic; `code2kb` checks evidence bindings, review records, and release artifacts.

**1.2.0 follow-up**: general full-stack inventory, cross-language evidence guidance, explicit scanning of nonstandard source directories, and clearer reference diagnostics. [See the supplement](CHANGELOG.md).

[Quick start](#quick-start) · [Outputs](#outputs) · [Independent verification](#independent-verification-12) · [Documentation](#documentation)

![Code2KB 1.2: pinned source becomes knowledge files through AI authoring, review, and release, then feeds external FTS or vector retrieval and bot Q&A](assets/readme/overview.en.svg)

## Outputs

| Output | Consumer and contents |
| --- | --- |
| **Knowledge source** | For maintainers: functional inventory, structured facts, business and engineering drafts, and unresolved questions |
| **Business and engineering views** | Business content covers features, workflows, rules, and Q&A. Engineering content adds implementation, APIs, methods, and source anchors. A manifest and pointer identify the version |
| **Optional retrieval view** | For external indexes: topic units derived from reviewed text, preserving conditions, exceptions, unknowns, and sources, with separate evaluation and audit records |

A business bot can use **FTS or vector retrieval → source text → model-composed answers**. The project's audited import path is the [retrieval extension](docs/retrieval-contract.md). Business bots ingest only business units; internal specifications and process files stay out of the corpus. Consumers who split the base business view themselves handle chunk boundaries, audience isolation, version switching, and evaluation.

The [public PetClinic case](conformance/public-source/petclinic/README.md) records a fixed-source-to-knowledge exercise with [SQLite FTS5 retrieval](conformance/public-source/petclinic/fts5-run.json). It tests evidence location, not final bot answers. `retrieval-query` also returns candidate evidence only.

## Quick start

Requires **Git, Python 3.9+**, and a coding agent that can read local repositories. Mutating CLI commands require `fcntl` file locking, available on platforms such as Linux and macOS; read-only checks remain available without that module.

### 1. Install and pin source revisions

```bash
git clone https://github.com/Ethereal-Space-one/code2kb-spec.git
cd code2kb-spec
python3 -m pip install -e .
git init /path/to/knowledge-project
cp templates/知识库配置.example.json /path/to/knowledge-project/知识库配置.json
git -C /path/to/source-repo rev-parse HEAD
```

Keep the knowledge project separate from source repositories. Edit `知识库配置.json`: remove unused example repositories and set each `repositories` entry's `path` to an absolute local path and `commit` to a pinned SHA.

### 2. Have an agent extract knowledge

Give your coding agent this task:

```text
Read <code2kb-spec-root>/skills/extract-app-knowledge/SKILL.md.
Build a source-backed business knowledge base in /path/to/knowledge-project.
Verify pinned commits and create the full functional inventory, then gather evidence, write, and review each module.
Preserve conditions and unknowns; do not present source inference as production behavior.
Follow the project's chosen review process and verify authorization before release.
```

The Skill loads evidence, writing, and review instructions by stage. Consumers supply the agent's model and execution environment.

### 3. Check, review, and release

```bash
code2kb check --project-root /path/to/knowledge-project
```

Complete `impact`, `confirm-claims`, and `prepare` per module, then choose a review path:

| Path | Conditions and entry point |
| --- | --- |
| **Human review** | After the actual reviewer explicitly approves the candidate and its boundaries, record the decision with `approve` |
| **Preauthorized policy review** | With a valid policy and review record for this candidate, run `policy-review`; packages outside policy or caught by a manual gate stay in draft |

Passing `check` or agent self-review does not approve a package. After approval, publish and audit:

```bash
code2kb publish --project-root /path/to/knowledge-project --release-id my-kb-v1
code2kb audit-release --project-root /path/to/knowledge-project
```

See the [usage guide](docs/usage.md) for full arguments, review records, and release steps.

<details>
<summary>Want to explore the file structure first? Run the bundled demo</summary>

```bash
python3 -B examples/create_demo.py
```

The script creates a small source repository and knowledge project in a temporary directory, runs `check`, and prints the path. It demonstrates files and checks; it does not call a model or generate a complete knowledge base.

</details>

## Independent verification (1.2)

An optional independent verifier checks whether cited source supports a claim. Depending on the verification type, it can also replay Q&A cases or inspect disclosure boundaries in business files. `evidence-pack` exports the expected items; consumers run the verifier and return its report. `code2kb` checks the candidate binding, coverage, digests, and declared identities.

![Optional 1.2 workflow: prepare a candidate, export evidence, run external calibration and verification, then check the report against policy; failed verification stays in draft](assets/readme/independent-review.en.svg)

Policy `1.1` can require calibration on injected faults using `verifier-calibrate`. Calibration scores do not establish accuracy on real projects. A failed verification leaves the module in draft; human review remains a separate option. See the [independent verifier workflow](docs/usage.md#可选独立验证者12).

## Extensions and maintenance

- **[Full-stack and cross-language evidence](skills/extract-app-knowledge/references/全栈范围盘点.md)**: inventory repositories, build units, and actual roles; investigate cross-layer calls, async work, native components, and configuration overrides by scenario. [Self-authored public cases](conformance/full-stack/README.md) check preservation of conditions and unknowns in knowledge artifacts.
- **[Resumable tasks](docs/0.6.0-runner.md)**: local task ledgers, checkpoints, and recovery, with [Claude Code](hosts/claude-code/README.md) / [Codex](hosts/codex/README.md) task instructions.
- **[Source-upgrade review](docs/1.0.0-public-contract.md)**: compare pinned revisions and produce a read-only plan of knowledge to review and remaining gaps.
- **[Source adapters](docs/adapter-contract.md)**: discover entry-point and relationship candidates for review; languages without a dedicated analyzer fall back to L1 file-level discovery.

<details>
<summary>Scan a nonstandard directory containing your own source</summary>

Replace `source_a` with a repository ID from your project configuration:

```bash
code2kb analyze-candidates --project-root /path/to/knowledge-project \
  --repository-id source_a --candidate-schema 0.2 \
  --adapter universal-l1 --scope vendor/internal
```

An explicit scope is no longer skipped because of an ancestor named `vendor`; nested dependency and generated directories remain filtered. Regular UTF-8 text with an unknown extension can enter L1 inventory. Candidates are not verified business facts. See the [adapter contract](docs/adapter-contract.md).

</details>

<details>
<summary>View source inventory, evidence, and two-view structure (3 diagrams)</summary>

Code, filenames, and fact IDs are illustrative. These detail diagrams use Chinese labels with English subtitles.

![Inventory source entries and adapter candidates; candidates require review](assets/readme/source-adapters.svg)

![Pinned source anchors and structured facts; production behavior needs separate evidence](assets/readme/evidence.svg)

![Shared business content, with additional implementation evidence in the engineering view](assets/readme/two-views.svg)

</details>

<details>
<summary>View optional retrieval and source-upgrade review (2 diagrams)</summary>

![Build topic units from reviewed knowledge for evaluated and audited retrieval](assets/readme/retrieval.svg)

![Compare pinned revisions to produce a read-only upgrade review plan](assets/readme/upgrade-review.svg)

</details>

## Documentation

[Usage guide](docs/usage.md) · [Knowledge-file specification](SPEC.md) · [Retrieval contract](docs/retrieval-contract.md) · [Assurance boundaries](docs/assurance-matrix.md) · [Versioning](docs/versioning.md)

Source code alone cannot prove production behavior, business policy, or authorization outcomes; unknowns remain explicit without evidence. Consumers provide model execution, production FTS/vector services, and bot deployment.

Current project version: `1.2.0`. New projects default to `c2kb-file/1`; existing `0.8.3` projects remain supported. See the [changelog](CHANGELOG.md) and [roadmap](ROADMAP.md). The normative specification is in Simplified Chinese.

The full-stack update is a post-release supplement on `main`; the `v1.2.0` tag remains the original release snapshot.

[Report an issue](https://github.com/Ethereal-Space-one/code2kb-spec/issues) · [Contribute](CONTRIBUTING.md) · [Apache License 2.0](LICENSE)
