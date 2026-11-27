"""Translate a recomputed upgrade preview into human work packets, without writes."""
from __future__ import annotations

from collections import defaultdict, deque
import hashlib
import json
import re

try:
    from .evidence_snapshot import git, parse_anchor, EvidenceError
except ImportError:
    from evidence_snapshot import git, parse_anchor, EvidenceError


def _node(module, kind, value):
    return (kind, value if "#" in value else module + "#" + value)


def _proofs(preview, relations):
    """One stable, shortest recorded dependency route per reached node and path."""
    edges = defaultdict(set)
    for mod, group in relations.items():
        for link in group["links"]:
            if link["status"] == "verified":
                edges[_node(mod, link["from_type"], link["from_id"])].add(
                    _node(mod, link["to_type"], link["to_id"]))
    origins = defaultdict(set); spans = defaultdict(list)
    for row in preview["changed_node_evidence"] + preview["changed_evidence"]:
        if row["outcome"] == "unchanged_excerpt" or row.get("status", "verified") != "verified":
            continue
        path, mod = row["source_path"], row["module_id"]
        spans[path].append((row["line_start"], row["line_end"]))
        if "node_id" in row:
            origins[path].add(_node(mod, row["kind"], row["node_id"]))
        else:
            origins[path].add(_node(mod, row["from_type"], row["from_id"]))
    result = defaultdict(list)
    for path, starts in sorted(origins.items()):
        todo = deque([(n, (n,)) for n in sorted(starts)])
        seen = set()
        while todo:
            node, chain = todo.popleft()
            if node in seen:
                continue
            seen.add(node)
            if node[0] in ("fact", "topic"):
                result[node[1].split("#", 1)[0]].append({
                    "source_path": path, "dependency_route": [f"{t}:{i}" for t, i in chain]})
            for nxt in sorted(edges[node]):
                if nxt not in seen:
                    todo.append((nxt, chain + (nxt,)))
    return result, spans


def _covered(repository, preview, path, spans):
    # A match on one excerpt must not hide another unmapped hunk in the same file.
    # Insertions, deletions, shifts, mode changes and binary deltas cannot be
    # discharged by an unchanged line-number mapping. Fall back, do not guess.
    raw = git(str(repository["path"]), "--literal-pathspecs", "diff", "--no-ext-diff",
              "--no-textconv", "--no-color", "--no-renames", "--unified=0",
              preview["old_commit"], preview["proposed_commit"], "--", path)
    if re.search(rb"^(?:old mode |new mode |Binary files |GIT binary patch)", raw, re.M):
        return None
    hunks = re.findall(rb"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", raw, re.M)
    if not hunks: return None
    intervals = sorted(spans)
    ranges = []
    for old, oc, new, nc in hunks:
        start, count = int(old), int(oc or b"1")
        if not count or int(new) != start or int(nc or b"1") != count:
            return None
        end, cursor = start + count - 1, start
        ranges.append((start,end))
        for first, last in intervals:
            if first > cursor: break
            cursor = max(cursor, last + 1)
            if cursor > end: break
        if cursor <= end: return None
    return ranges


def build(plan, preview, relations, repository, catalog):
    paths, spans = _proofs(preview, relations)
    gaps = []
    ranges = {}
    untraced = []
    if plan["decision"] == "selected_modules":
        for item in preview["changed_files"]:
            path = item["path"]
            ranges[path] = _covered(repository, preview, path, spans[path])
            if not ranges[path]:
                gaps.append(path)
        reached_rules = {f["fact_id"] for f in plan["must_review_facts"]}
        for module, rules in sorted(catalog.items()):
            for rule in rules:
                fact = module + "#" + rule["fact_id"]
                for value in re.split(r"[,，]", rule.get("anchors", "")):
                    try:
                        role, path, first, last = parse_anchor(value.strip())
                    except EvidenceError:
                        continue
                    if role == plan["repository_id"] and fact not in reached_rules and any(
                            start <= last and first <= end for start, end in ranges.get(path) or []):
                        untraced.append(fact)
                        break
    reasons = sorted(set(plan["fallback_reasons"]) | ({"diff_outside_verified_spans"} if gaps else set()))
    if untraced: reasons.append("changed_fact_without_verified_route")
    full = bool(reasons) or plan["decision"] != "selected_modules"
    queue = []
    for row in plan["baseline_migration"]["modules"]:
        module = row["module_id"]
        facts = [f for f in plan["must_review_facts"] if f["fact_id"].startswith(module + "#")]
        direct = [p["path"] for p in plan["changed_paths"] if module in p["modules"]]
        baseline = {k: row[k] for k in ("source_revision_files", "review_reset_files", "manifest_files", "relation_file",
                                         "evidence_records_rebuildable", "evidence_records_requiring_review")}
        mode = "review_module" if full or module in plan["selected_modules"] else "baseline_only"
        topics = [t for t in plan["affected_topics"] if t.startswith(module + "#")]
        if full:
            rule_scope = "all_rules"
        elif mode == "baseline_only":
            rule_scope = "baseline_only"
        elif facts:
            rule_scope = "named_rules_and_topics"
        elif topics and not direct:
            rule_scope = "consumer_topics"
        else:
            rule_scope = "all_module_rules"
        queue.append(dict(module_id=module, work=mode, rule_scope=rule_scope, changed_paths=direct, dependency_routes=paths.get(module, []),
                          facts=facts, topics=topics,
                          baseline=baseline, status="not_reviewed"))
    result = dict(schema_version="1.0", kind="source_upgrade_review_queue", repository_id=plan["repository_id"],
                  old_commit=plan["old_commit"], proposed_commit=plan["proposed_commit"], plan_sha256=plan["plan_sha256"],
                  disposition="full_project_review" if full else "selected_modules", fallback_reasons=reasons,
                  uncovered_diff_paths=gaps, untraced_changed_facts=sorted(set(untraced)), modules=queue, changed_paths=plan["changed_paths"],
                  published_unit_ids=plan["published_unit_ids"], unresolved_relations=plan["needs_evidence"],
                  runtime_evidence=plan["baseline_migration"]["runtime_evidence_requiring_independent_review"],
                  gate="fresh_evidence_and_explicit_approval_required", mutates_project=False)
    result["queue_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True, ensure_ascii=False,
                                                       separators=(",", ":")).encode()).hexdigest()
    return result
