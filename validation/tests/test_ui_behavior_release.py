"""Self-authored pinned UI truth through candidates, review and retrieval.

The export is a test fixture, not an automatic source extractor or authorization
for a user project. No Vue runtime, answer model or backend is executed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import test_knowledge as fixture
from test_collection_scope import git, point_anchors, write_json
from validation.evidence_snapshot import snapshot


PUBLIC = Path(__file__).resolve().parents[2] / "conformance/ui-behavior"
EXPECTED = json.loads((PUBLIC / "expected.json").read_text(encoding="utf-8"))
MODEL = json.loads((PUBLIC / "ui.json").read_text(encoding="utf-8"))
MODULE = EXPECTED["module_id"]
RELEASE = "ui-behavior-v1"


def digests(root):
    return {p.relative_to(root): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


class UIFixture:
    """Build only this frozen fixture; all approvals are explicitly test-only."""
    run_cli = fixture.KnowledgeTests.run_cli

    def __init__(self, root):
        self.root = root.resolve()
        self.project = self.root / "knowledge"
        self.module = self.project / "知识源/演练/界面控件"
        self.evidence = self.root / "evidence"

    def call(self, action, *args):
        result = self.run_cli(action, *args)
        if result.returncode:
            raise AssertionError(f"{action}: {result.stderr}")
        return json.loads(result.stdout)

    def build(self):
        if self.root.exists() and any(self.root.iterdir()):
            raise ValueError("fixture output root must be empty; existing work is never overwritten")
        self.root.mkdir(parents=True, exist_ok=True)
        repo = self.root / "source"
        shutil.copytree(PUBLIC / "sources", repo)
        source = repo / "ControlBehavior.vue"
        if hashlib.sha256(source.read_bytes()).hexdigest() != EXPECTED["source_sha256"]:
            raise AssertionError("fixture source changed without updating the frozen truth")
        fixture.init_fixture_repo(repo)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "self-authored UI behavior fixture"], check=True)
        pin = git(repo, "rev-parse", "HEAD")
        repositories = {"fixture": {"path": str(repo), "commit": pin}}
        write_json(self.project / "知识库配置.json", {
            "standard_version": "c2kb-file/1", "knowledge_source_root": "知识源",
            "repositories": repositories, "coverage_terms": ["控件演练"],
        })
        revision = f"fixture={pin}"

        def document(kind, body, *, technical=False):
            meta = (f"---\nmodule_id: {MODULE}\ndocument_type: {kind}\nreview_status: reviewed\n"
                    "reviewed_by: fixture-reviewer\nreviewed_at: 2026-11-16\napplicability: current\n")
            if technical or kind == "spec":
                meta += f"source_revisions: {revision}\n"
            if technical:
                meta += "runtime_status: source_only\n"
            return meta + "---\n\n" + body

        entries = EXPECTED["entries"]
        index = "\n".join(f"| {e['entry_id']} | 按钮 | {e['action']} | {MODULE} | fixture:ControlBehavior.vue:{e['line']} | 已归类 |"
                          for e in entries)
        audience = "\n".join(f"| {e['entry_id']} | 用户操作 | 范围内 |" for e in entries)
        fixture.write(self.project / "知识源/功能大纲.md",
            f"---\ndocument_type: outline\nreview_status: draft\napplicability: current\nsource_revisions: {revision}\n"
            "inventory_status: complete\n---\n\n# 控件演练限定范围\n\n## 模块清单\n\n"
            "| module_id | 业务域 | 子模块 | 发现入口 | 状态 |\n| --- | --- | --- | --- | --- |\n"
            f"| {MODULE} | 演练 | 界面控件 | 控件演练 | 知识草稿 |\n\n## 入口证据索引\n\n"
            "| entry_id | 类型 | 入口或动作 | module_id | 证据 | 状态 |\n| --- | --- | --- | --- | --- | --- |\n"
            f"{index}\n\n## 入口受众\n\n| entry_id | 受众 | 范围 |\n| --- | --- | --- |\n{audience}\n\n"
            "## 盘点覆盖说明\n\n控件演练仅限自编片段的四个按钮；不宣称实际应用完整，没有框架、设备、服务或部署证据。\n")
        facts = "\n".join(f"| {f['fact_id']} | {f['claim']} | CODE_VERIFIED | {', '.join(point_anchors(f))} | 规则与限制.md,常见问答.md,技术实现.md |"
                          for f in EXPECTED["facts"])
        spec = ("# 界面控件：结构化规格\n\n## 取证基线\n\n固定自编源码；只有静态证据，不运行组件或注入服务。\n\n"
                "## 入口与调用链\n\n| fact_id | 单一结论与条件 | 证据等级 | 固定提交锚点 | 影响的知识文件 |\n"
                f"| --- | --- | --- | --- | --- |\n{facts}\n\n")
        for heading, header, separator in (
            ("入口与接口", "| entry_id | api_id | 调用条件 | 证据 |", "| --- | --- | --- | --- |"),
            ("接口契约", "| api_id | 接口标识 | 调用方 | 服务入口 | 主处理方法 | 证据 |", "| --- | --- | --- | --- | --- | --- |"),
            ("方法职责", "| method_id | 符号 | 职责 | 关键性 | 关联接口 | 源码锚点 |", "| --- | --- | --- | --- | --- | --- |"),
            ("调用匹配", "| api_id | 匹配状态 | 调用方证据 | 服务方证据 | 部署配对 | 差异或边界 |", "| --- | --- | --- | --- | --- | --- |"),
        ):
            spec += f"## {heading}\n\n{header}\n{separator}\n\n"
        spec += ("## 冲突和未知\n\n注入服务、权限、持久化、最终业务完成及真实设备表现均未知；"
                 "未提供取消后回包、导航、乱序响应或跨模块交互材料，不补造转换或接口；注入函数若改变输入，其返回后的空内容组合未登记。\n\n"
                 "## 大纲覆盖核对\n\n| entry_id | 处置 | fact_ids | 说明 |\n| --- | --- | --- | --- |\n")
        spec += "\n".join(f"| {e['entry_id']} | 已取证 | {','.join(e['fact_ids'])} | 限固定自编片段 |" for e in entries)
        spec += ("\n\n## 问答自测\n\n设计问题只对照静态正文，不是回答模型成绩。\n\n"
                 "| 类别 | 真实问题 | 预期行为 | 实测结果 | 结论 |\n| --- | --- | --- | --- | --- |\n"
                 "| 正常 | 两个提交相同吗？ | 区分范围 | 静态正文已区分 | 通过 |\n"
                 "| 失败 | 失败会自动重试吗？ | 用户触发且有守卫 | 静态分支已核对 | 通过 |\n"
                 "| 未知 | 已返回等于已保存吗？ | 不等于 | 无后端运行证据 | 通过 |\n"
                 "| 越权 | 能证明服务端权限吗？ | 不能 | 仅静态披露检查，未测试实际拒答 | 通过 |\n\n"
                 "## 界面交互规格\n\n```json\n" + json.dumps(MODEL, ensure_ascii=False, indent=2) + "\n```\n")
        fixture.write(self.module / "结构化规格.md", document("spec", spec))
        fixture.write(self.module / "规则与限制.md", document("rules", "# 控件规则\n\n正文待合入。\n"))
        fixture.write(self.module / "常见问答.md", document("faq", (PUBLIC / "faq.md").read_text(encoding="utf-8")))
        fixture.write(self.module / "模块概览.md", document("overview", "# 控件演练\n\n## 范围\n\n四个自编按钮的静态语义，不提供实际业务结果保证。\n"))
        fixture.write(self.module / "功能与范围.md", document("scope", "# 控件演练：功能与范围\n\n## 范围\n\n报送表单与本地确认区域；服务、部署和其他组件不在范围内。\n"))
        fixture.write(self.module / "技术实现.md", document("implementation", "# 控件演练：技术实现\n\n等待合入候选。\n", technical=True))
        fixture.write(self.module / "待确认事项.md", f"---\nmodule_id: {MODULE}\ndocument_type: questions\nreview_status: draft\napplicability: current\n---\n\n# 待确认\n\n服务契约、运行权限、设备、持久化与最终业务结果均没有证据。\n")
        before = digests(self.project)
        candidate = self.call("render-ui-facts", "--module-id", MODULE)
        if before != digests(self.project):
            raise AssertionError("render-ui-facts mutated the project")
        write_json(self.evidence / "rendered-candidates.json", candidate)
        segments = candidate["segments"]
        # Simulated fixture-only review of frozen truth, never real approval.
        fixture.write(self.module / "规则与限制.md", document("rules", "# 控件规则\n\n" + "\n".join(s["business"] for s in segments)))
        fixture.write(self.module / "技术实现.md", document("implementation", "# 控件实现\n\n" + "\n".join(s["engineering"] for s in segments), technical=True))
        write_json(self.evidence / "source-snapshots.json", [{"fact_id": f["fact_id"], "snapshots": [snapshot(a, repositories) for a in f["anchors"]]} for f in EXPECTED["facts"]])
        self.call("confirm-claims", "--module-id", MODULE)
        write_json(self.evidence / "prepared.json", self.call("prepare", "--module-id", MODULE, "--refresh",
            "--business-topics", "控件显示可用条件与点击反馈", "--business-unknowns", "服务与最终业务结果",
            "--business-keywords", "报送,表单,提交,重试,关闭,对话框",
            "--engineering-topics", "固定源码与控件守卫", "--engineering-unknowns", "部署和运行",
            "--engineering-keywords", "控件,守卫",
            "--files", "模块概览.md,功能与范围.md,规则与限制.md,常见问答.md,技术实现.md"))
        for kind in ("claim_entailment", "qa_replay"):
            write_json(self.evidence / f"{kind}.json", self.call("evidence-pack", "--module-id", MODULE, "--kind", kind))
        self.call("approve", "--module-id", MODULE, "--reviewed-by", "fixture-reviewer", "--reviewed-at", "2026-11-16",
                  "--approval-note", "Explicit fixture-only test authorization; not approval of any user project.")
        fixture.init_fixture_repo(self.project)
        subprocess.run(["git", "-C", str(self.project), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "commit", "-qm", "fixture-only UI knowledge review"], check=True)
        suite = {"schema_version": "0.1", "suite_id": "ui-behavior", "audience": "business", "cases": [
            {**case, "expected_module_ids": [MODULE], "expected_unit_ids": [], "top_k": 3,
             "forbidden_phrases": ["fixture:", "FACT-", "UI-"]} for case in EXPECTED["cases"]]}
        write_json(self.evidence / "suite.json", suite)
        self.call("check")
        write_json(self.evidence / "publish.json", self.call("publish", "--release-id", RELEASE,
            "--with-retrieval", "--retrieval-suite", str(self.evidence / "suite.json")))
        write_json(self.evidence / "release-audit.json", self.call("audit-release", "--release-id", RELEASE))
        write_json(self.evidence / "retrieval-audit.json", self.call("retrieval-audit", "--release-id", RELEASE))
        queries = {case["case_id"]: self.call("retrieval-query", "--query", case["query"], "--audience", "business", "--top-k", "3") for case in suite["cases"]}
        write_json(self.evidence / "queries.json", queries)
        write_json(self.root / "fixture.json", {"fixture_only": True, "answer_model_run": False, "runtime_run": False,
            "module_id": MODULE, "release_id": RELEASE, "source_commit": pin, "source_sha256": EXPECTED["source_sha256"]})
        return self


def materialize(root):
    return UIFixture(root).build()


class UIBehaviorReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.example = materialize(Path(cls.temporary.name))

    def test_four_scoped_controls_render_and_retrieve_without_runtime_claims(self):
        example = self.example
        rendered = json.loads((example.evidence / "rendered-candidates.json").read_text(encoding="utf-8"))
        self.assertEqual(rendered["status"], "review_candidate")
        self.assertEqual(len(rendered["segments"]), 4)
        main, retry, local, close = rendered["segments"]
        self.assertNotIn("本地对话框", main["business"])
        self.assertIn("只打开本地对话框", local["business"])
        self.assertIn("没有自动重试", retry["business"])
        self.assertIn("不证明取消报送请求或回滚", close["business"])
        self.assertIn("fixture:ControlBehavior.vue:", main["engineering"])
        queries = json.loads((example.evidence / "queries.json").read_text(encoding="utf-8"))
        for case in EXPECTED["cases"]:
            response = queries[case["case_id"]]
            self.assertEqual(response["answerability"], "not_assessed")
            phrases = case["required_phrases"] + case["required_unknown_phrases"]
            self.assertTrue(any(all(p in h["text"] for p in phrases) for h in response["hits"]), case["case_id"])
            for hit in response["hits"]:
                self.assertNotIn("fixture:", hit["text"])
                self.assertTrue(hit["source_locations"])

    def test_guard_change_blocks_release_and_preserves_old_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            example = materialize(Path(directory))
            before = digests(example.project / "发布")
            spec = example.module / "结构化规格.md"
            fixture.write(spec, spec.read_text(encoding="utf-8").replace('"guard": "内容去除首尾空白后非空且当前未等待"', '"guard": "内容有效、选择已确认且当前未等待"', 1))
            impacts = example.call("impact", "--module-id", MODULE)["pending_impacts"]
            self.assertEqual({(row["fact_id"], row["file"]) for row in impacts},
                             {("FACT-003", name) for name in ("规则与限制.md", "常见问答.md", "技术实现.md")})
            self.assertNotEqual(example.run_cli("publish", "--release-id", "ui-behavior-v2").returncode, 0)
            self.assertEqual(before, digests(example.project / "发布"))
            example.call("audit-release", "--release-id", RELEASE)
            example.call("retrieval-audit", "--release-id", RELEASE)

    def test_optional_section_removal_requires_review(self):
        with tempfile.TemporaryDirectory() as directory:
            example = materialize(Path(directory))
            before = digests(example.project / "发布")
            spec = example.module / "结构化规格.md"
            self.assertEqual(example.call("impact", "--module-id", MODULE)["pending_impacts"], [])
            original = spec.read_text(encoding="utf-8")
            revised = fixture.replace_section(original, "## 界面交互规格", "")
            self.assertNotIn("## 界面交互规格", revised)
            self.assertIn("## 结论复核", original)
            self.assertEqual(original.split("## 结论复核", 1)[1], revised.split("## 结论复核", 1)[1])
            fixture.write(spec, revised)
            impacts = example.call("impact", "--module-id", MODULE)["pending_impacts"]
            self.assertEqual({row["fact_id"] for row in impacts}, {fact["fact_id"] for fact in EXPECTED["facts"]})
            self.assertNotEqual(example.run_cli("publish", "--release-id", "ui-behavior-v2").returncode, 0)
            self.assertEqual(before, digests(example.project / "发布"))
            example.call("audit-release", "--release-id", RELEASE)

    def test_reviewed_ui_revision_can_publish_a_new_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            example = materialize(Path(directory))
            release = example.project / "发布"
            # Commit the existing snapshot before preparing another release.
            subprocess.run(["git", "-C", str(example.project), "add", "."], check=True)
            subprocess.run(["git", "-C", str(example.project), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "retain fixture snapshot"], check=True)
            history_commit = git(example.project, "rev-parse", "HEAD")
            old_files = digests(release)
            spec = example.module / "结构化规格.md"
            fixture.write(spec, spec.read_text(encoding="utf-8").replace('"guard": "内容去除首尾空白后非空且当前未等待"',
                '"guard": "报送内容去除首尾空白后非空且当前未等待"', 1))
            candidate = example.call("render-ui-facts", "--module-id", MODULE)
            self.assertIn("报送内容去除首尾空白后非空且当前未等待", candidate["segments"][0]["business"])
            for name, audience in (("规则与限制.md", "business"), ("技术实现.md", "engineering")):
                path = example.module / name
                metadata = path.read_text(encoding="utf-8").split("---", 2)[1]
                fixture.write(path, "---" + metadata + "---\n\n# 控件复核修订\n\n" +
                              "\n".join(row[audience] for row in candidate["segments"]))
            # Fixture-only substantive comparison: the clarified guard means
            # precisely the existing trim/nonpending branch, no new behavior.
            example.call("confirm-claims", "--module-id", MODULE)
            example.call("prepare", "--module-id", MODULE, "--refresh",
                         "--business-topics", "控件显示可用条件与点击反馈", "--business-unknowns", "服务与最终业务结果",
                         "--business-keywords", "报送,表单,提交,重试,关闭,对话框",
                         "--engineering-topics", "固定源码与控件守卫", "--engineering-unknowns", "部署和运行",
                         "--engineering-keywords", "控件,守卫",
                         "--files", "模块概览.md,功能与范围.md,规则与限制.md,常见问答.md,技术实现.md")
            example.call("approve", "--module-id", MODULE, "--reviewed-by", "fixture-reviewer", "--reviewed-at", "2026-11-16",
                         "--approval-note", "Fixture-only review of equivalent readable trim guard; no user-project authorization.")
            subprocess.run(["git", "-C", str(example.project), "add", "."], check=True)
            subprocess.run(["git", "-C", str(example.project), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                            "commit", "-qm", "fixture-only guard clarification review"], check=True)
            example.call("publish", "--release-id", "ui-behavior-v2", "--with-retrieval",
                         "--retrieval-suite", str(example.evidence / "suite.json"))
            example.call("audit-release", "--release-id", "ui-behavior-v2")
            example.call("retrieval-audit", "--release-id", "ui-behavior-v2")
            # The existing contract keeps only the current working snapshot.
            # Restore committed history separately, rather than requiring v1
            # and v2 trees side by side or changing the publication format.
            previous = example.root / "previous-knowledge"
            subprocess.run(["git", "-C", str(example.project), "worktree", "add", "-q", "--detach", str(previous), history_commit], check=True)
            self.assertEqual(old_files, digests(previous / "发布"))
            restored = UIFixture(example.root)
            restored.project = previous
            restored.call("audit-release", "--release-id", RELEASE)
            restored.call("retrieval-audit", "--release-id", RELEASE)

    def test_export_never_overwrites_existing_work(self):
        with self.assertRaises(ValueError):
            materialize(self.example.root)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--export-fixture":
        result = materialize(Path(sys.argv[2]))
        print(json.dumps({"fixture_root": str(result.root), "project": str(result.project), "evidence": str(result.evidence)}, ensure_ascii=False))
    else:
        unittest.main()
