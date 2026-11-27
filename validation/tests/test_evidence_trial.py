import copy
import unittest
from validation import evidence_trial as trial


class EvidenceTrialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack, cls.key = trial.generate(12)
        cls.answers = {"pack_sha256": trial.digest(cls.pack), "reviewer": "scorer-test-oracle-not-a-reviewer",
                       "items": [dict(case_id=i, verdict=t["verdict"], evidence_ids=t["evidence_ids"])
                                 for i,t in cls.key["labels"].items()]}

    def test_clean_packet_and_full_coverage(self):
        self.assertNotIn("labels", self.pack)
        self.assertNotIn("seed", self.pack)
        self.assertEqual(len({c["case_id"] for c in self.pack["cases"]}), 10)
        self.assertTrue(all(set(c) == {"case_id","claim","target_commit","snippets"} for c in self.pack["cases"]))
        report = trial.score(self.pack, self.key, self.answers)
        self.assertEqual(report["correct"], 10)
        self.assertEqual(set(report["by_category"]), {"clean","contradiction","wrong_commit","wrong_evidence","no_evidence"})
        self.assertTrue(all(v["total"] == 2 for v in report["by_category"].values()))

    def test_universal_refusal_and_wrong_citation_do_not_pass(self):
        answers = copy.deepcopy(self.answers)
        for i in answers["items"]: i.update(verdict="insufficient", evidence_ids=[])
        self.assertEqual(trial.score(self.pack, self.key, answers)["correct"], 6)
        answers = copy.deepcopy(self.answers)
        positive = next(i for i in answers["items"] if i["verdict"] == "supported")
        positive["evidence_ids"] = []
        self.assertEqual(trial.score(self.pack, self.key, answers)["correct"], 9)

    def test_extraction_scores_values_and_requires_correct_revision_citations(self):
        pack, key = trial.generate(44, "extract")
        self.assertTrue(all("question" in c and "claim" not in c for c in pack["cases"]))
        answers = dict(pack_sha256=trial.digest(pack),reviewer="test-oracle",items=[
            dict(case_id=k,value=v["value"],evidence_ids=v["evidence_ids"]) for k,v in key["labels"].items()])
        self.assertEqual(trial.score(pack,key,answers)["correct"], 10)
        for item in answers["items"]:
            if item["value"] is not None: item["value"] += 1
        self.assertEqual(trial.score(pack,key,answers)["correct"], 6)
        next(a for a in answers["items"] if a["value"] is not None)["value"] = True
        with self.assertRaises(ValueError): trial.score(pack,key,answers)

    def test_stale_or_tampered_labels_and_duplicate_response_rejected(self):
        changed = copy.deepcopy(self.key)
        next(iter(changed["labels"].values()))["verdict"] = "junk"
        with self.assertRaises(ValueError): trial.score(self.pack, changed, self.answers)
        for change in ("stale", "missing", "duplicate"):
            answers = copy.deepcopy(self.answers)
            if change == "stale": answers["pack_sha256"] = "0"*64
            elif change == "missing": answers["items"].pop()
            else: answers["items"].append(answers["items"][0])
            with self.subTest(change=change), self.assertRaises(ValueError):
                trial.score(self.pack, self.key, answers)
