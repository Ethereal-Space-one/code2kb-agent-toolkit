"""English authoring boundaries and an actual audited FTS5 evidence path."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

import test_knowledge as fixture
from validation import content_language as lang, verifier, retrieval_profile
from validation.external_fts5 import probe
from validation.governance import replace_meta
from validation.governance import scan_business_terms


PUBLIC = Path(__file__).resolve().parents[2] / "conformance/english"
EXPECTED = json.loads((PUBLIC / "expected.json").read_text(encoding="utf-8"))
MODULE = EXPECTED["module_id"]


class LanguageUnitTests(unittest.TestCase):
    def test_strict_language_and_bilingual_word_boundaries(self):
        self.assertEqual(lang.declared({}), "zh-CN")
        for value in (None, "", "english", "fr", [], True):
            with self.subTest(value=value), self.assertRaises(ValueError):
                lang.declared({"content_language": value})
        for claim in ("Permission depends on ownership.", "The STATUS changes.", "名额 is limited"):
            self.assertEqual(verifier.risk_floor([claim]), "high")
        self.assertEqual(verifier.risk_floor(["A statement about reformatted text."]), "low")
        self.assertTrue(lang.BUSINESS_EN.search("The INTERNAL ENDPOINT uses a transaction annotation."))
        self.assertFalse(lang.BUSINESS_EN.search("Check your account, order status and permission to proceed."))
        self.assertFalse(lang.is_unknown("This order is not available."))
        scan_business_terms(fixture.core, "A commitment to your account does not change order status or permissions.", "English business text")
        with self.assertRaises(ValueError):
            scan_business_terms(fixture.core, "The internal endpoint uses a transaction annotation.", "English business text")
        # Frozen, pre-feature releases retain the previous English lexical rules.
        scan_business_terms(fixture.core, "The internal endpoint uses a transaction annotation.", "Legacy business text", english_rules=False)

    def test_unknown_loss_and_english_verifier_calibration(self):
        full = {"one": {"meta": {"audience": "business", "module_id": MODULE, "topic": "Order lookup"}, "body": "Actual behavior has not been verified."}}
        compact = {"one": {**full["one"], "body": "Actual behavior is available."}}
        self.assertFalse(retrieval_profile.compare(full, compact)["passed"])
        entry = {"ref": "one", "claim": "Missing orders return not_found.", "anchors": [{"anchor": "source:orders.py:5", "path": "orders.py", "line_start": 5, "line_end": 6, "text": 'if order is None: return {"error": "not_found"}', "snippet_sha256": "0" * 64}]}
        pack, key = verifier.build_calibration([entry], 1, 1, language="en")
        self.assertIn("independent verifier", pack["instructions"])
        self.assertIn("It is not the case that:", " ".join(item["claim"] for item in pack["items"]))
        self.assertNotRegex(json.dumps(pack, ensure_ascii=False), r"[\u3400-\u9fff]")
        changed = {**pack, "instructions": "Different instructions"}
        with self.assertRaisesRegex(ValueError, "不匹配"):
            verifier.score_calibration(changed, key, {})


class EnglishKnowledgeTests(unittest.TestCase):
    run_cli = fixture.KnowledgeTests.run_cli

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        repo = self.root / "source"
        shutil.copytree(PUBLIC / "source", repo)
        fixture.init_fixture_repo(repo)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=Example", "-c", "user.email=example@example.invalid", "commit", "-qm", "English fixture source"], check=True)
        commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        self.project = self.root / "knowledge"
        self.module = self.project / "知识源/Sales/Order lookup"
        self.config_path = self.project / "知识库配置.json"
        self.config = {"standard_version": "c2kb-file/1", "knowledge_source_root": "知识源", "content_language": "en", "repositories": {"source": {"path": str(repo), "commit": commit}}}
        fixture.write(self.config_path, json.dumps(self.config))
        revision = f"source={commit}"
        outline = f"---\ndocument_type: outline\nreview_status: draft\napplicability: current\nsource_revisions: {revision}\ninventory_status: complete\n---\n\n# Fixture inventory\n\n## 模块清单\n\n| module_id | 业务域 | 子模块 | 发现入口 | 状态 |\n| --- | --- | --- | --- | --- |\n| {MODULE} | Sales | Order lookup | Lookup function | 知识草稿 |\n\n## 入口证据索引\n\n| entry_id | 类型 | 入口或动作 | module_id | 证据 | 状态 |\n| --- | --- | --- | --- | --- | --- |\n| ENT-001 | 其他 | Lookup function | {MODULE} | source:orders.py:1 | 已归类 |\n\n## 入口受众\n\n| entry_id | 受众 | 范围 |\n| --- | --- | --- |\n| ENT-001 | 用户操作 | 范围内 |\n\n## 盘点覆盖说明\n\nFixture scope is this function only; production behavior is unknown.\n"
        fixture.write(self.project / "知识源/功能大纲.md", outline)
        spec = "# Order lookup: specification\n\n## 入口与调用链\n\n| fact_id | 单一结论与条件 | 证据等级 | 固定提交锚点 | 影响的知识文件 |\n| --- | --- | --- | --- | --- |\n"
        for item in EXPECTED["facts"]:
            spec += f"| {item['id']} | {item['claim']} | CODE_VERIFIED | source:orders.py:{item['line']} | 常见问答.md |\n"
        for heading, header in (("入口与接口", "entry_id | api_id | 调用条件 | 证据"), ("接口契约", "api_id | 接口标识 | 调用方 | 服务入口 | 主处理方法 | 证据"), ("调用匹配", "api_id | 匹配状态 | 调用方证据 | 服务方证据 | 部署配对 | 差异或边界"), ("方法职责", "method_id | 符号 | 职责 | 关键性 | 关联接口 | 源码锚点")):
            spec += f"\n## {heading}\n\n| {header} |\n| " + " | ".join(["---"] * len(header.split(" | "))) + " |\n"
        spec += "\n## 大纲覆盖核对\n\n| entry_id | 处置 | fact_ids | 说明 |\n| --- | --- | --- | --- |\n| ENT-001 | 已取证 | FACT-001, FACT-002, FACT-003 | Statically compared with the fixture function. |\n\n## 问答自测\n\nDesigned cases; static text comparison, not bot execution.\n\n| 类别 | 真实问题 | 预期行为 | 实测结果 | 结论 |\n| --- | --- | --- | --- | --- |\n"
        for category, question, expected in (("正常", EXPECTED["query"], "Signed-in users and assigned regions"), ("失败", "What if the order is missing?", "Not-found result"), ("未知", "Is production behavior proven?", "Not verified"), ("越权", "Can I access orders outside my region?", "No such permission is promised")):
            spec += f"| {category} | {question} | {expected} | Compared with fixture text; runtime not tested | 通过 |\n"
        self.document("结构化规格.md", "spec", spec, revisions=revision)
        self.document("常见问答.md", "faq", (PUBLIC / "knowledge.md").read_text(encoding="utf-8"))
        for filename, kind, title, text in (("模块概览.md", "overview", "Overview", "Read the questions for lookup conditions and answer boundaries."), ("功能与范围.md", "scope", "Features and scope", "This fixture describes one lookup function; actual production behavior is not verified."), ("规则与限制.md", "rules", "Rules and limitations", "The question text states all lookup conditions; actual production behavior is not verified.")):
            self.document(filename, kind, f"# Order lookup: {title}\n\n## Notes\n\n{text}\n")
        self.document("技术实现.md", "implementation", "# Order lookup: implementation\n\n## Evidence and boundaries\n\nFACT-001, FACT-002 and FACT-003 describe source:orders.py:1. Runtime behavior is not verified.\n", revisions=revision)
        fixture.write(self.project / "知识源/术语表.md", "---\ndocument_type: glossary\nreview_status: reviewed\nreviewed_by: fixture-reviewer\nreviewed_at: 2026-11-04\napplicability: current\ncontent_language: en\n---\n\n# Glossary\n\n## Assigned region\n\nA region included in an account's allowed set; actual assignments have not been verified.\n")
        self.assert_cli("confirm-claims", "--module-id", MODULE)
        fixture.init_fixture_repo(self.project)

    def document(self, filename, kind, body, revisions=None):
        meta = f"---\nmodule_id: {MODULE}\ndocument_type: {kind}\nreview_status: draft\napplicability: current\n"
        if kind != "spec":
            meta += "content_language: en\n"
        if revisions:
            meta += f"source_revisions: {revisions}\n"
        if kind == "implementation":
            meta += "runtime_status: source_only\n"
        fixture.write(self.module / filename, meta + "---\n\n" + body)

    def assert_cli(self, *args):
        result = self.run_cli(*args)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def prepare(self):
        return self.assert_cli("prepare", "--module-id", MODULE, "--auto-retrieval-metadata", "--refresh")

    def approve(self):
        self.assert_cli("approve", "--module-id", MODULE, "--reviewed-by", "fixture-reviewer", "--reviewed-at", "2026-11-04", "--approval-note", "Fixture-only authorization; no user project is authorized.")

    def commit(self):
        subprocess.run(["git", "-C", str(self.project), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.project), "-c", "user.name=Example", "-c", "user.email=example@example.invalid", "commit", "-qm", "English fixture inputs"], check=True)

    def test_configuration_and_document_language_cannot_disagree(self):
        self.assert_cli("check")
        path = self.module / "常见问答.md"
        original = path.read_text(encoding="utf-8")
        fixture.write(path, replace_meta(original, {"content_language": None}))
        for action in ("check", "prepare", "publish"):
            args = (action, "--module-id", MODULE) if action == "prepare" else (action,)
            result = self.run_cli(*args)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("content_language", result.stderr)

    def test_translation_invalidates_review_and_keeps_english_pack(self):
        first = self.prepare()
        pack = self.assert_cli("evidence-pack", "--module-id", MODULE, "--kind", "claim_entailment")
        self.assertIn("independent verifier", pack["instructions"])
        self.approve()
        path = self.module / "常见问答.md"
        fixture.write(path, path.read_text(encoding="utf-8") + "\nAdditional product wording, with no change to the source evidence.\n")
        self.assertNotEqual(self.run_cli("publish").returncode, 0)
        self.assert_cli("confirm-claims", "--module-id", MODULE)
        second = self.prepare()
        self.assertNotEqual(first["review_subject_digest"], second["review_subject_digest"])
        self.assertNotEqual(self.run_cli("publish").returncode, 0)

    def test_published_english_fts_keeps_conditions_and_unknowns_when_config_changes(self):
        self.prepare()
        self.approve()
        self.commit()
        self.assert_cli("publish", "--release-id", "english-v1")
        self.assert_cli("audit-release")
        release = self.project / "发布"
        business = release / "业务版/Sales/Order lookup/常见问答.md"
        self.assertEqual(business.read_bytes(), (release / "研发版/Sales/Order lookup/常见问答.md").read_bytes())
        for filename in ("目录.md", "发布信息.md", "检索索引.md"):
            text = (release / "业务版" / filename).read_text(encoding="utf-8")
            prose = re.sub(r"\]\([^)]*\)", "]", text)
            self.assertNotRegex(prose, r"[\u3400-\u9fff]")
        # Retrieval must use the frozen declaration, not mutable project settings.
        fixture.write(self.config_path, json.dumps({**self.config, "content_language": "zh-CN"}))
        self.assert_cli("retrieval-build", "--release-id", "english-v1")
        suite = {"schema_version": "0.1", "suite_id": "english-lookup", "audience": "business", "cases": [{"case_id": "lookup", "query": EXPECTED["query"], "expected_module_ids": [MODULE], "expected_unit_ids": [], "required_phrases": EXPECTED["required_phrases"], "required_unknown_phrases": EXPECTED["unknown_phrases"], "forbidden_phrases": EXPECTED["forbidden_phrases"], "top_k": 1}]}
        path = self.root / "suite.json"
        fixture.write(path, json.dumps(suite))
        report = self.assert_cli("retrieval-evaluate", "--release-id", "english-v1", "--suite", str(path))
        self.assertEqual(report["gate_status"], "passed")
        self.assert_cli("retrieval-audit", "--release-id", "english-v1")
        result = self.assert_cli("retrieval-query", "--query", EXPECTED["query"], "--audience", "business", "--top-k", "1")
        self.assertEqual(result["answerability"], "not_assessed")
        evidence = result["hits"][0]["text"]
        self.assertIn("## Sources", evidence)
        for phrase in EXPECTED["required_phrases"] + EXPECTED["unknown_phrases"]:
            self.assertIn(phrase, evidence)
        actual_fts = probe(self.project, "english-v1", "business", ['"assigned regions"'], top_k=1)
        hit = actual_fts["queries"][0]["ranking"][0]["unit_id"]
        manifest = json.loads((release / "检索清单/english-v1.json").read_text(encoding="utf-8"))
        entry = next(item for item in manifest["units"] if item["unit_id"] == hit)
        body = (self.project / entry["path"]).read_text(encoding="utf-8")
        for phrase in EXPECTED["required_phrases"] + EXPECTED["unknown_phrases"]:
            self.assertIn(phrase, body)

    def test_compact_english_project_keeps_the_same_review_path(self):
        fixture.write(self.project / "Code2KB工程配置.json", json.dumps({"schema_version": "0.1", "content_profile": "compact"}))
        self.prepare()
        self.approve()
        self.commit()
        self.assert_cli("publish", "--release-id", "english-compact-v1")
        self.assert_cli("audit-release")

    def test_frozen_audit_checks_language_and_crlf_english_disclosure(self):
        self.prepare()
        self.approve()
        self.commit()
        self.assert_cli("publish", "--release-id", "english-v1")
        release = self.project / "发布"
        local = "Sales/Order lookup/常见问答.md"
        business = release / "业务版" / local
        original = business.read_text(encoding="utf-8")
        registry_path = release / "版本清单/english-v1.json"
        pointer_path = release / "当前版本.json"

        def rehash():
            # Simulate an internally consistent but invalid imported snapshot.
            registry = json.loads(registry_path.read_text(encoding="utf-8"))
            for view in registry["views"].values():
                path = self.project / view["path"] / local
                view["files"][local] = hashlib.sha256(path.read_bytes()).hexdigest()
            fixture.write(registry_path, json.dumps(registry))
            pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
            pointer["registry_sha256"] = hashlib.sha256(registry_path.read_bytes()).hexdigest()
            fixture.write(pointer_path, json.dumps(pointer))

        fixture.write(business, replace_meta(original, {"content_language": None}))
        rehash()
        result = self.run_cli("audit-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inconsistent content_language", result.stderr)
        # The root glossary is also language-bound, despite not being a module file.
        fixture.write(business, original)
        glossary = release / "业务版/术语表.md"
        fixture.write(glossary, replace_meta(glossary.read_text(encoding="utf-8"), {"content_language": None}))
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["views"]["business"]["files"]["术语表.md"] = hashlib.sha256(glossary.read_bytes()).hexdigest()
        fixture.write(registry_path, json.dumps(registry))
        rehash()
        result = self.run_cli("audit-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("inconsistent content_language", result.stderr)
        fixture.write(glossary, replace_meta(glossary.read_text(encoding="utf-8"), {"content_language": "en"}))
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        registry["views"]["business"]["files"]["术语表.md"] = hashlib.sha256(glossary.read_bytes()).hexdigest()
        fixture.write(registry_path, json.dumps(registry))
        leaked = original + "\nThe internal endpoint uses a transaction annotation.\n"
        for view in ("业务版", "研发版"):
            (release / view / local).write_bytes(leaked.replace("\n", "\r\n").encode("utf-8"))
        rehash()
        result = self.run_cli("audit-release")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("禁用表述", result.stderr)


if __name__ == "__main__":
    unittest.main()
