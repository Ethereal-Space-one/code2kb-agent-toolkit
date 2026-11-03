from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest import mock

import test_governance as gov
import test_knowledge as fixture
import verifier

core, write = fixture.core, fixture.write
MODULE = "example.order.query"
BASE_CHECKS = ["knowledge_check", "impact_clear", "qa_four_categories", "source_traceability", "cross_module_consistency", "sensitive_scan"]
REQUIREMENTS = {
    "required_kinds": [verifier.KIND_CLAIM], "min_calibration_recall": 0.9,
    "max_calibration_false_positive_rate": 0.1, "min_calibration_faults": 4, "calibration_max_age_days": 30,
}


def entry(ref, claim, text):
    snippet = verifier.sha(text)
    return {"ref": ref, "claim": claim, "anchors": [{"anchor": f"a:{ref}.txt:1", "path": f"{ref}.txt", "line_start": 1, "line_end": 1, "text": text, "snippet_sha256": snippet}]}


class VerifierUnitTests(unittest.TestCase):
    def test_risk_floor_only_raises(self):
        self.assertEqual(verifier.risk_floor(["用户可提交查询"]), "low")
        for term in verifier.HIGH_IMPACT_TERMS:
            self.assertEqual(verifier.risk_floor([f"这里涉及{term}判断"]), "high")

    def test_requirements_reject_permissive_or_malformed_values(self):
        verifier.validate_requirements(dict(REQUIREMENTS))
        bad = [
            {**REQUIREMENTS, "required_kinds": [verifier.KIND_QA]},
            {**REQUIREMENTS, "required_kinds": [verifier.KIND_CLAIM, verifier.KIND_CLAIM]},
            {**REQUIREMENTS, "min_calibration_recall": 0},
            {**REQUIREMENTS, "max_calibration_false_positive_rate": 1},
            {**REQUIREMENTS, "min_calibration_faults": 0},
            {**REQUIREMENTS, "calibration_max_age_days": True},
            {**REQUIREMENTS, "extra": 1},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier.validate_requirements(value)

    def calibration(self, answer):
        entries = [entry("one", "甲成立", "line one"), entry("two", "乙成立", "line two"), entry("three", "丙成立", "line three")]
        pack, key = verifier.build_calibration(entries, 7, 3)
        answers = {"verifier": {"id": "v1"}, "items": [
            {"item_id": item_id, "verdict": answer(truth), "reason": "x"} for item_id, truth in key["items"].items()]}
        return pack, key, answers

    def test_calibration_is_deterministic_and_scores_faults(self):
        first = self.calibration(lambda truth: "supported")
        second = self.calibration(lambda truth: "supported")
        self.assertEqual(first[0], second[0])
        faults = {item["fault"] for item in first[1]["items"].values()}
        self.assertEqual(faults, {"none", "negated", "overreach", "invented_effect", "injection", "wrong_anchor"})
        sloppy = verifier.score_calibration(*first)
        self.assertEqual(sloppy["recall"], 0.0)
        ideal_pack, ideal_key, ideal_answers = self.calibration(lambda truth: "supported" if truth["expected"] == "supported" else "unsupported")
        ideal = verifier.score_calibration(ideal_pack, ideal_key, ideal_answers)
        self.assertEqual((ideal["recall"], ideal["false_positive_rate"]), (1.0, 0.0))
        with self.assertRaises(ValueError):
            verifier.score_calibration({**ideal_pack, "seed": 8}, ideal_key, ideal_answers)

    def test_calibration_answers_must_cover_every_item(self):
        pack, key, answers = self.calibration(lambda truth: "supported")
        answers["items"].pop()
        with self.assertRaises(ValueError):
            verifier.score_calibration(pack, key, answers)

    def test_calibration_report_thresholds_age_and_arithmetic(self):
        pack, key, answers = self.calibration(lambda truth: "supported" if truth["expected"] == "supported" else "unsupported")
        report = verifier.score_calibration(pack, key, answers)
        requirements = {**REQUIREMENTS, "min_calibration_faults": 1}
        verifier.validate_calibration(report, verifier_id="v1", requirements=requirements)
        cases = [
            ({"verifier_id": "other"}, "另一位"),
            ({"recall": 0.5}, "不一致"),
            ({"faults_caught": 0}, "不一致"),
            ({"extra": 1}, "字段"),
            ({"generated_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()}, "未来"),
            ({"generated_at": (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()}, "有效期"),
            ({"generated_at": "2020-01-01T00:00:00"}, "时区"),
        ]
        for changes, expected in cases:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, expected):
                verifier.validate_calibration({**report, **changes}, verifier_id="v1", requirements=requirements)
        with self.assertRaisesRegex(ValueError, "数量"):
            verifier.validate_calibration(report, verifier_id="v1", requirements={**requirements, "min_calibration_faults": 1000})

    def test_envelope_demands_independence_and_exact_coverage(self):
        expected = [{"file": "业务.md", "file_sha256": "0" * 64}]
        good = {
            "verifier": {"id": "v1", "kind": "ai", "session_id": "s"}, "subject_producers": ["author"],
            "coverage": {"items_expected": 1, "items_checked": 1}, "status": "passed",
            "items": [{"file": "业务.md", "file_sha256": "0" * 64, "verdict": "clean", "reason": ""}],
        }
        kwargs = {"executed_by": "ci", "policy_owner": "owner"}
        verifier.validate_envelope(verifier.KIND_LEAK, good, expected, **kwargs)
        for changes, expected_text in [
            ({"subject_producers": ["v1"]}, "独立"),
            ({"verifier": {**good["verifier"], "id": "ci"}}, "独立"),
            ({"verifier": {**good["verifier"], "id": "owner"}}, "独立"),
            ({"coverage": {"items_expected": 2, "items_checked": 1}}, "覆盖计数"),
            ({"items": []}, "覆盖计数"),
            ({"status": "failed"}, "status"),
            ({"items": [{"file": "业务.md", "file_sha256": "1" * 64, "verdict": "clean", "reason": ""}]}, "文件内容"),
            ({"items": [{"file": "其他.md", "file_sha256": "0" * 64, "verdict": "clean", "reason": ""}]}, "应查范围"),
            ({"items": [{"file": "业务.md", "file_sha256": "0" * 64, "verdict": "leak", "reason": ""}], "status": "failed"}, "原因"),
        ]:
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, expected_text):
                verifier.validate_envelope(verifier.KIND_LEAK, {**good, **changes}, expected, **kwargs)


class VerifierProjectTests(unittest.TestCase):
    setUp = fixture.KnowledgeTests.setUp
    run_cli = fixture.KnowledgeTests.run_cli
    commit_project = gov.GovernanceTests.commit_project
    enable_policy = gov.GovernanceTests.enable_policy
    prepare_policy_candidate = gov.GovernanceTests.prepare_policy_candidate
    policy_record = gov.GovernanceTests.policy_record

    def enable_verifier_policy(self, requirements=None, kinds=(verifier.KIND_CLAIM,), **overrides):
        required = sorted(set(BASE_CHECKS) | set(kinds))
        self.enable_policy(schema_version="1.1", required_checks=required,
                           verifier_requirements={**REQUIREMENTS, "required_kinds": list(kinds), **(requirements or {})}, **overrides)
        return required

    def calibrate(self, verifier_id="verifier-ai-1", sloppy=False):
        key_path = self.root / f"key-{verifier_id}.json"
        result = self.run_cli("verifier-calibrate", "--key-out", str(key_path))
        self.assertEqual(result.returncode, 0, result.stderr)
        pack = json.loads(result.stdout)
        key = json.loads(key_path.read_text(encoding="utf-8"))
        answers = {"verifier": {"id": verifier_id}, "items": [
            {"item_id": item_id, "verdict": "supported" if sloppy or truth["expected"] == "supported" else "unsupported", "reason": "校准作答"}
            for item_id, truth in key["items"].items()]}
        for name, value in (("pack", pack), ("key", key), ("answers", answers)):
            write(self.root / f"{name}-{verifier_id}.json", json.dumps(value, ensure_ascii=False))
        scored = self.run_cli("verifier-calibrate", "--pack", str(self.root / f"pack-{verifier_id}.json"),
                              "--key", str(key_path), "--answers", str(self.root / f"answers-{verifier_id}.json"))
        self.assertEqual(scored.returncode, 0, scored.stderr)
        return json.loads(scored.stdout)

    def build_envelope(self, subject, short, verifier_id="verifier-ai-1", calibration=None, schema="0.2"):
        kind = verifier.SHORT_KINDS[short]
        result = self.run_cli("evidence-pack", "--module-id", MODULE, "--kind", short)
        self.assertEqual(result.returncode, 0, result.stderr)
        pack = json.loads(result.stdout)
        items = []
        for item in pack["items"]:
            if kind == verifier.KIND_CLAIM:
                shaped = {"fact_id": item["fact_id"], "claim_sha256": item["claim_sha256"],
                          "anchors": [{"anchor": a["anchor"], "snippet_sha256": a["snippet_sha256"]} for a in item["anchors"]]}
            elif kind == verifier.KIND_QA:
                shaped = {"category": item["category"], "question_sha256": item["question_sha256"]}
            else:
                shaped = {"file": item["file"], "file_sha256": item["file_sha256"]}
            items.append({**shaped, "verdict": verifier.PASS_VERDICT[kind], "reason": ""})
        envelope = {
            "schema_version": schema, "subject_digest": subject, "module_id": MODULE, "tool": kind, "status": "passed",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "verifier": {"id": verifier_id, "kind": "ai", "session_id": "session-1"},
            "subject_producers": ["author-agent"],
            "coverage": {"items_expected": len(items), "items_checked": len(items)}, "items": items,
        }
        if calibration:
            envelope["calibration"] = {"path": calibration["path"], "sha256": calibration["sha256"]}
        return envelope

    def submit(self, subject, required, envelopes, **record_overrides):
        reports, checks = [], {check: {"check_id": check, "status": "passed", "report_sha256": core.digest(check)} for check in required}
        for kind, envelope in envelopes.items():
            path = f"自动审核报告/{kind.split('.')[-1]}.json"
            body = json.dumps(envelope, ensure_ascii=False, sort_keys=True) + "\n"
            write(self.project / path, body)
            sha = core.digest(body)
            checks[kind]["report_sha256"] = sha
            reports.append({"name": kind, "result": "passed", "sha256": sha, "path": path})
        record = self.policy_record(subject, checks=[checks[name] for name in sorted(checks)], external_reports=reports, **record_overrides)
        self.commit_project("记录验证者报告")
        return self.run_cli("policy-review", "--module-id", MODULE, "--evidence-file", record.relative_to(self.project).as_posix(), "--executed-by", "ci-bot")

    def calibrated_run(self, **options):
        required = self.enable_verifier_policy()
        subject = self.prepare_policy_candidate()
        calibration = self.calibrate()
        self.commit_project("提交校准报告")
        envelope = self.build_envelope(subject, "claim_entailment", calibration=calibration)
        return required, subject, envelope

    def test_calibrated_independent_verifier_passes_policy_review(self):
        required, subject, envelope = self.calibrated_run()
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(core.parse_frontmatter(self.module / "模块概览.md")[0]["review_status"], "policy_reviewed")

    def test_all_three_kinds_can_be_required_and_pass(self):
        kinds = tuple(sorted(verifier.VERIFIER_KINDS))
        required = self.enable_verifier_policy(kinds=kinds)
        subject = self.prepare_policy_candidate()
        calibration = self.calibrate()
        self.commit_project("提交校准报告")
        envelopes = {
            verifier.SHORT_KINDS[short]: self.build_envelope(subject, short, calibration=calibration if short == "claim_entailment" else None)
            for short in verifier.SHORT_KINDS
        }
        result = self.submit(subject, required, envelopes)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_policy_1_0_still_accepts_envelope_0_2_without_calibration(self):
        required = sorted(set(BASE_CHECKS) | {verifier.KIND_CLAIM})
        self.enable_policy(required_checks=required)
        subject = self.prepare_policy_candidate()
        result = self.submit(subject, required, {verifier.KIND_CLAIM: self.build_envelope(subject, "claim_entailment")})
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_tampered_envelope_is_rejected(self):
        required, subject, envelope = self.calibrated_run()
        item = envelope["items"][0]
        cases = [
            ("结论文字", lambda e: e["items"][0].update(claim_sha256="0" * 64)),
            ("源码片段", lambda e: e["items"][0]["anchors"][0].update(snippet_sha256="0" * 64)),
            ("源码片段", lambda e: e["items"][0].update(anchors=[])),
            ("覆盖计数", lambda e: e.update(items=[])),
            ("独立", lambda e: e["verifier"].update(id="ci-bot")),
            ("独立", lambda e: e["verifier"].update(id="example-owner")),
            ("独立", lambda e: e.update(subject_producers=["verifier-ai-1"])),
            ("校准报告", lambda e: e.pop("calibration")),
            ("校准报告", lambda e: e["calibration"].update(sha256="0" * 64)),
            ("校准报告", lambda e: e["calibration"].update(path="自动审核报告/不存在.json")),
            ("校准报告", lambda e: e["calibration"].update(path="自动审核报告/claim_entailment.json")),
        ]
        for index, (expected, mutate) in enumerate(cases):
            with self.subTest(index=index, expected=expected):
                changed = json.loads(json.dumps(envelope))
                mutate(changed)
                result = self.submit(subject, required, {verifier.KIND_CLAIM: changed}, run_id=f"weekly-tamper-{index}")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)
        self.assertEqual(item["verdict"], "supported")

    def test_flagged_claim_blocks_policy_review(self):
        required, subject, envelope = self.calibrated_run()
        envelope["items"][0].update(verdict="unsupported", reason="片段未说明提交条件")
        envelope["status"] = "failed"
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope})
        self.assertNotEqual(result.returncode, 0)

    def test_verifier_that_misses_injected_faults_cannot_be_used(self):
        required = self.enable_verifier_policy()
        subject = self.prepare_policy_candidate()
        calibration = self.calibrate(sloppy=True)
        self.commit_project("提交校准报告")
        envelope = self.build_envelope(subject, "claim_entailment", calibration=calibration)
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("错误抓取率", result.stderr)

    def test_calibration_belongs_to_one_verifier(self):
        required = self.enable_verifier_policy()
        subject = self.prepare_policy_candidate()
        calibration = self.calibrate("verifier-ai-1")
        self.commit_project("提交校准报告")
        envelope = self.build_envelope(subject, "claim_entailment", verifier_id="verifier-ai-2", calibration=calibration)
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope})
        self.assertIn("另一位验证者", result.stderr)

    def test_old_envelope_is_rejected_when_policy_requires_verifier(self):
        required = self.enable_verifier_policy()
        subject = self.prepare_policy_candidate()
        envelope = {"schema_version": "0.1", "subject_digest": subject, "module_id": MODULE, "tool": verifier.KIND_CLAIM,
                    "status": "passed", "generated_at": datetime.now(timezone.utc).isoformat()}
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope})
        self.assertIn("0.2 验证者信封", result.stderr)

    def test_risk_floor_and_semantic_quality_gate(self):
        spec = self.module / "结构化规格.md"
        write(spec, spec.read_text(encoding="utf-8").replace("用户可提交查询", "用户须具备权限才可提交查询"))
        self.assertEqual(self.run_cli("confirm-claims", "--module-id", MODULE).returncode, 0)
        required = self.enable_verifier_policy(allowed_risk_levels=["low", "medium", "high"])
        subject = self.prepare_policy_candidate()
        calibration = self.calibrate()
        self.commit_project("提交校准报告")
        envelope = self.build_envelope(subject, "claim_entailment", calibration=calibration)
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope}, risk_level="low")
        self.assertIn("下限", result.stderr)
        result = self.submit(subject, required, {verifier.KIND_CLAIM: envelope}, risk_level="high", run_id="weekly-high")
        self.assertIn("semantic_quality", result.stderr)

    def test_policy_schema_rules(self):
        self.enable_policy(schema_version="1.1")
        subject = self.prepare_policy_candidate()
        record = self.policy_record(subject)
        command = ("policy-review", "--module-id", MODULE, "--evidence-file", record.relative_to(self.project).as_posix(), "--executed-by", "ci-bot")
        for policy, expected in (
            ({"schema_version": "1.1"}, "verifier_requirements"),
            ({"verifier_requirements": dict(REQUIREMENTS)}, "verifier_requirements"),
            ({"schema_version": "1.1", "verifier_requirements": dict(REQUIREMENTS)}, "required_checks"),
        ):
            with self.subTest(policy=policy):
                self.enable_policy(**policy)
                result = self.run_cli(*command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr)

    def test_evidence_pack_requires_current_draft_candidate(self):
        self.assertNotEqual(self.run_cli("evidence-pack", "--module-id", MODULE, "--kind", "claim_entailment").returncode, 0)
        subject = self.prepare_policy_candidate()
        for short, key in (("claim_entailment", "fact_id"), ("qa_replay", "category"), ("leak_probe", "file")):
            pack = json.loads(self.run_cli("evidence-pack", "--module-id", MODULE, "--kind", short).stdout)
            self.assertEqual(pack["subject_digest"], subject)
            self.assertTrue(pack["items"] and all(key in item for item in pack["items"]))
        claim = json.loads(self.run_cli("evidence-pack", "--module-id", MODULE, "--kind", "claim_entailment").stdout)
        self.assertIn("frontend", claim["items"][0]["anchors"][0]["text"])

    def test_calibration_command_guards(self):
        self.assertNotEqual(self.run_cli("verifier-calibrate").returncode, 0)
        inside = self.project / "key.json"
        self.assertIn("项目目录之外", self.run_cli("verifier-calibrate", "--key-out", str(inside)).stderr)
        self.assertFalse(inside.exists())
        outside = self.root / "answer-key.json"
        self.assertEqual(self.run_cli("verifier-calibrate", "--key-out", str(outside)).returncode, 0)
        self.assertIn("已存在", self.run_cli("verifier-calibrate", "--key-out", str(outside)).stderr)
        self.assertIn("--pack", self.run_cli("verifier-calibrate", "--answers", str(outside)).stderr)


if __name__ == "__main__":
    unittest.main()
