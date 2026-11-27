import copy
import unittest
from unittest.mock import patch
from validation import review_queue as queue


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.preview = dict(changed_node_evidence=[], changed_evidence=[dict(
            module_id="a", from_type="method", from_id="M1", to_type="fact", to_id="F1",
            source_path="rules", line_start=2, line_end=4, status="verified", outcome="changed_excerpt")],
            changed_files=[{"path":"rules"}], old_commit="a"*40, proposed_commit="b"*40)
        def link(fr, fi, to, ti):
            return dict(from_type=fr,from_id=fi,to_type=to,to_id=ti,status="verified")
        self.relations = {"a":{"links":[link("method","M1","fact","F1"),link("fact","F1","topic","b#T1")]}}
        mods = [dict(module_id=m, source_revision_files=["spec"], review_reset_files=[], manifest_files=[],
                     relation_file=None, evidence_records_rebuildable=0, evidence_records_requiring_review=0)
                for m in ("a","b","c")]
        self.plan = dict(decision="selected_modules", selected_modules=["a","b"], fallback_reasons=[],
                         baseline_migration=dict(modules=mods,runtime_evidence_requiring_independent_review=[]),
                         must_review_facts=[dict(fact_id="a#F1",documents=["faq.md"])],
                         changed_paths=[dict(path="rules",modules=["a"])], affected_topics=["b#T1"], published_unit_ids=[],
                         needs_evidence=[], repository_id="repo", old_commit="a"*40, proposed_commit="b"*40, plan_sha256="0"*64)

    def make(self, raw):
        with patch.object(queue,"git",return_value=raw):
            return queue.build(self.plan,self.preview,self.relations,{"path":"fixture"}, getattr(self, "catalog", {}))

    def test_reaches_cross_module_without_inheriting_approval(self):
        q=self.make(b"@@ -2 +2 @@\n")
        a,b,c=q["modules"]
        self.assertEqual([i["work"] for i in (a,b,c)], ["review_module","review_module","baseline_only"])
        self.assertEqual(b["dependency_routes"][0]["dependency_route"],["method:a#M1","fact:a#F1","topic:b#T1"])
        self.assertEqual(a["facts"][0]["documents"],["faq.md"])
        self.assertEqual([p["rule_scope"] for p in (a,b,c)], ["named_rules_and_topics","consumer_topics","baseline_only"])
        self.assertFalse(q["mutates_project"])
        self.assertTrue(all(i["status"]=="not_reviewed" for i in (a,b,c)))
        self.assertEqual(q["queue_sha256"],self.make(b"@@ -2 +2 @@\n")["queue_sha256"])

    def test_other_hunk_in_same_file_insertion_mode_or_binary_force_global(self):
        for raw in (b"@@ -2 +2 @@\n@@ -8 +8 @@\n",b"@@ -2,0 +3 @@\n", b"@@ -2 +2,0 @@\n",
                    b"old mode 100644\nnew mode 100755\n@@ -2 +2 @@\n",b"Binary files f and g differ\n"):
            with self.subTest(raw=raw):
                result=self.make(raw)
                self.assertEqual(result["uncovered_diff_paths"],["rules"])
                self.assertEqual(result["disposition"],"full_project_review")
                self.assertTrue(all(m["work"]=="review_module" for m in result["modules"]))

    def test_changed_fact_without_verified_relation_cannot_be_silently_skipped(self):
        self.catalog = {"a": [dict(fact_id="F2",anchors="repo:rules:2-3")]}
        q = self.make(b"@@ -2 +2 @@\n")
        self.assertEqual(q["untraced_changed_facts"], ["a#F2"])
        self.assertEqual(q["disposition"], "full_project_review")
        self.assertTrue(all(p["rule_scope"] == "all_rules" for p in q["modules"]))

    def test_preexisting_global_fallback_never_becomes_selected(self):
        self.plan.update(decision="full_project_review",fallback_reasons=["unverified_relation"])
        result=self.make(b"@@ -2 +2 @@\n")
        self.assertEqual(result["fallback_reasons"],["unverified_relation"])
        self.assertEqual(result["disposition"],"full_project_review")
