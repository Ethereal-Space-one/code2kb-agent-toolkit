"""Bounded collection oracle -> authored facts/ENT -> audited retrieval.

No answer model or production application is run. The export option keeps the
actual release/query/context artifacts for a separate, held-out answer replay.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

# Also support the documented direct, fixture-only export invocation.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import test_knowledge as fixture
from validation.evidence_snapshot import snapshot
from validation.retrieval_model import digest, json_bytes


PUBLIC = Path(__file__).resolve().parents[2] / "conformance/collection-scope"
EXPECTED = json.loads((PUBLIC / "expected.json").read_text(encoding="utf-8"))
MODULE = EXPECTED["module_id"]
RELEASE = "collection-scope-v1"


def write_json(path: Path, value) -> None:
    fixture.write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()


def point_anchors(fact: dict) -> list[str]:
    # Fact tables use point anchors. Keep enough overlapping verifier windows
    # to cover the frozen ranges, which are also exported intact as snapshots.
    points = []
    for anchor in fact["anchors"]:
        path, lines = anchor.rsplit(":", 1)
        first, _, last = lines.partition("-")
        for line in range(int(first), int(last or first) + 1, 6):
            points.append(f"{path}:{line}")
    return list(dict.fromkeys(points))


class CollectionFixture:
    """A fixture-only project builder, not an extraction adapter or public API."""

    run_cli = fixture.KnowledgeTests.run_cli

    def __init__(self, root: Path):
        self.root = root.resolve()
        self.project = self.root / "knowledge"
        self.module = self.project / "知识源/演练/订单集合"
        self.evidence = self.root / "evidence"

    def call(self, action: str, *args: str) -> dict:
        result = self.run_cli(action, *args)
        if result.returncode:
            raise AssertionError(f"{action}: {result.stderr}")
        return json.loads(result.stdout)

    def build(self) -> dict:
        if self.root.exists() and any(self.root.iterdir()):
            raise ValueError("fixture output root must be empty; existing work is never overwritten")
        self.root.mkdir(parents=True, exist_ok=True)
        repo = self.root / "source"
        shutil.copytree(PUBLIC / "sources", repo)
        fixture.init_fixture_repo(repo)
        subprocess.run(["git", "-C", str(repo), "add", "orders.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "self-authored collection scope fixture"], check=True)
        pin = git(repo, "rev-parse", "HEAD")
        fixed_source = git(repo, "show", f"{pin}:orders.py") + "\n"
        if digest(fixed_source.encode()) != EXPECTED["source_sha256"]:
            raise AssertionError("fixture source changed without updating the frozen truth")
        repositories = {"fixture": {"path": str(repo), "commit": pin}}
        write_json(self.project / "知识库配置.json", {
            "standard_version": "c2kb-file/1", "knowledge_source_root": "知识源",
            "repositories": repositories, "coverage_terms": ["集合演练"],
        })
        self.repositories = repositories
        self.fixed_source = fixed_source
        version = f"fixture={pin}"

        def document(kind: str, body: str, *, technical=False) -> str:
            meta = (f"---\nmodule_id: {MODULE}\ndocument_type: {kind}\nreview_status: reviewed\n"
                    "reviewed_by: fixture-reviewer\nreviewed_at: 2026-11-16\napplicability: current\n")
            if technical or kind == "spec":
                meta += f"source_revisions: {version}\n"
            if technical:
                meta += "runtime_status: source_only\n"
            return meta + "---\n\n" + body

        entries = EXPECTED["entries"]
        index = "\n".join(
            f"| {e['entry_id']} | 其他 | {e['action']} | {MODULE} | fixture:orders.py:{e['line']} | 已归类 |"
            for e in entries)
        audience = "\n".join(f"| {e['entry_id']} | 用户操作 | 范围内 |" for e in entries)
        outline = (f"---\ndocument_type: outline\nreview_status: draft\napplicability: current\nsource_revisions: {version}\n"
                   "inventory_status: complete\n---\n\n# 集合演练限定范围\n\n## 模块清单\n\n"
                   "| module_id | 业务域 | 子模块 | 发现入口 | 状态 |\n| --- | --- | --- | --- | --- |\n"
                   f"| {MODULE} | 演练 | 订单集合 | 集合演练 | 知识草稿 |\n\n"
                   "## 入口证据索引\n\n| entry_id | 类型 | 入口或动作 | module_id | 证据 | 状态 |\n"
                   f"| --- | --- | --- | --- | --- | --- |\n{index}\n\n"
                   "## 入口受众\n\n| entry_id | 受众 | 范围 |\n| --- | --- | --- |\n"
                   f"{audience}\n\n## 盘点覆盖说明\n\n"
                   "集合演练只登记八个集合操作，不宣称应用入口穷尽。已知是固定集合语义；实际运行结果未知；界面、服务与部署不在范围内。\n")
        fixture.write(self.project / "知识源/功能大纲.md", outline)
        facts = "\n".join(
            f"| {f['fact_id']} | {f['claim']} | CODE_VERIFIED | {', '.join(point_anchors(f))} | 规则与限制.md,常见问答.md |"
            for f in EXPECTED["facts"])
        spec = ("# 订单集合：结构化规格\n\n## 入口与调用链\n\n"
                "| fact_id | 单一结论与条件 | 证据等级 | 固定提交锚点 | 影响的知识文件 |\n"
                f"| --- | --- | --- | --- | --- |\n{facts}\n\n")
        for heading, header, separator in (
            ("入口与接口", "| entry_id | api_id | 调用条件 | 证据 |", "| --- | --- | --- | --- |"),
            ("接口契约", "| api_id | 接口标识 | 调用方 | 服务入口 | 主处理方法 | 证据 |", "| --- | --- | --- | --- | --- | --- |"),
            ("方法职责", "| method_id | 符号 | 职责 | 关键性 | 关联接口 | 源码锚点 |", "| --- | --- | --- | --- | --- | --- |"),
            ("调用匹配", "| api_id | 匹配状态 | 调用方证据 | 服务方证据 | 部署配对 | 差异或边界 |", "| --- | --- | --- | --- | --- | --- |"),
        ):
            spec += f"## {heading}\n\n{header}\n{separator}\n\n"
        spec += ("## 冲突和未知\n\n实际权限、运行配置、批量执行、文件交付与持久化均没有证据；"
                 "这里不登记虚构接口或运行证据。\n\n## 大纲覆盖核对\n\n"
                 "| entry_id | 处置 | fact_ids | 说明 |\n| --- | --- | --- | --- |\n")
        spec += "\n".join(f"| {e['entry_id']} | 已取证 | {','.join(e['fact_ids'])} | 限本演练固定集合语义 |" for e in entries)
        spec += ("\n\n## 问答自测\n\n设计案例，未经真实使用者确认；仅静态正文对照，不是回答模型运行成绩。\n\n"
                 "| 类别 | 真实问题 | 预期行为 | 实测结果 | 结论 |\n| --- | --- | --- | --- | --- |\n")
        for case in EXPECTED["cases"]:
            category = {"invalid-selection": "失败", "runtime-unknown": "未知"}.get(case["case_id"], "正常")
            phrases = case["required_phrases"] + case["required_unknown_phrases"]
            spec += f"| {category} | {case['query']} | {'；'.join(phrases)} | 对照自编正文，未调用回答模型 | 通过 |\n"
        spec += "| 越权 | 可以披露内部实现吗？ | 业务正文只含限定集合规则，实际拒答未测试 | 仅静态披露检查 | 通过 |\n"
        fixture.write(self.module / "结构化规格.md", document("spec", spec))
        for name, kind in (("rules.md", "rules"), ("faq.md", "faq")):
            target = "规则与限制.md" if kind == "rules" else "常见问答.md"
            fixture.write(self.module / target, document(kind, (PUBLIC / name).read_text(encoding="utf-8")))
        fixture.write(self.module / "模块概览.md", document("overview", "# 订单集合演练\n\n## 范围\n\n参阅规则与问答中的筛选、分页、选择及不同目标范围；实际业务处理未知。\n"))
        fixture.write(self.module / "功能与范围.md", document("scope", "# 订单集合演练：功能与范围\n\n## 范围\n\n仅计算六条虚构订单的集合，不提供实际处理、交付或线上权限保证。\n"))
        technical = "# 订单集合演练：技术实现\n\n## 固定事实与证据\n\n" + "\n".join(
            f"- {f['fact_id']}：{f['claim']} 出处：{', '.join(f['anchors'])}。" for f in EXPECTED["facts"])
        fixture.write(self.module / "技术实现.md", document("implementation", technical + "\n", technical=True))
        fixture.write(self.module / "待确认事项.md",
                      f"---\nmodule_id: {MODULE}\ndocument_type: questions\nreview_status: draft\napplicability: current\n---\n\n"
                      "# 待确认事项\n\n实际运行、权限、文件交付和持久化没有证据；不在本集合演练的保证范围。\n")

        # Pin the exact snippets used by reviewers; existence is not entailment.
        snapshots = [{"fact_id": f["fact_id"], "snapshots": [snapshot(a, repositories) for a in f["anchors"]]}
                     for f in EXPECTED["facts"]]
        write_json(self.evidence / "source-snapshots.json", snapshots)
        self.call("confirm-claims", "--module-id", MODULE)
        prepared = self.call("prepare", "--module-id", MODULE, "--refresh",
                             "--business-topics", "订单筛选分页选择和目标范围", "--business-unknowns", "实际业务执行和交付",
                             "--business-keywords", "订单,筛选,分页,选择,批量,导出",
                             "--engineering-topics", "集合计算和固定源码", "--engineering-unknowns", "部署与运行",
                             "--engineering-keywords", "目标集合",
                             "--files", "模块概览.md,功能与范围.md,规则与限制.md,常见问答.md,技术实现.md")
        write_json(self.evidence / "prepared.json", prepared)
        write_json(self.evidence / "claim-pack.json", self.call("evidence-pack", "--module-id", MODULE, "--kind", "claim_entailment"))
        write_json(self.evidence / "qa-pack.json", self.call("evidence-pack", "--module-id", MODULE, "--kind", "qa_replay"))
        self.call("approve", "--module-id", MODULE, "--reviewed-by", "fixture-reviewer", "--reviewed-at", "2026-11-16",
                  "--approval-note", "Explicit fixture-only test authorization; not approval of any user project.")
        fixture.init_fixture_repo(self.project)
        subprocess.run(["git", "-C", str(self.project), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "fixture-only reviewed collection knowledge"], check=True)
        suite = {"schema_version": "0.1", "suite_id": "collection-scope", "audience": "business", "cases": [
            {**case, "expected_module_ids": [MODULE], "expected_unit_ids": [],
             "forbidden_phrases": EXPECTED["forbidden_phrases"], "top_k": 2}
            for case in EXPECTED["cases"]]}
        write_json(self.evidence / "suite.json", suite)
        self.call("check")
        write_json(self.evidence / "publish.json", self.call("publish", "--release-id", RELEASE,
                   "--with-retrieval", "--retrieval-suite", str(self.evidence / "suite.json")))
        write_json(self.evidence / "release-audit.json", self.call("audit-release", "--release-id", RELEASE))
        write_json(self.evidence / "retrieval-audit.json", self.call("retrieval-audit", "--release-id", RELEASE))
        manifest = json.loads((self.project / f"发布/检索清单/{RELEASE}.json").read_text(encoding="utf-8"))
        queries, results, contexts = {}, {}, {}
        for case in suite["cases"]:
            response = self.call("retrieval-query", "--query", case["query"], "--audience", "business", "--top-k", str(case["top_k"]))
            queries[case["case_id"]] = response
            results[case["case_id"]] = [{"unit_id": hit["unit_id"], "score": 1 / hit["rank"]} for hit in response["hits"]]
            # Full returned unit bodies are the explicit assembly policy here.
            contexts[case["case_id"]] = [{"unit_id": hit["unit_id"], "text": hit["text"]} for hit in response["hits"]]
        external = {"schema_version": "0.1", "suite_id": suite["suite_id"], "retriever_id": "lexical-v1-query-replay",
                    "corpus_sha256": digest(json_bytes(manifest["views"])), "cases": results}
        write_json(self.evidence / "queries.json", queries)
        write_json(self.evidence / "results.json", external)
        write_json(self.evidence / "contexts.json", contexts)
        diagnosis = self.call("retrieval-diagnose-context", "--release-id", RELEASE,
                              "--suite", str(self.evidence / "suite.json"), "--results", str(self.evidence / "results.json"),
                              "--contexts", str(self.evidence / "contexts.json"))
        write_json(self.evidence / "diagnosis.json", diagnosis)
        # These once-held-out wordings are now public regression questions. Keep
        # exact retrieval contexts for a fresh, separately blinded answer replay.
        replay = []
        for case in json.loads((PUBLIC / "replay-questions.json").read_text(encoding="utf-8")):
            response = self.call("retrieval-query", "--query", case["question"], "--audience", "business", "--top-k", "3")
            replay.append({**case, "release_id": response["release_id"],
                           "manifest_sha256": response["retrieval_manifest_sha256"],
                           "answerability": response["answerability"], "hits": response["hits"]})
        write_json(self.evidence / "replay-contexts.json", replay)
        metadata = {"fixture_only": True, "answer_model_run": False, "release_id": RELEASE, "source_commit": pin,
                    "source_sha256": EXPECTED["source_sha256"], "assembly_policy": "full returned unit bodies",
                    "source": "source/orders.py", "project": "knowledge", "evidence": "evidence"}
        write_json(self.root / "fixture.json", metadata)
        return metadata


def materialize(root: Path) -> CollectionFixture:
    result = CollectionFixture(root)
    result.build()
    return result


def oracle(fixed_source: str):
    name = "collection_scope_fixture_oracle"
    module = types.ModuleType(name)
    sys.modules[name] = module
    try:
        exec(compile(fixed_source, "orders.py", "exec"), module.__dict__)
    finally:
        del sys.modules[name]
    return module


class CollectionScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.example = materialize(Path(cls.temporary.name))

    def test_frozen_truth_matches_actual_in_memory_operations(self):
        app = oracle(self.example.fixed_source)
        sets = EXPECTED["sets"]

        def equal(name, actual):
            self.assertEqual(list(actual), sets[name], name)

        first = app.View()
        second = app.change_page(first, 2)
        equal("default_matching", app.matching_ids())
        equal("page_one", app.page_ids(first))
        equal("page_two", app.page_ids(second))
        cross = app.select_row(app.change_page(app.select_row(first, "O-101"), 2), "O-104")
        equal("cross_selected", sorted(cross.selected))
        equal("cross_batch", app.batch_targets(cross))
        equal("cross_export", app.export_targets(cross))
        self.assertEqual(cross.page, 2)
        equal("page_all_empty", sorted(app.select_page(second).selected))
        equal("page_all_existing", sorted(app.select_page(app.change_page(app.select_row(first, "O-101"), 2)).selected))
        equal("all_matching", sorted(app.select_matching(second).selected))
        changed = app.change_filter(cross, "complete")
        self.assertEqual(changed.page, 1)
        equal("changed_filter_matching", app.matching_ids(changed.status))
        equal("changed_filter_selected", sorted(changed.selected))
        equal("changed_filter_batch", app.batch_targets(changed))
        equal("changed_filter_export", app.export_targets(changed))
        equal("empty_batch", app.batch_targets(first))
        equal("default_matching", app.export_targets(first))
        with self.assertRaisesRegex(ValueError, "current page"):
            app.select_row(first, "O-104")
        self.assertEqual(first, app.View())
        with self.assertRaisesRegex(ValueError, "positive"):
            app.change_page(first, 0)

    def test_published_rules_faq_retrieval_and_exact_assembly_preserve_scope(self):
        example = self.example
        report = json.loads((example.project / f"发布/检索评测/{RELEASE}.json").read_text(encoding="utf-8"))
        self.assertEqual(report["gate_status"], "passed")
        self.assertEqual(report["summary"]["passed"], len(EXPECTED["cases"]))
        self.assertEqual(report["summary"]["audience_leakage"], 0)
        queries = json.loads((example.evidence / "queries.json").read_text(encoding="utf-8"))
        diagnosis = json.loads((example.evidence / "diagnosis.json").read_text(encoding="utf-8"))
        for row in diagnosis["cases"]:
            self.assertFalse(any(row["missing_at_retrieval"].values()), row)
            self.assertFalse(any(row["lost_during_assembly"].values()), row)
        for response in queries.values():
            self.assertEqual(response["answerability"], "not_assessed")
            self.assertEqual(response["release_id"], RELEASE)
            self.assertTrue(response["hits"])
            self.assertTrue(all(hit["audience"] == "business" for hit in response["hits"]))
            self.assertTrue(all(hit["source_locations"] for hit in response["hits"]))
        for case in EXPECTED["cases"]:
            phrases = case["required_phrases"] + case["required_unknown_phrases"]
            # Stronger than the evaluator's concatenated-module phrase gate:
            # one returned unit must keep this question's complete pairing.
            supporting = [hit for hit in queries[case["case_id"]]["hits"]
                          if all(phrase in hit["text"] for phrase in phrases)]
            self.assertTrue(supporting, case["case_id"])
            self.assertTrue(any(path.endswith("/常见问答.md") for hit in supporting for path in hit["source_paths"]), case["case_id"])
        for filename, original in (("规则与限制.md", "rules.md"), ("常见问答.md", "faq.md")):
            published = example.project / "发布/业务版/演练/订单集合" / filename
            self.assertIn((PUBLIC / original).read_text(encoding="utf-8").strip(), published.read_text(encoding="utf-8"))
        pack = json.loads((example.evidence / "qa-pack.json").read_text(encoding="utf-8"))
        self.assertEqual(pack["subject_digest"], json.loads((example.evidence / "prepared.json").read_text(encoding="utf-8"))["review_subject_digest"])
        questions = {item["question"] for item in pack["items"]}
        self.assertTrue({case["query"] for case in EXPECTED["cases"]} <= questions)

    def test_trimming_scope_boundary_is_detected_without_altering_release(self):
        example = self.example
        release = example.project / "发布"
        before = {p.relative_to(release): digest(p.read_bytes()) for p in release.rglob("*") if p.is_file()}
        contexts = json.loads((example.evidence / "contexts.json").read_text(encoding="utf-8"))
        contexts["cross-scope"] = [{"unit_id": contexts["cross-scope"][0]["unit_id"], "text": "O-101"}]
        path = example.evidence / "trimmed-contexts.json"
        write_json(path, contexts)
        report = example.call("retrieval-diagnose-context", "--release-id", RELEASE,
                              "--suite", str(example.evidence / "suite.json"), "--results", str(example.evidence / "results.json"),
                              "--contexts", str(path))
        cross = next(row for row in report["cases"] if row["case_id"] == "cross-scope")
        self.assertEqual(cross["missing_at_retrieval"]["required_phrases"], [])
        self.assertTrue(cross["lost_during_assembly"]["required_phrases"])
        self.assertTrue(cross["lost_during_assembly"]["required_unknown_phrases"])
        self.assertEqual(before, {p.relative_to(release): digest(p.read_bytes()) for p in release.rglob("*") if p.is_file()})


    def test_public_replay_questions_preserve_exact_sets_and_boundaries(self):
        replay = json.loads((self.example.evidence / "replay-contexts.json").read_text(encoding="utf-8"))
        gold = json.loads((PUBLIC / "replay-gold.json").read_text(encoding="utf-8"))
        self.assertEqual({case["id"] for case in replay}, set(gold))
        for case in replay:
            self.assertEqual(case["answerability"], "not_assessed")
            self.assertEqual(case["release_id"], RELEASE)
            self.assertEqual(len(case["hits"]), 3)
            self.assertTrue(all(hit["text"] and hit["source_locations"] for hit in case["hits"]))
        self.assertEqual(sum(len(case["sets"]) for case in gold.values()), 13)
        bindings = {
            "H1": {"visible": "page_one", "matching": "default_matching"},
            "H2": {"batch": "page_one"}, "H3": {"batch": "all_matching"},
            "H4": {"batch": "cross_batch", "export": "cross_export"},
            "H5": {"visible": "page_two", "export": "cross_export"},
            "H6": {}, "H7": {"selected": "changed_filter_selected", "batch": "changed_filter_batch"},
            "H8": {}, "H9": {"selected": "page_all_existing"},
            "H10": {"batch": "changed_filter_batch", "export": "changed_filter_export"},
        }
        for case_id, names in bindings.items():
            self.assertEqual(gold[case_id]["sets"], {scope: EXPECTED["sets"][name] for scope, name in names.items()}, case_id)
        # Gold/answers are never passed to retrieval or included in the contexts.
        self.assertTrue(all("sets" not in case and "answer" not in case for case in replay))

    def test_scope_fact_change_requires_review_without_replacing_old_release(self):
        with tempfile.TemporaryDirectory() as directory:
            example = materialize(Path(directory))
            release = example.project / "发布"
            before = {p.relative_to(release): digest(p.read_bytes()) for p in release.rglob("*") if p.is_file()}
            spec = example.module / "结构化规格.md"
            original = EXPECTED["facts"][6]["claim"]
            # Deliberately inject a different scope without reviewing its prose.
            # This checks stale-review invalidation, not semantic entailment.
            changed = "批量仅计算当前页目标，不再使用跨页已选集合。"
            fixture.write(spec, spec.read_text(encoding="utf-8").replace(original, changed))
            impacts = example.call("impact", "--module-id", MODULE)["pending_impacts"]
            self.assertEqual({(row["fact_id"], row["file"]) for row in impacts},
                             {("FACT-007", "规则与限制.md"), ("FACT-007", "常见问答.md")})
            failed = example.run_cli("publish", "--release-id", "collection-scope-v2")
            self.assertNotEqual(failed.returncode, 0)
            self.assertEqual(before, {p.relative_to(release): digest(p.read_bytes()) for p in release.rglob("*") if p.is_file()})
            example.call("audit-release", "--release-id", RELEASE)
            example.call("retrieval-audit", "--release-id", RELEASE)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--export-fixture":
        output = Path(sys.argv[2])
        result = materialize(output)
        print(json.dumps({"fixture_root": str(result.root), "project": str(result.project), "evidence": str(result.evidence)}, ensure_ascii=False))
    else:
        unittest.main()
