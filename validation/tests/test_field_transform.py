"""Source oracle and audited retrieval regression for one synthetic rule family."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import unittest

import test_knowledge as fixture

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "conformance" / "field-transform"
MODULE = "example.order.query"
TITLE = "临时档如何调整和匹配"
QUERY = "临时档如何调整和匹配，小端估重大端分别怎么算，产生空档怎么办？"
REQUIRED = (
    "调档系数 d 不大于 0", "小端加 d", "估重加 2d", "大端减 d",
    "保留小端原值", "保留估重原值", "保留大端原值", "不参与区间匹配",
    "左开右闭", "向后取档", "超最大档", "正式配置实值未证实",
)


class FieldTransformTests(unittest.TestCase):
    def test_source_oracle_preserves_distinct_fields_and_boundaries(self):
        case = runpy.run_path(str(EXAMPLE / "tiers.py"))
        small, large = case["BASE"]
        adjusted, select, tier = (case[n] for n in ("adjusted", "select", "Tier"))
        for d in (0, -1):
            self.assertIs(adjusted(large, d), large)
            self.assertEqual(select(5, d), ("小档", "命中"))
        self.assertEqual(adjusted(small, 1), tier("小档", 0, 5, 4))
        self.assertEqual(adjusted(large, 1), tier("大档", 6, 9, 9))
        self.assertEqual(adjusted(tier("对照", 0, 8, 4), 1), tier("对照", 0, 8, 4))
        for weight, expected in (
            (4, ("小档", "命中")), (5, ("大档", "向后取档")),
            (6, ("大档", "向后取档")), (7, ("大档", "命中")),
            (9, ("大档", "命中")), (10, (None, "超最大档")),
        ):
            with self.subTest(weight=weight):
                self.assertEqual(select(weight, 1), expected)
        self.assertEqual(small, tier("小档", 0, 3, 5))
        self.assertEqual(large, tier("大档", 5, 7, 10))

    def prepare_workspace(self, body, *, dependent_faq=False):
        env = fixture.KnowledgeTests("test_publish_isolated_views_and_no_overwrite")
        env.setUp()
        self.addCleanup(env.doCleanups)
        def call(action, *args):
            result = env.run_cli(action, *args)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        repo = Path(env.repos["backend"]["path"])
        before = env.repos["backend"]["commit"]
        src = (EXAMPLE / "tiers.py").read_text(encoding="utf-8")
        fixture.write(repo / "tiers.py", src)
        subprocess.run(["git", "-C", str(repo), "add", "tiers.py"], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-qm", "synthetic tiers"], check=True)
        pin = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        config = env.project / "知识库配置.json"
        fixture.write(config, config.read_text(encoding="utf-8").replace(before, pin))
        for path in env.source.rglob("*.md"):
            old = path.read_text(encoding="utf-8")
            if before in old:
                fixture.write(path, old.replace(before, pin))
        spec = env.module / "结构化规格.md"
        value = spec.read_text(encoding="utf-8")
        source_rows = []
        for i, (token, claim) in enumerate((
            ("if d <= 0", "系数非正时原档原样返回"),
            ("lower = ", "小端大于零才加系数"),
            ("estimate = ", "估重不大于七才加两倍系数"),
            ("upper = ", "大端至少五才减系数"),
            ("if tier.lower < weight", "左开右闭且空档向后选，不命中则超最大档"),
        ), 2):
            n = next(n for n, line in enumerate(src.splitlines(), 1) if token in line)
            source_rows.append(f"| FACT-{i:03d} | {claim} | CODE_VERIFIED | backend:tiers.py:{n} | 功能与范围.md |\n")
        marker = "\n## 入口与接口"
        self.assertEqual(value.count(marker), 1)
        fixture.write(spec, value.replace(marker, "".join(source_rows) + marker))
        scope = env.module / "功能与范围.md"
        fixture.write(scope, scope.read_text(encoding="utf-8") + "\n" + body)
        if dependent_faq:
            fixture.write(spec, spec.read_text(encoding="utf-8").replace(
                "frontend:dummy.txt:1 | 功能与范围.md", "frontend:dummy.txt:1 | 模块概览.md", 1))
            faq = env.module / "常见问答.md"
            fixture.write(faq, fixture.doc("faq", "过磅问题", reviewed=True)
                          + "\n## 大档余量\n\n大端减 d 后才是上界。\n")
            content = spec.read_text(encoding="utf-8")
            original = "| FACT-005 | 大端至少五才减系数 |"
            row = next(line for line in content.splitlines() if line.startswith(original))
            fixture.write(spec, content.replace(row, row.replace("功能与范围.md", "功能与范围.md,常见问答.md")))
        fixture.finalize_fixture(env.project, MODULE)
        return env, call, repo, pin

    def basic_suite(self, env):
        # A legacy-shaped evaluation still works for both, including the under-detailed control.
        # This is intentionally separate from the topic-specific completeness check below.
        suite = env.root / "basic.json"
        fixture.write(suite, json.dumps({
            "schema_version": "0.1", "suite_id": "general-operation", "audience": "business",
            "cases": [{"case_id": "basic", "query": "用户能看到什么操作说明",
                       "expected_module_ids": [MODULE], "expected_unit_ids": [],
                       "required_phrases": ["这是用户能看到的操作说明"],
                       "required_unknown_phrases": [], "forbidden_phrases": [], "top_k": 3}],
        }, ensure_ascii=False))
        return suite

    def publish_and_query(self, body):
        env, call, _, _ = self.prepare_workspace(body)
        self.publish_with_retrieval(call, "field-transform", self.basic_suite(env))
        return self.query_topic(call, "field-transform")

    def publish_with_retrieval(self, call, release_id, suite):
        call("publish", "--release-id", release_id, "--with-retrieval", "--retrieval-suite", str(suite))
        call("audit-release", "--release-id", release_id)
        call("retrieval-audit", "--release-id", release_id)

    def query_topic(self, call, release_id):
        response = call("retrieval-query", "--query", QUERY, "--top-k", "1")
        self.assertEqual(response["release_id"], release_id)
        self.assertEqual(len(response["hits"]), 1)
        hit = response["hits"][0]
        self.assertEqual(hit["audience"], "business")
        self.assertTrue(any(loc["heading"] == TITLE for loc in hit["source_locations"]), hit["source_locations"])
        self.assertNotIn("tiers.py", hit["text"])
        self.assertNotIn("FACT-", hit["text"])
        return hit["text"]

    def test_entire_topic_survives_audited_top_one_retrieval(self):
        hit = self.publish_and_query(self.example_body())
        self.assertEqual([item for item in REQUIRED if item not in hit], [])

    def test_audited_summary_is_not_a_complete_topic(self):
        hit = self.publish_and_query(f"## {TITLE}\n\n小端 / 估重 / 大端分别调整，匹配区间左开右闭，空档向后取档。\n")
        self.assertIn("分别调整", hit)
        missing = [item for item in REQUIRED if item not in hit]
        for phrase in ("小端加 d", "估重加 2d", "大端减 d", "正式配置实值未证实"):
            self.assertIn(phrase, missing)


    def example_body(self):
        readme = (EXAMPLE / "README.md").read_text(encoding="utf-8")
        return readme[readme.index(f"## {TITLE}"):readme.index("\n开发验证：")]

    def test_single_formula_upgrade_keeps_independent_fact_and_old_snapshot(self):
        body = self.example_body()
        env, call, repo, pin = self.prepare_workspace(body, dependent_faq=True)
        suite = self.basic_suite(env)

        def git(path, *args):
            return subprocess.check_output(["git", "-C", str(path), "-c", "user.name=Fixture",
                                            "-c", "user.email=fixture@example.invalid", *args]).strip()

        def inventory(path):
            return {p.relative_to(path): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in path.rglob("*") if p.is_file()}

        self.publish_with_retrieval(call, "field-before", suite)
        self.assertIn("大端减 d", self.query_topic(call, "field-before"))
        published = env.project / "发布"
        old_files = inventory(published)
        git(env.project, "add", "发布")
        git(env.project, "commit", "-qm", "Sealed fixture release before formula change")
        history = git(env.project, "rev-parse", "HEAD").decode()

        fixed = git(repo, "show", f"{pin}:tiers.py").decode() + "\n"
        self.assertEqual(fixed.count("tier.upper - d"), 1)
        fixture.write(repo / "tiers.py", fixed.replace("tier.upper - d", "tier.upper - 2 * d"))
        git(repo, "add", "tiers.py")
        git(repo, "commit", "-qm", "Change only the upper formula")
        new_pin = git(repo, "rev-parse", "HEAD").decode()
        new_source = git(repo, "show", f"{new_pin}:tiers.py").decode() + "\n"
        self.assertEqual(new_source, fixed.replace("tier.upper - d", "tier.upper - 2 * d"))
        for source, expected in (("before", ("小档", "命中")), ("after", ("大档", "向后取档"))):
            sample = env.root / f"{source}.py"
            fixture.write(sample, fixed if source == "before" else new_source)
            self.assertEqual(runpy.run_path(str(sample))["select"](4, 1), expected)

        config = env.project / "知识库配置.json"
        for target in [config, *env.source.rglob("*.md")]:
            text = target.read_text(encoding="utf-8")
            if pin in text:
                fixture.write(target, text.replace(pin, new_pin))
        spec = env.module / "结构化规格.md"
        original = spec.read_text(encoding="utf-8")
        self.assertEqual(original.count("大端至少五才减系数"), 1)
        fixture.write(spec, original.replace("大端至少五才减系数", "大端至少五才减两倍系数"))
        impacts = lambda: {(x["fact_id"], x["file"]) for x in
                           call("impact", "--module-id", MODULE)["pending_impacts"]}
        self.assertEqual(impacts(), {("FACT-005", "功能与范围.md"), ("FACT-005", "常见问答.md")})
        failed = env.run_cli("publish", "--release-id", "field-after", "--with-retrieval",
                             "--retrieval-suite", str(suite))
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(inventory(published), old_files)

        scope = env.module / "功能与范围.md"
        faq = env.module / "常见问答.md"
        for p in (scope, faq):
            revised = p.read_text(encoding="utf-8").replace("大端减 d", "大端减 2d")
            if p == scope:
                revised = (revised.replace("(0, 4]", "(0, 3]").replace("(6, 9]", "(6, 8]")
                           .replace("重量 5 向后取大档", "重量 4 或 5 向后取大档"))
            fixture.write(p, revised)
        queue_after_edit = impacts()
        self.assertIn(("FACT-003", "功能与范围.md"), queue_after_edit)  # same changed file
        self.assertNotIn(("FACT-001", "模块概览.md"), queue_after_edit)
        fixture.finalize_fixture(env.project, MODULE)
        self.assertEqual(impacts(), set())

        self.publish_with_retrieval(call, "field-after", suite)
        hit = self.query_topic(call, "field-after")
        for phrase in ("小端加 d", "估重加 2d", "大端减 2d", "(0, 3]", "(6, 8]", "重量 4 或 5 向后取大档"):
            self.assertIn(phrase, hit)
        self.assertNotIn("大端减 d", hit)
        current_business = "\n".join(p.read_text(encoding="utf-8")
                                     for p in (published / "业务版").rglob("*.md"))
        self.assertNotIn("大端减 d", current_business)

        archived = env.root / "sealed-old-release"
        archived.mkdir()
        git(env.project, "worktree", "add", "--detach", str(archived), history)
        previous = env.project
        try:
            env.project = archived
            self.assertEqual(inventory(archived / "发布"), old_files)
            call("audit-release", "--release-id", "field-before")
            call("retrieval-audit", "--release-id", "field-before")
            self.assertIn("大端减 d", self.query_topic(call, "field-before"))
        finally:
            env.project = previous
            git(env.project, "worktree", "remove", str(archived))
