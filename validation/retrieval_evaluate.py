"""Offline lexical baseline and strict retrieval-result evaluator."""

from __future__ import annotations

from collections import Counter
import math
from pathlib import Path
import re

try:
    from . import content_language
    from .retrieval_model import RetrievalError, digest, json_bytes, read_unit, strict_json
except ImportError:
    import content_language
    from retrieval_model import RetrievalError, digest, json_bytes, read_unit, strict_json


def tokens(text: str) -> Counter:
    result = Counter()
    normalized = text.casefold()
    for word in re.findall(r"[a-z0-9_.-]+", normalized):
        result[word] += 1
    for chunk in re.findall(r"[\u3400-\u9fff]+", normalized):
        for index, char in enumerate(chunk):
            result[char] += 1
            if index + 1 < len(chunk):
                result[chunk[index:index + 2]] += 1
    return result


def lexical(query: str, units: list[dict], top_k: int) -> list[str]:
    query_tokens = tokens(query)
    scored = []
    for item in units:
        meta, body = item["meta"], item["body"]
        fields = (
            (meta["module_id"], 6.0), (meta["topic"], 5.0),
            (meta["question_variants"], 4.0), (body, 1.0),
        )
        score = 0.0
        for value, weight in fields:
            corpus = tokens(value)
            score += weight * sum(min(count, corpus[token]) / math.sqrt(1 + corpus[token]) for token, count in query_tokens.items() if token in corpus)
        if score > 0:
            scored.append((-score, meta["unit_id"]))
    scored.sort()
    return [unit_id for _, unit_id in scored[:top_k]]


def load_suite(path: Path) -> dict:
    suite = strict_json(path)
    if set(suite) != {"schema_version", "suite_id", "audience", "cases"} or suite["schema_version"] != "0.1" or suite["audience"] not in {"business", "engineering"} or not isinstance(suite["suite_id"], str) or not suite["suite_id"] or not isinstance(suite["cases"], list) or not suite["cases"]:
        raise RetrievalError("检索评测问题集结构无效")
    ids = set()
    required = {"case_id", "query", "expected_module_ids", "expected_unit_ids", "required_phrases", "required_unknown_phrases", "forbidden_phrases", "top_k"}
    for case in suite["cases"]:
        if not isinstance(case, dict) or set(case) != required or not isinstance(case["case_id"], str) or not case["case_id"] or case["case_id"] in ids or not isinstance(case["query"], str) or not case["query"] or type(case["top_k"]) is not int or not 1 <= case["top_k"] <= 20:
            raise RetrievalError("检索评测用例结构无效或 ID 重复")
        ids.add(case["case_id"])
        for field in required - {"case_id", "query", "top_k"}:
            if not isinstance(case[field], list) or any(not isinstance(value, str) or not value for value in case[field]) or len(case[field]) != len(set(case[field])):
                raise RetrievalError(f"检索评测用例 {field} 无效")
        if not case["expected_module_ids"] and not case["expected_unit_ids"]:
            raise RetrievalError("评测用例至少要指定预期模块或单元")
    return suite


def load_units(release_root: Path, manifest: dict) -> dict[str, dict]:
    units = {}
    for entry in manifest["units"]:
        path = release_root.parent / entry["path"]
        meta, body = read_unit(path)
        if meta["unit_id"] in units:
            raise RetrievalError("检索单元 ID 重复")
        if meta["release_id"] != manifest["release_id"] or meta["source_documents"].split(" | ") != entry["source_documents"]:
            raise RetrievalError("检索单元与发布身份或出处不一致")
        units[meta["unit_id"]] = {"entry": entry, "meta": meta, "body": body}
    return units


def evaluate_data(suite: dict, units: dict[str, dict], external: dict | None, corpus_sha256: str,
                  release_id: str | None = None, *, all_external_candidates: bool = False) -> dict:
    if not units:
        raise RetrievalError("检索语料为空")
    if external is not None:
        if set(external) != {"schema_version", "suite_id", "retriever_id", "corpus_sha256", "cases"} or external["schema_version"] != "0.1" or external["suite_id"] != suite["suite_id"] or external["corpus_sha256"] != corpus_sha256 or not isinstance(external["retriever_id"], str) or not external["retriever_id"] or not isinstance(external["cases"], dict):
            raise RetrievalError("外部检索结果身份或语料摘要不匹配")
        if set(external["cases"]) != {case["case_id"] for case in suite["cases"]}:
            raise RetrievalError("外部检索结果用例集合不匹配")
    retriever_id = external["retriever_id"] if external else "lexical-v1"
    expected_release = release_id or next(iter(units.values()))["meta"]["release_id"]
    corpus_identity_correct = all(unit["meta"]["release_id"] == expected_release and bool(unit["meta"]["source_documents"]) for unit in units.values())
    rows = []
    for case in suite["cases"]:
        audience = suite["audience"]
        allowed = [unit for unit in units.values() if audience == "engineering" or unit["meta"]["audience"] == "business"]
        if external:
            hits = external["cases"][case["case_id"]]
            if not isinstance(hits, list) or any(not isinstance(hit, dict) or set(hit) != {"unit_id", "score"} or not isinstance(hit["unit_id"], str) or type(hit["score"]) not in (int, float) or not math.isfinite(hit["score"]) for hit in hits):
                raise RetrievalError("外部检索结果格式无效")
            all_ids = [hit["unit_id"] for hit in hits]
            if len(all_ids) != len(set(all_ids)) or any(unit_id not in units for unit_id in all_ids):
                raise RetrievalError("外部检索结果包含重复或未知单元 ID")
            result_ids = all_ids if all_external_candidates else all_ids[:case["top_k"]]
        else:
            result_ids = lexical(case["query"], allowed, case["top_k"])
        selected = [units[unit_id] for unit_id in result_ids]
        expected_modules = set(case["expected_module_ids"])
        expected_units = set(case["expected_unit_ids"])
        relevant = [unit for unit in selected if unit["meta"]["unit_id"] in expected_units or unit["meta"]["module_id"] in expected_modules]
        text = "\n".join(unit["body"] for unit in relevant)
        all_text = "\n".join(unit["body"] for unit in selected)
        found_modules = {unit["meta"]["module_id"] for unit in selected}
        found_units = set(result_ids)
        missing_modules = sorted(expected_modules - found_modules)
        missing_units = sorted(expected_units - found_units)
        module_recall = (len(expected_modules) - len(missing_modules)) / len(expected_modules) if expected_modules else None
        unit_recall = (len(expected_units) - len(missing_units)) / len(expected_units) if expected_units else None
        module_rank = next((index for index, unit in enumerate(selected, 1)
                            if unit["meta"]["module_id"] in expected_modules), None)
        unit_rank = next((index for index, unit_id in enumerate(result_ids, 1)
                          if unit_id in expected_units), None)
        combined_rank = min((rank for rank in (module_rank, unit_rank) if rank is not None), default=None)
        required = [phrase for phrase in case["required_phrases"] if phrase not in text]
        unknown = [phrase for phrase in case["required_unknown_phrases"] if phrase not in text]
        forbidden = [phrase for phrase in case["forbidden_phrases"] if phrase in all_text]
        leakage = [unit_id for unit_id in result_ids if audience == "business" and units[unit_id]["meta"]["audience"] != "business"]
        hashes = [digest(re.sub(r"\s+", "", content_language.split_sources(unit["body"])[0]).encode("utf-8")) for unit in selected]
        duplicate_hits = len(hashes) - len(set(hashes))
        passed = (not missing_modules and not missing_units and not required and not unknown
                  and not forbidden and not leakage and duplicate_hits == 0 and corpus_identity_correct)
        rows.append({
            "case_id": case["case_id"], "query": case["query"], "hits": result_ids,
            "module_recall_at_k": module_recall, "unit_recall_at_k": unit_recall,
            "module_rank": module_rank, "unit_rank": unit_rank,
            "reciprocal_rank": 1 / combined_rank if combined_rank else 0.0,
            "missing_module_ids": missing_modules, "missing_unit_ids": missing_units,
            "missing_required_phrases": required, "missing_unknown_phrases": unknown,
            "forbidden_phrase_hits": forbidden, "audience_leakage": leakage,
            "duplicate_hits": duplicate_hits, "passed": passed,
            "source_release_correct": corpus_identity_correct,
        })
    target_summary = {}
    for kind in ("module", "unit"):
        recall_key = f"{kind}_recall_at_k"
        measured = [row for row in rows if row[recall_key] is not None]
        count = len(measured)
        ranks = [row[f"{kind}_rank"] for row in measured]
        target_summary[f"{kind}_case_count"] = count
        target_summary[recall_key] = sum(row[recall_key] for row in measured) / count if count else None
        target_summary[f"{kind}_mrr"] = sum(1 / rank if rank else 0.0 for rank in ranks) / count if count else None
    required_count = sum(len(case["required_phrases"]) for case in suite["cases"])
    unknown_count = sum(len(case["required_unknown_phrases"]) for case in suite["cases"])
    required_missing = sum(len(row["missing_required_phrases"]) for row in rows)
    unknown_missing = sum(len(row["missing_unknown_phrases"]) for row in rows)
    return {
        "schema_version": "0.2", "suite_id": suite["suite_id"], "suite_audience": suite["audience"],
        "retriever_id": retriever_id, "corpus_sha256": corpus_sha256,
        "cases": rows,
        "summary": {"total": len(rows), "passed": sum(row["passed"] for row in rows),
                    **target_summary,
                    "mrr": sum(row["reciprocal_rank"] for row in rows) / len(rows),
                    "audience_leakage": sum(len(row["audience_leakage"]) for row in rows),
                    "required_phrase_count": required_count, "unknown_phrase_count": unknown_count,
                    "required_phrase_coverage": 1 - required_missing / required_count if required_count else None,
                    "unknown_phrase_coverage": 1 - unknown_missing / unknown_count if unknown_count else None,
                    "forbidden_phrase_hits": sum(len(row["forbidden_phrase_hits"]) for row in rows),
                    "duplicate_hit_ratio": sum(row["duplicate_hits"] for row in rows) / max(1, sum(len(row["hits"]) for row in rows)),
                    "source_release_correct": all(row["source_release_correct"] for row in rows)},
        "gate_status": "passed" if all(row["passed"] for row in rows) else "failed",
    }


def diagnose_context(suite: dict, units: dict, external: dict, contexts: dict, corpus_sha256: str, release_id: str) -> dict:
    """Compare retrieved full units with the excerpts supplied to the model."""
    report = evaluate_data(suite, units, external, corpus_sha256, release_id, all_external_candidates=True)
    if set(contexts) != {case["case_id"] for case in suite["cases"]}:
        raise RetrievalError("上下文记录与检索题集的用例不匹配")
    cases = []
    for case, row in zip(suite["cases"], report["cases"]):
        case_id = case["case_id"]
        if row["audience_leakage"]:
            raise RetrievalError(f"检索结果含超出受众范围的单元：{case_id}")
        excerpts = contexts[case_id]
        if not isinstance(excerpts, list):
            raise RetrievalError(f"上下文记录须为片段数组：{case_id}")
        retrieved_ids = set(row["hits"])
        context_ids = {}
        relevant_excerpts = []
        for excerpt in excerpts:
            if (not isinstance(excerpt, dict) or set(excerpt) != {"unit_id", "text"}
                    or not isinstance(excerpt["unit_id"], str)
                    or not isinstance(excerpt["text"], str) or not excerpt["text"].strip()):
                raise RetrievalError(f"上下文片段须包含单元 ID 和原文：{case_id}")
            unit_id = excerpt["unit_id"]
            if unit_id not in retrieved_ids or excerpt["text"] not in units[unit_id]["body"]:
                raise RetrievalError(f"上下文片段不属于本题已召回单元的原文：{case_id}")
            module_id = units[unit_id]["meta"]["module_id"]
            context_ids[unit_id] = module_id
            if unit_id in case["expected_unit_ids"] or module_id in case["expected_module_ids"]:
                relevant_excerpts.append(excerpt["text"])

        missing = {
            "module_ids": row["missing_module_ids"], "unit_ids": row["missing_unit_ids"],
            "required_phrases": row["missing_required_phrases"],
            "required_unknown_phrases": row["missing_unknown_phrases"],
        }
        lost = {
            "module_ids": sorted(set(case["expected_module_ids"]) - set(missing["module_ids"]) - set(context_ids.values())),
            "unit_ids": sorted(set(case["expected_unit_ids"]) - set(missing["unit_ids"]) - context_ids.keys()),
        }
        for key in ("required_phrases", "required_unknown_phrases"):
            lost[key] = [phrase for phrase in case[key] if phrase not in missing[key]
                         and not any(phrase in excerpt for excerpt in relevant_excerpts)]
        cases.append({"case_id": case_id, "retrieved_unit_ids": row["hits"], "context_unit_ids": list(context_ids),
                      "missing_at_retrieval": missing, "lost_during_assembly": lost})
    return {"schema_version": "0.1", "release_id": release_id, "suite_id": suite["suite_id"],
            "audience": suite["audience"], "retriever_id": report["retriever_id"],
            "corpus_sha256": corpus_sha256, "cases": cases}


def evaluate_in_release(release_root: Path, release_id: str, suite_path: Path, external_path: Path | None = None) -> dict:
    manifest_path = release_root / "检索清单" / f"{release_id}.json"
    manifest = strict_json(manifest_path)
    if manifest.get("release_id") != release_id:
        raise RetrievalError("检索清单 release ID 不匹配")
    suite = load_suite(suite_path)
    units = load_units(release_root, manifest)
    corpus_sha256 = digest(json_bytes(manifest["views"]))
    external = strict_json(external_path) if external_path else None
    report = evaluate_data(suite, units, external, corpus_sha256, release_id)
    report.update({"release_id": release_id, "manifest_units_sha256": digest(json_bytes(manifest["units"])), "suite_sha256": digest(suite_path.read_bytes())})
    report_path = release_root / "检索评测" / f"{release_id}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = release_root / "检索评测" / f"{release_id}.md"
    suite_copy = release_root / "检索评测" / "套件" / f"{release_id}.json"
    suite_copy.parent.mkdir(parents=True, exist_ok=True)
    suite_copy.write_bytes(suite_path.read_bytes())
    external_copy = None
    if external_path:
        external_copy = release_root / "检索评测" / "外部结果" / f"{release_id}.json"
        external_copy.parent.mkdir(parents=True, exist_ok=True)
        external_copy.write_bytes(external_path.read_bytes())
    report_path.write_bytes(json_bytes(report))
    summary = report["summary"]
    markdown = [f"# 检索评测：{release_id}", "", f"- 问题集：{suite['suite_id']}",
                f"- 检索器：{report['retriever_id']}", f"- 门禁：{report['gate_status']}",
                f"- 通过：{summary['passed']}/{summary['total']}"]
    coverage_metrics = (
        ("模块召回率", "module_recall_at_k", "module_case_count", "道标注题"),
        ("目标单元召回率", "unit_recall_at_k", "unit_case_count", "道标注题"),
        ("必要短语覆盖率", "required_phrase_coverage", "required_phrase_count", "条标注短语"),
        ("未知边界覆盖率", "unknown_phrase_coverage", "unknown_phrase_count", "条标注短语"),
    )
    for label, key, count_key, count_unit in coverage_metrics:
        value = summary[key]
        display = f"{value:.1%}" if value is not None else "未测"
        markdown.append(f"- {label} {display}（{summary[count_key]} {count_unit}）")
    for label, key in (("模块 MRR", "module_mrr"), ("目标单元 MRR", "unit_mrr")):
        value = summary[key]
        display = f"{value:.3f}" if value is not None else "未标注"
        markdown.append(f"- {label} {display}")
    markdown.extend(["", "## 用例", ""])
    for case, row in zip(suite["cases"], report["cases"]):
        markdown.extend([f"### {row['case_id']}", "", f"- 查询：{row['query']}",
                         f"- 结果：{', '.join(row['hits']) or '无命中'}"])
        for label, kind in (("首个预期模块排名", "module"), ("首个目标单元排名", "unit")):
            rank = row[f"{kind}_rank"]
            if rank is not None:
                display = str(rank)
            elif case[f"expected_{kind}_ids"]:
                display = f"未进入前 {case['top_k']} 条"
            else:
                display = "未标注"
            markdown.append(f"- {label} {display}")
        markdown.extend([
            f"- 通过：{'是' if row['passed'] else '否'}",
            f"- 未命中的预期模块：{', '.join(row['missing_module_ids']) or '无'}",
            f"- 未命中的目标单元：{', '.join(row['missing_unit_ids']) or '无'}",
            f"- 缺少必要短语：{', '.join(row['missing_required_phrases']) or '无'}",
            f"- 缺少未知边界：{', '.join(row['missing_unknown_phrases']) or '无'}",
            f"- 禁止断言命中：{', '.join(row['forbidden_phrase_hits']) or '无'}",
            f"- 受众泄漏：{', '.join(row['audience_leakage']) or '无'}", "",
        ])
    markdown_path.write_text("\n".join(markdown), encoding="utf-8")
    manifest["evaluation"] = {"suite_id": suite["suite_id"], "suite_path": f"发布/检索评测/套件/{release_id}.json", "suite_sha256": report["suite_sha256"], "report_path": f"发布/检索评测/{release_id}.json", "report_sha256": digest(report_path.read_bytes()), "report_markdown_path": f"发布/检索评测/{release_id}.md", "report_markdown_sha256": digest(markdown_path.read_bytes()), "external_results_path": f"发布/检索评测/外部结果/{release_id}.json" if external_copy else None, "external_results_sha256": digest(external_copy.read_bytes()) if external_copy else None, "retriever_id": report["retriever_id"], "corpus_sha256": corpus_sha256}
    manifest["gate_status"] = report["gate_status"]
    manifest_path.write_bytes(json_bytes(manifest))
    pointer_path = release_root / "当前检索版本.json"
    if report["gate_status"] == "passed":
        pointer = {"retrieval_schema_version": "0.1", "release_id": release_id,
                   "base_registry_sha256": manifest["base_registry_sha256"],
                   "manifest_path": f"发布/检索清单/{release_id}.json",
                   "manifest_sha256": digest(manifest_path.read_bytes())}
        pointer_path.write_bytes(json_bytes(pointer))
    elif pointer_path.exists():
        pointer_path.unlink()
    return report
