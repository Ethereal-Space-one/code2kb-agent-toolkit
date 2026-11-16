"""Strict authored UI contracts, local identities and per-fact impact seams."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

import test_knowledge as fixture
from validation import ui_model


MODULE = "example.order.query"
ENTRIES = [("ENT-001", "按钮", "查询", MODULE, "frontend:dummy.txt:1", "已归类"),
           ("ENT-002", "页面", "结果", MODULE, "frontend:dummy.txt:1", "已归类"),
           ("ENT-003", "页面", "其他", "other.module", "frontend:dummy.txt:1", "已归类")]
FACTS = {"FACT-001": "CODE_VERIFIED", "FACT-002": "RUN_VERIFIED", "FACT-003": "BUSINESS_CONFIRMED",
         "FACT-004": "UNKNOWN", "FACT-005": "INFERRED"}


def contract():
    return {"schema_version": ui_model.SCHEMA, "controls": [{
        "control_id": "UI-query", "entry_id": "ENT-001", "scope": "当前订单行", "role": "button", "label": "查询",
        "states": [
            {"state_id": "ready", "when": "valid && !busy", "presentation": {"visible": True, "enabled": True, "busy": False},
             "meaning": "可以发起查询，不代表服务端已接受", "fact_ids": ["FACT-001"]},
            {"state_id": "waiting", "when": "busy", "presentation": {"visible": True, "enabled": False, "busy": True,
                                                                          "label": "查询中", "feedback": "等待回应"},
             "meaning": "仅表示客户端正在等待", "fact_ids": ["FACT-001"]}],
        "transitions": [{"transition_id": "query", "from": "ready", "trigger": "点击", "guard": "valid && !busy",
                         "to": "waiting", "effect": {"kind": "stay", "target": "当前查询区域"},
                         "feedback": "显示等待反馈", "fact_ids": ["FACT-002"]}]}]}


def document(data):
    return SimpleNamespace(body=ui_model.HEADING + "\n\n```json\n" + json.dumps(data, ensure_ascii=False) + "\n```\n",
                           module_id=MODULE, relative=Path("订单/订单查询/结构化规格.md"))


class UIModelTests(unittest.TestCase):
    def validate(self, data, **kwargs):
        ui_model.validate(data, module_id=MODULE, entries=ENTRIES, fact_levels=FACTS,
                          standard_version=kwargs.get("standard_version", "c2kb-file/1"))

    def test_valid_block_roundtrips_and_dimensions_are_independent(self):
        data = contract()
        state = data["controls"][0]["states"][0]
        state["when"] = "mayView || mayEdit"
        state["presentation"] = {"visible": False, "enabled": True, "busy": "not_applicable"}
        self.validate(data)
        self.assertEqual(ui_model.parse_spec(document(data)), data)
        state["presentation"]["busy"] = "unknown"
        self.validate(data)

    def test_absent_and_example_headings_do_not_enable_extension(self):
        for body in ("# Plain spec", "```markdown\n## 界面交互规格\n```", "~~~~md\n## 界面交互规格\n~~~~"):
            spec = SimpleNamespace(body=body)
            self.assertIsNone(ui_model.parse_spec(spec))
            self.assertIsNone(ui_model.analyze_spec(spec, None, None, None))

    def test_malformed_duplicate_or_non_json_blocks_fail(self):
        valid = document(contract()).body
        for body in (valid + valid, valid.replace("```json", "```"), valid[:-4],
                     valid + "\n```json\n{}\n```", valid.replace("## 界面交互规格", "## 界面交互规格 extra"),
                     valid.replace('"controls":', '"controls": [], "controls":'),
                     valid.replace('"visible": true', '"visible": NaN'),
                     valid.replace('"c2kb-ui/0.1"', '"c2kb-ui/9"'),
                     "## 界面交互规格\n\n解释但没有 JSON"):
            with self.subTest(body=body[:100]), self.assertRaises(ui_model.UIError):
                ui_model.parse_spec(SimpleNamespace(body=body))

    def test_every_nested_object_is_strict_and_safe_on_bad_types(self):
        for change in (
            lambda d: d.update(extra=True), lambda d: d.update(controls={}),
            lambda d: d["controls"].append(None),
            lambda d: d["controls"][0].update(control_id=[]),
            lambda d: d["controls"][0].update(entry_id={}),
            lambda d: d["controls"][0].update(scope=None),
            lambda d: d["controls"][0].update(label="查询\n## Hidden heading"),
            lambda d: d["controls"][0].update(states=[]),
            lambda d: d["controls"][0]["states"][0].update(extra=True),
            lambda d: d["controls"][0]["states"][0].update(state_id=[]),
            lambda d: d["controls"][0]["states"][0].update(fact_ids=[{}]),
            lambda d: d["controls"][0]["states"][0].update(presentation=[]),
            lambda d: d["controls"][0]["states"][0]["presentation"].update(enabled=1),
            lambda d: d["controls"][0]["states"][0]["presentation"].update(busy=[]),
            lambda d: d["controls"][0]["states"][0]["presentation"].pop("visible"),
            lambda d: d["controls"][0]["states"][0]["presentation"].update(extra=False),
            lambda d: d["controls"][0].update(transitions={}),
            lambda d: d["controls"][0]["transitions"].append(None),
            lambda d: d["controls"][0]["transitions"][0].update(effect=[]),
            lambda d: d["controls"][0]["transitions"][0]["effect"].update(kind=[]),
            lambda d: d["controls"][0]["transitions"][0].update(guard=False),
            lambda d: d["controls"][0]["transitions"][0].update(feedback="ok\r\nheading"),
        ):
            data = contract()
            change(data)
            with self.subTest(data=data), self.assertRaises(ui_model.UIError):
                self.validate(data)

    def test_control_entries_and_navigation_must_belong_to_module(self):
        for entry_id in ("ENT-003", "ENT-missing"):
            data = contract()
            data["controls"][0]["entry_id"] = entry_id
            with self.assertRaises(ui_model.UIError):
                self.validate(data)
        data = contract()
        effect = data["controls"][0]["transitions"][0]["effect"]
        effect.update(kind="navigate", target="ENT-002")
        self.validate(data)
        for target in ("ENT-003", "ENT-missing", "https://example.invalid", []):
            effect["target"] = target
            with self.subTest(target=target), self.assertRaises(ui_model.UIError):
                self.validate(data)

    def test_verified_fact_references_do_not_upgrade_unknowns(self):
        for ids in ([], ["FACT-missing"], ["FACT-004"], ["FACT-005"], ["FACT-001", "FACT-001"]):
            data = contract()
            data["controls"][0]["states"][0]["fact_ids"] = ids
            with self.subTest(ids=ids), self.assertRaises(ui_model.UIError):
                self.validate(data)
        data = contract()
        data["controls"][0]["states"][0]["fact_ids"] = ["FACT-003"]
        data["controls"][0]["states"][0]["presentation"]["visible"] = "unknown"
        self.validate(data)

    def test_distinct_controls_share_entry_scope_label_and_local_state_ids(self):
        data = contract()
        second = deepcopy(data["controls"][0])
        second.update(control_id="UI-another")
        data["controls"].append(second)
        self.validate(data)
        second.update(label="取消", role="cancel button")
        self.validate(data)
        second["control_id"] = data["controls"][0]["control_id"]
        with self.assertRaises(ui_model.UIError):
            self.validate(data)

    def test_duplicates_and_cross_control_state_references_fail(self):
        for change in (
            lambda c: c["states"].append(deepcopy(c["states"][0])),
            lambda c: c["transitions"].append(deepcopy(c["transitions"][0])),
            lambda c: c["transitions"][0].update(to="missing"),
            lambda c: c["transitions"][0].update(**{"from": "missing"}),
        ):
            data = contract()
            change(data["controls"][0])
            with self.assertRaises(ui_model.UIError):
                self.validate(data)
        data = contract()
        data["controls"].append(deepcopy(data["controls"][0]))
        with self.assertRaises(ui_model.UIError):
            self.validate(data)

    def test_semantic_effects_and_unknowns_do_not_require_an_api(self):
        data = contract()
        effect = data["controls"][0]["transitions"][0]["effect"]
        for kind in ui_model.EFFECTS - {"navigate"}:
            effect.update(kind=kind, target="订单详情面板")
            self.validate(data)
        for target in ("src/Order.vue", "Order.vue", "openPanel()", "https://example.invalid", "API-001", "ENT-002", "x => y"):
            effect["target"] = target
            with self.subTest(target=target), self.assertRaises(ui_model.UIError):
                self.validate(data)
        data = contract()
        data["controls"][0]["transitions"] = []
        self.validate(data)

    def test_older_file_standard_is_rejected_only_when_enabled(self):
        with self.assertRaisesRegex(ui_model.UIError, "c2kb-file/1"):
            self.validate(contract(), standard_version="0.8.3")

    def test_dependencies_are_per_fact_and_canonical_without_mutation(self):
        data = contract()
        original = deepcopy(data)
        baseline = ui_model.fact_dependencies(data, entries=ENTRIES)
        data["controls"][0]["states"].reverse()
        self.assertEqual(baseline, ui_model.fact_dependencies(data, entries=ENTRIES))
        self.assertEqual(original, contract())
        self.assertNotIn("FACT-003", baseline)
        data["controls"][0]["transitions"][0]["guard"] = "valid && !busy && selected"
        changed = ui_model.fact_dependencies(data, entries=ENTRIES)
        self.assertEqual(baseline["FACT-001"], changed["FACT-001"])
        self.assertNotEqual(baseline["FACT-002"], changed["FACT-002"])
        data["controls"][0]["states"][0]["meaning"] = "等待不代表实际完成"
        self.assertNotEqual(changed["FACT-002"], ui_model.fact_dependencies(data, entries=ENTRIES)["FACT-002"])

    def test_navigation_target_dependencies_are_local_to_referencing_facts(self):
        data = contract()
        data["controls"][0]["transitions"][0]["effect"] = {"kind": "navigate", "target": "ENT-002"}
        original = deepcopy(data)
        baseline = ui_model.fact_dependencies(data, entries=ENTRIES)
        renamed = list(ENTRIES)
        renamed[1] = (*renamed[1][:2], "审批结果", *renamed[1][3:])
        changed = ui_model.fact_dependencies(data, entries=renamed)
        self.assertEqual(baseline["FACT-001"], changed["FACT-001"])
        self.assertNotEqual(baseline["FACT-002"], changed["FACT-002"])
        renamed[2] = (*renamed[2][:2], "其他模块的新名称", *renamed[2][3:])
        self.assertEqual(changed, ui_model.fact_dependencies(data, entries=renamed))
        self.assertEqual(changed, ui_model.fact_dependencies(data, entries=list(reversed(renamed))))
        self.assertEqual(data, original)
        with self.assertRaises(ui_model.UIError):
            ui_model.fact_dependencies(data, entries=ENTRIES[:1])

    def test_navigation_name_change_invalidates_claims_and_foreign_consumers(self):
        table = "## 入口与调用链\n\n" + ui_model.FACT_HEADER + "\n| --- | --- | --- | --- | --- |\n"
        table += "\n".join(f"| FACT-00{i} | 用户可查询 | CODE_VERIFIED | frontend:dummy.txt:1 | 功能与范围.md |" for i in (1, 2, 3))
        spec = SimpleNamespace(body=table, module_id=MODULE, doc_type="spec", relative=Path("订单/订单查询/结构化规格.md"),
                               meta={"source_revisions": "frontend=fixed"})
        outline = SimpleNamespace(entries=list(ENTRIES))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            governance = fixture.core.Governance(root, root, {"standard_version": "c2kb-file/1"}, [spec], outline, fixture.core)
            def mapping(fact_id):
                return {"data": {"links": [{"from_type": "fact", "to_type": "topic", "from_id": MODULE + "#" + fact_id}]}}
            governance.relations = {"consumer.navigation": mapping("FACT-002"), "consumer.state": mapping("FACT-001"),
                                    "consumer.unrelated": mapping("FACT-003")}
            plain_claims = governance.expected_claims(spec)
            plain_foreign = governance.cross_module_fact_digest("consumer.navigation")
            data = contract()
            data["controls"][0]["transitions"][0]["effect"] = {"kind": "navigate", "target": "ENT-002"}
            spec.body = table + "\n\n" + document(data).body
            claims = governance.expected_claims(spec)
            foreign = {owner: governance.cross_module_fact_digest(owner) for owner in governance.relations}
            old_render = fixture.core.fact_render.render_ui(spec, data, fixture.core, {"ENT-002": "结果"})
            outline.entries[1] = (*outline.entries[1][:2], "审批结果", *outline.entries[1][3:])
            changed = governance.expected_claims(spec)
            self.assertEqual({key for key in claims if claims[key] != changed[key]}, {("FACT-002", "功能与范围.md")})
            self.assertNotEqual(old_render, fixture.core.fact_render.render_ui(spec, data, fixture.core, {"ENT-002": "审批结果"}))
            self.assertNotEqual(foreign["consumer.navigation"], governance.cross_module_fact_digest("consumer.navigation"))
            for owner in ("consumer.state", "consumer.unrelated"):
                self.assertEqual(foreign[owner], governance.cross_module_fact_digest(owner))
            spec.body = table
            self.assertEqual(plain_claims, governance.expected_claims(spec))
            self.assertEqual(plain_foreign, governance.cross_module_fact_digest("consumer.navigation"))

    def test_rendering_does_not_infer_activation_or_opening_from_presentation_and_external(self):
        data = contract()
        data["controls"][0]["states"][0]["presentation"].update(visible=False, enabled=True)
        data["controls"][0]["transitions"][0]["effect"] = {"kind": "external", "target": "第三方账户验证"}
        self.validate(data)
        table = "## 入口与调用链\n\n" + ui_model.FACT_HEADER + "\n| --- | --- | --- | --- | --- |\n"
        table += "\n".join(f"| FACT-00{i} | 用户可查询 | CODE_VERIFIED | frontend:dummy.txt:1 | 功能与范围.md |" for i in (1, 2))
        spec = SimpleNamespace(body=table)
        for language, neutral, unsupported, visibility, enabled, activation in (
            ("zh-CN", "外部交互", "打开外部目标", "显示：否", "已启用：是", "可触发"),
            ("en", "External interaction", "Open external destination", "Visible：no", "Enabled：yes", "Can activate"),
        ):
            rendered = fixture.core.fact_render.render_ui(spec, data, fixture.core, {}, language=language)[0]
            for audience in ("business", "engineering"):
                self.assertIn(neutral, rendered[audience])
                self.assertNotIn(unsupported, rendered[audience])
                self.assertIn(visibility, rendered[audience])
                self.assertIn(enabled, rendered[audience])
                self.assertNotIn(activation, rendered[audience])

    def test_foreign_ui_dependencies_change_only_referenced_fact_digest(self):
        table = "## 入口与调用链\n\n" + ui_model.FACT_HEADER + "\n| --- | --- | --- | --- | --- |\n"
        table += "\n".join(f"| FACT-00{i} | 用户可查询 | CODE_VERIFIED | frontend:dummy.txt:1 | 功能与范围.md |" for i in (1, 2, 3))
        spec = SimpleNamespace(body=table, module_id=MODULE, doc_type="spec", relative=Path("订单/订单查询/结构化规格.md"),
                               meta={"source_revisions": "frontend=fixed"})
        outline = SimpleNamespace(entries=ENTRIES)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            governance = fixture.core.Governance(root, root, {"standard_version": "c2kb-file/1"}, [spec], outline, fixture.core)
            def mapping(fact_id):
                return {"data": {"links": [{"from_type": "fact", "to_type": "topic", "from_id": MODULE + "#" + fact_id}]}}
            governance.relations = {"consumer.linked": mapping("FACT-001"), "consumer.unrelated": mapping("FACT-003")}
            old = governance.cross_module_fact_digest("consumer.linked")
            row = fixture.core.table_rows(spec.body, "## 入口与调用链", ui_model.FACT_HEADER)[0]
            legacy_input = [[MODULE + "#FACT-001", row, None, "frontend=fixed"]]
            self.assertEqual(old, fixture.core.digest(json.dumps(legacy_input, ensure_ascii=False, separators=(",", ":"), sort_keys=True)))
            unrelated = governance.cross_module_fact_digest("consumer.unrelated")
            data = contract()
            spec.body = table + "\n\n" + document(data).body
            with_ui = governance.cross_module_fact_digest("consumer.linked")
            self.assertNotEqual(old, with_ui)
            self.assertEqual(unrelated, governance.cross_module_fact_digest("consumer.unrelated"))
            data["controls"][0]["states"][0]["when"] = "valid && !busy && permission"
            spec.body = table + "\n\n" + document(data).body
            self.assertNotEqual(with_ui, governance.cross_module_fact_digest("consumer.linked"))
            self.assertEqual(unrelated, governance.cross_module_fact_digest("consumer.unrelated"))


class UIIntegrationTests(unittest.TestCase):
    setUp = fixture.KnowledgeTests.setUp
    run_cli = fixture.KnowledgeTests.run_cli

    def add_ui(self, data):
        path = self.module / "结构化规格.md"
        body = path.read_text(encoding="utf-8")
        if ui_model.HEADING in body:
            body = body.split(ui_model.HEADING, 1)[0]
        fixture.write(path, body + "\n" + document(data).body)

    def ui(self):
        data = contract()
        data["controls"][0]["transitions"][0]["fact_ids"] = ["FACT-001"]
        return data

    def test_preflight_and_check_use_same_validator_without_mutation(self):
        data = self.ui()
        data["controls"][0]["states"][0]["presentation"].pop("enabled")
        self.add_ui(data)
        path = self.module / "结构化规格.md"
        before = path.read_bytes()
        for action, args in (("check", ()), ("preflight", ("--module-id", MODULE))):
            result = self.run_cli(action, *args)
            self.assertNotEqual(result.returncode, 0, result.stderr)
            self.assertIn("visible/enabled/busy", result.stderr)
        self.assertEqual(before, path.read_bytes())

    def test_ui_guard_change_enqueues_claim_impact_and_old_plain_digest_is_unchanged(self):
        source, config = fixture.core.read_config(self.project)
        docs, outline = fixture.core.read_documents(source)
        governance = fixture.core.Governance(self.project, source, config, docs, outline, fixture.core)
        spec = governance.spec(MODULE)
        baseline = governance.expected_claims(spec)
        row = fixture.core.table_rows(spec.body, "## 入口与调用链", ui_model.FACT_HEADER)[0]
        old_hash = fixture.core.digest(json.dumps(row, ensure_ascii=False, separators=(",", ":"), sort_keys=True))
        self.assertEqual(next(iter(baseline.values()))[2], old_hash)
        data = self.ui()
        self.add_ui(data)
        result = self.run_cli("impact", "--module-id", MODULE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["pending_impacts"])
        self.assertEqual(self.run_cli("confirm-claims", "--module-id", MODULE).returncode, 0)
        result = self.run_cli("impact", "--module-id", MODULE)
        self.assertEqual(json.loads(result.stdout)["pending_impacts"], [])
        data["controls"][0]["transitions"][0]["guard"] = "valid && !busy && selected"
        self.add_ui(data)
        result = self.run_cli("impact", "--module-id", MODULE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({item["fact_id"] for item in json.loads(result.stdout)["pending_impacts"]}, {"FACT-001"})


if __name__ == "__main__":
    unittest.main()
