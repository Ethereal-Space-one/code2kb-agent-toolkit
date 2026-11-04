"""Self-authored mixed-language evidence → knowledge → audited retrieval cases.

Expected facts and authored business text are separate fixture inputs. These
tests check provenance and preservation, not model comprehension or runtime.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

import test_knowledge as fixture
from validation.adapters.platform import scan
from validation.evidence_snapshot import snapshot


PUBLIC = Path(__file__).resolve().parents[2] / "conformance/full-stack"
CASES = json.loads((PUBLIC / "expected.json").read_text(encoding="utf-8"))["cases"]


class FullStackKnowledgeTests(unittest.TestCase):
    run_cli = fixture.KnowledgeTests.run_cli

    def check_case(self, case_id: str) -> None:
        case = next(c for c in CASES if c["case_id"] == case_id)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name).resolve()
        self.project = root / "knowledge"
        source = self.project / "知识源"
        module = source / "演练" / case["topic"]
        module.mkdir(parents=True)
        revisions = {}
        for role in ("app", "support"):
            repo = root / role
            shutil.copytree(PUBLIC / case_id / "sources" / role, repo)
            fixture.init_fixture_repo(repo)
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Example", "-c", "user.email=example@example.invalid",
                            "commit", "-qm", "self-authored full-stack fixture"], check=True)
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            revisions[role] = {"path": str(repo), "commit": commit}
            for path in repo.rglob("*"):
                if path.is_file() and ".git" not in path.parts:
                    key = f"{role}/{path.relative_to(repo).as_posix()}"
                    self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), case["source_sha256"][key])
            candidates = scan(role, revisions[role], adapter_name="universal-l1", scope=case["app_scope"] if role == "app" else None)
            self.assertEqual({c["source_path"] for c in candidates["candidates"]},
                             {p.split("/", 1)[1] for p in case["source_sha256"] if p.startswith(role + "/")})
            self.assertEqual(candidates["edges"], [])

        points = []
        for fact in case["facts"]:
            cited = []
            for anchor in fact["anchors"]:
                record = snapshot(anchor, revisions)
                self.assertTrue(record["snippet_sha256"])
                role, path, line = anchor.rsplit(":", 2)
                cited.append(f"{role}:{path}:{line.split('-')[0]}")
            points.append(", ".join(cited))

        config = {"standard_version": "c2kb-file/1", "knowledge_source_root": "知识源",
                  "coverage_terms": ["案例指定行为"], "repositories": revisions}
        fixture.write(self.project / "知识库配置.json", json.dumps(config, ensure_ascii=False))
        module_id = case["module_id"]
        version_text = ", ".join(f"{r}={v['commit']}" for r, v in sorted(revisions.items()))

        def document(kind: str, text: str, *, technical=False) -> str:
            meta = f"---\nmodule_id: {module_id}\ndocument_type: {kind}\nreview_status: reviewed\nreviewed_by: fixture-reviewer\nreviewed_at: 2026-11-04\napplicability: current\n"
            if technical or kind == "spec":
                meta += f"source_revisions: {version_text}\n"
            if technical:
                meta += "runtime_status: source_only\n"
            return meta + "---\n\n" + text

        first_anchor = points[0].split(", ")[0]
        outline = f"---\ndocument_type: outline\nreview_status: draft\napplicability: current\nsource_revisions: {version_text}\ninventory_status: complete\n---\n\n# 案例限定范围\n\n## 模块清单\n\n| module_id | 业务域 | 子模块 | 发现入口 | 状态 |\n| --- | --- | --- | --- | --- |\n| {module_id} | 演练 | {case['topic']} | 案例指定行为 | 知识草稿 |\n\n## 入口证据索引\n\n| entry_id | 类型 | 入口或动作 | module_id | 证据 | 状态 |\n| --- | --- | --- | --- | --- | --- |\n| ENT-001 | 其他 | 案例指定行为 | {module_id} | {first_anchor} | 已归类 |\n\n## 盘点覆盖说明\n\n只核对案例指定行为及源码片段，不代表应用入口穷尽；运行行为未知。\n"
        fixture.write(source / "功能大纲.md", outline)
        facts = "\n".join(f"| {f['fact_id']} | {f['claim']} | CODE_VERIFIED | {anchors} | 模块概览.md |"
                          for f, anchors in zip(case["facts"], points))
        spec = f"# {case['topic']}：结构化规格\n\n## 入口与调用链\n\n| fact_id | 单一结论与条件 | 证据等级 | 固定提交锚点 | 影响的知识文件 |\n| --- | --- | --- | --- | --- |\n{facts}\n\n"
        for heading, header, separator in (
            ("入口与接口", "| entry_id | api_id | 调用条件 | 证据 |", "| --- | --- | --- | --- |"),
            ("接口契约", "| api_id | 接口标识 | 调用方 | 服务入口 | 主处理方法 | 证据 |", "| --- | --- | --- | --- | --- | --- |"),
            ("方法职责", "| method_id | 符号 | 职责 | 关键性 | 关联接口 | 源码锚点 |", "| --- | --- | --- | --- | --- | --- |"),
        ):
            spec += f"## {heading}\n\n{header}\n{separator}\n\n"
        spec += "## 问答自测\n\n设计案例，未经真实使用者确认；下列结果只表示静态正文对照。\n\n| 类别 | 真实问题 | 预期行为 | 实测结果 | 结论 |\n| --- | --- | --- | --- | --- |\n"
        for category, question, expected in (
            ("正常", case["query"], case["required_phrases"][0]),
            ("失败", "失败结果能否保证？", case["required_phrases"][-1]),
            ("未知", "线上是否已经验证？", case["unknown_phrases"][-1]),
            ("越权", "能否提供内部实现？", "业务正文不包含内部编号或路径；实际拒答未测试"),
        ):
            spec += f"| {category} | {question} | {expected} | 对照模块概览中的条件与未知，未执行机器人测试 | 通过 |\n"
        fixture.write(module / "结构化规格.md", document("spec", spec))
        business = (PUBLIC / case_id / "knowledge.md").read_text(encoding="utf-8")
        fixture.write(module / "模块概览.md", document("overview", f"# {case['topic']}\n\n" + business))
        fixture.write(module / "功能与范围.md", document("scope", f"# {case['topic']}：功能与范围\n\n## 范围\n\n只说明本模块所列条件与失败分支；实际使用权限和线上行为未验证。\n"))
        detail = "\n".join(f"- {f['fact_id']}：{f['claim']}；出处 {', '.join(f['anchors'])}。" for f in case["facts"])
        fixture.write(module / "技术实现.md", document("implementation", f"# {case['topic']}：技术实现\n\n## 证据与边界\n\n{detail}\n", technical=True))
        fixture.finalize_fixture(self.project, module_id)
        suite = {"schema_version": "0.1", "suite_id": case_id, "audience": "business", "cases": [{
            "case_id": case_id, "query": case["query"], "expected_module_ids": [module_id], "expected_unit_ids": [],
            "required_phrases": case["required_phrases"], "required_unknown_phrases": case["unknown_phrases"],
            "forbidden_phrases": case["forbidden_phrases"] + ["FACT-001", "source_revisions"], "top_k": 1,
        }]}
        suite_path = root / "retrieval-suite.json"
        fixture.write(suite_path, json.dumps(suite, ensure_ascii=False))
        for args in (("check",), ("publish", "--release-id", case_id, "--with-retrieval", "--retrieval-suite", str(suite_path)),
                     ("audit-release",), ("retrieval-audit", "--release-id", case_id)):
            result = self.run_cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
        result = self.run_cli("retrieval-query", "--query", case["query"], "--audience", "business", "--top-k", "1")
        self.assertEqual(result.returncode, 0, result.stderr)
        reply = json.loads(result.stdout)
        self.assertEqual(reply["answerability"], "not_assessed")
        self.assertEqual(len(reply["hits"]), 1)
        body = (self.project / reply["hits"][0]["unit_path"]).read_text(encoding="utf-8")
        for phrase in case["required_phrases"] + case["unknown_phrases"]:
            self.assertIn(phrase, body)
        for phrase in case["forbidden_phrases"] + ["FACT-001", "vendor/internal/ReportJob.cs"]:
            self.assertNotIn(phrase, body)

    def test_browser_service_conditions_reach_retrieval(self) -> None:
        self.check_case("browser-service")

    def test_page_worker_acceptance_does_not_become_completion(self) -> None:
        self.check_case("page-worker")

    def test_native_resource_failure_keeps_cleanup_boundary(self) -> None:
        self.check_case("native-resource")


if __name__ == "__main__":
    unittest.main()
