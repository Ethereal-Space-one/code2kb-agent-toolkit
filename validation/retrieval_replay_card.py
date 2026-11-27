"""Make one read-only replay card from an audited context diagnosis."""

from __future__ import annotations

from html import escape
import re

try:
    from .retrieval_model import RetrievalError, digest, json_bytes
    from .retrieval_query import source_locations
except ImportError:  # direct CLI invocation
    from retrieval_model import RetrievalError, digest, json_bytes
    from retrieval_query import source_locations


def build(project, case_id, suite, results, contexts, report, units, base, manifest, manifest_sha256, core,
          *, include_excerpts=False):
    """Render the selected case; callers must first audit and diagnose all inputs."""
    row = next((item for item in report["cases"] if item["case_id"] == case_id), None)
    if row is None:
        raise RetrievalError("复盘卡题目 ID 不在题集中 / Replay card case ID is not in the suite")
    excerpts_by_unit = {}
    for excerpt in contexts[case_id]:
        excerpts_by_unit.setdefault(excerpt["unit_id"], []).append(excerpt["text"])
    cache = {}
    evidence = []
    for rank, unit_id in enumerate(row["retrieved_unit_ids"], start=1):
        unit = units[unit_id]
        audience = unit["meta"]["audience"]
        view = "业务版" if audience == "business" else "研发版"
        recorded = excerpts_by_unit.get(unit_id, [])
        evidence.append({
            "rank": rank, "unit_id": unit_id, "topic": unit["meta"]["topic"], "audience": audience,
            "recorded_excerpt_count": len(recorded),
            "recorded_context": ("no_excerpt_recorded" if not recorded else
                                 "full_unit_as_one_excerpt" if unit["body"] in recorded else
                                 "excerpts_only"),
            "source_locations": source_locations(project, view, unit, base["views"][audience]["files"], cache, core),
        })
    case = next(item for item in suite["cases"] if item["case_id"] == case_id)
    missing, lost = row["missing_at_retrieval"], row["lost_during_assembly"]

    def annotate(gaps):
        output = {key: gaps[key] for key in ("module_ids", "unit_ids")}
        for key, marker in [("required_phrases", "required"), ("required_unknown_phrases", "unknown")]:
            absent = set(gaps[key])
            records = []
            for number, phrase in enumerate(case[key], start=1):
                if phrase not in absent:
                    continue
                record = {"marker_id": f"{marker}-{number}", "position": number, "sha256": digest(phrase.encode("utf-8"))}
                if include_excerpts:
                    record["text"] = phrase
                records.append(record)
            output[key] = records
        return output

    evaluated = manifest["evaluation"]
    recorded_excerpts = []
    for excerpt in contexts[case_id]:
        text = excerpt["text"]
        record = {"unit_id": excerpt["unit_id"], "code_points": len(text), "sha256": digest(text.encode("utf-8"))}
        if include_excerpts:
            record["text"] = text
        recorded_excerpts.append(record)
    return {
        "schema_version": "0.1",
        "kind": "retrieval-replay-card",
        "case_id": case_id,
        "identity": {
            "release_id": report["release_id"],
            "validator_version": core.IMPLEMENTATION_VERSION,
            "knowledge_document_commit": base["document_commit"],
            "base_registry_sha256": manifest["base_registry_sha256"],
            "retrieval_manifest_sha256": manifest_sha256,
            "corpus_sha256": report["corpus_sha256"],
            "suite_id": report["suite_id"],
            "audience": report["audience"],
            "retriever_id": report["retriever_id"],
            "normalized_input_sha256": {name: digest(json_bytes(value)) for name, value in [
                ("suite", suite), ("results", results), ("contexts", contexts),
            ]},
        },
        "validation": {
            "snapshot_audit": "passed",
            "saved_retrieval_gate_status": manifest["gate_status"],
            "saved_retrieval_gate_suite_id": evaluated["suite_id"] if evaluated is not None else None,
            "recorded_context_check": "matches_retrieved_text",
            "evidence_status": "gaps_found" if any(missing.values()) or any(lost.values()) else "no_annotated_gaps",
            "answer_review_status": "not_assessed",
        },
        "retrieved": evidence,
        "counts": {"retrieved_units": len(evidence), "recorded_context_units": len(excerpts_by_unit),
                   "recorded_excerpts": len(contexts[case_id])},
        "recorded_excerpts": recorded_excerpts,
        "missing_at_retrieval": annotate(missing),
        "lost_during_assembly": annotate(lost),
    }


def _inline(value: str) -> str:
    """Keep input labels literal even when exported Markdown is later rendered."""
    text = " ".join(value.split())
    return re.sub(r"([\\`*_{}\[\]()#!|~])", r"\\\1", escape(text, quote=False))


def _literal(text: str) -> list[str]:
    # A fence longer than all backtick runs keeps Markdown in the excerpt literal.
    fence = "`" * max(3, 1 + max((len(run) for run in re.findall(r"`+", text)), default=0))
    return [fence, text, fence, ""]


def markdown(card: dict, language: str) -> str:
    cn = language == "zh-CN"
    def say(zh, en):
        return zh if cn else en

    identity, validation = card["identity"], card["validation"]
    gate = validation["saved_retrieval_gate_status"]
    gate_suite = validation["saved_retrieval_gate_suite_id"]
    gate_label = {
        "passed": say("通过", "passed"), "failed": say("未通过", "failed"),
        "unevaluated": say("未评测", "unevaluated"),
    }[gate]
    if gate_suite is not None:
        gate_label += say("；已保存的评测题集：", "; saved evaluation suite: ") + _inline(gate_suite)
    counts = card["counts"]
    recording_labels = {
        "no_excerpt_recorded": say("上下文记录未包含", "not in recorded context"),
        "full_unit_as_one_excerpt": say("上下文记录有整段原文", "full unit recorded"),
        "excerpts_only": say("有片段记录；没有单个完整单元", "excerpts recorded; none spans the full unit"),
    }
    lines = [
        "# " + say("证据复盘卡", "Evidence replay card") + " · " + _inline(card["case_id"]), "",
        say("**快照及出处审计：通过**", "**Snapshot and source audit: passed**") + "  ",
        say("**已保存的检索门禁：** ", "**Saved retrieval gate:** ") + gate_label + "  ",
        say("**证据覆盖：** ", "**Evidence coverage:** ") + (
            say("发现缺口", "gaps found") if validation["evidence_status"] == "gaps_found"
            else say("未发现已标注的缺口", "no annotated gaps")) + "  ",
        say("**最终答复：未评判，需单独复核。**", "**Final answer: not assessed; review it separately.**"), "",
        "## " + say("检索找到了什么", "What retrieval found"), "",
        say("检索单元 {found} 个；上下文记录包含 {included} 个单元、{excerpts} 个片段。",
            "Retrieved units: {found} · Units in recorded context: {included} · Excerpts: {excerpts}")
        .format(found=counts["retrieved_units"], included=counts["recorded_context_units"],
                excerpts=counts["recorded_excerpts"]), "",
    ]
    for hit in card["retrieved"]:
        sources = " · ".join("[" + say("出处 ", "source ") + str(number) + "](" + item["href"] + ")"
                             for number, item in enumerate(hit["source_locations"], start=1))
        lines.append(f"{hit['rank']}. **{_inline(hit['topic'])}** · {_inline(hit['unit_id'])} · "
                     + recording_labels[hit["recorded_context"]] + (f" · {sources}" if sources else ""))
    if not card["retrieved"]:
        lines.append(say("这题没有召回单元。", "No units were retrieved for this question."))
    lines.extend(["", "## " + say("上下文片段指纹", "Recorded excerpt fingerprints"), ""])
    for number, excerpt in enumerate(card["recorded_excerpts"], start=1):
        lines.extend([f"{number}. {_inline(excerpt['unit_id'])} · {excerpt['code_points']} "
                      + say("字符", "code points") + f" · SHA-256: `{excerpt['sha256']}`", ""])
        if "text" in excerpt:
            lines.extend(_literal(excerpt["text"]))
    if not card["recorded_excerpts"]:
        lines.extend([say("本题的上下文记录没有片段。", "No excerpts appear in the recorded context for this question."), ""])
    elif "text" not in card["recorded_excerpts"][0]:
        lines.extend([say("默认不输出片段或标注原文。需要在本地核对时用 `--include-excerpts`。",
                          "Excerpt and annotation text are omitted by default. Use `--include-excerpts` for local inspection."), ""])
    labels = {
        "module_ids": say("模块", "Modules"),
        "unit_ids": say("单元", "Units"),
        "required_phrases": say("必要原文", "Required phrases"),
        "required_unknown_phrases": say("必须保留的未知边界", "Required unknowns"),
    }
    for field, title in [("missing_at_retrieval", say("检索时就缺少", "Missing from retrieval")),
                         ("lost_during_assembly", say("已找到但上下文记录中缺失", "Found but absent from recorded context"))]:
        gaps = card[field]
        lines.extend(["", "## " + title, ""])
        for key, label in labels.items():
            if key in {"module_ids", "unit_ids"}:
                if gaps[key]:
                    lines.append("- " + label + ": " + "；".join(_inline(value) for value in gaps[key]))
                continue
            for marker in gaps[key]:
                text = ": " + _inline(marker["text"]) if "text" in marker else ""
                lines.append(f"- {label} #{marker['position']}{text} · SHA-256: `{marker['sha256']}`")
        if not any(gaps.values()):
            lines.append(say("没有已标注的缺口。", "No annotated gaps."))
    lines.extend(["", "## " + say("核验身份", "Verification identity"), ""])
    for key, label in [
        ("release_id", say("发布 ID", "Release ID")),
        ("validator_version", say("核验工具版本", "Validator version")),
        ("knowledge_document_commit", say("知识文档提交（不是业务源码提交）", "Knowledge-document commit (not source-code commit)")),
        ("audience", say("受众", "Audience")), ("suite_id", say("题集", "Suite")),
        ("retriever_id", say("检索器标识", "Retriever")),
        ("base_registry_sha256", say("基础清单 SHA-256", "Base registry SHA-256")),
        ("retrieval_manifest_sha256", say("检索清单 SHA-256", "Retrieval manifest SHA-256")),
        ("corpus_sha256", say("语料 SHA-256", "Corpus SHA-256")),
    ]:
        lines.append("- " + label + ": " + _inline(identity[key]))
    for key, value in identity["normalized_input_sha256"].items():
        lines.append("- " + say("规范化 JSON", "Normalized JSON") + f" {key} SHA-256: {value}")
    lines.extend(["", say(
        "这是本地诊断记录，不是脱敏报告。出处链接相对于知识项目根目录；分享前仍须检查标题、路径、标识及选出的原文。",
        "This is a local diagnostic, not a redacted report. Source links are relative to the knowledge project root; check titles, paths, identifiers and any opted-in text before sharing.",
    ), "", say(
        "通过校验只表示记录的片段逐字匹配该版检索原文；不证明模型真的收到了它，也不证明答复正确、覆盖完整或线上行为。",
        "Validation confirms the recorded excerpts match this release’s retrieved text. It does not prove the model received them, the answer was correct, all evidence was covered, or production behavior.",
    ), ""])
    return "\n".join(lines)
