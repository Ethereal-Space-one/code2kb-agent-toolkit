"""A synthetic review oracle, not an analyzer or a score for an answer model."""

import hashlib
from itertools import product
from pathlib import Path
import runpy
import unittest


CASE = Path(__file__).resolve().parents[2] / "conformance/rule-precedence"
SOURCE = CASE / "sources/returns.py"
BOOLEANS = {"否": False, "是": True}
DESTINATIONS = {"开架书架": "open-shelf", "预约柜": "hold-shelf", "修补台": "repair"}
NOTES = {"无": (), "预约待核对": ("check-hold",)}


class RulePrecedenceTests(unittest.TestCase):
    def reader_answers(self):
        """Decode only the four cells per row in this fixture's reader-facing table."""
        rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in (CASE / "knowledge.md").read_text(encoding="utf-8").splitlines()
            if line.startswith("|")
        ]
        self.assertEqual(rows[:2], [
            ["有预约", "需修补", "建议去向", "随单备注"],
            ["---", "---", "---", "---"],
        ])
        out = {}
        for has_hold, needs_repair, destination, notes in rows[2:]:
            key = (BOOLEANS[has_hold], BOOLEANS[needs_repair])
            self.assertNotIn(key, out)
            out[key] = (DESTINATIONS[destination], NOTES[notes])
        self.assertEqual(set(out), set(product((False, True), repeat=2)))
        return out

    def test_reader_pairs_each_condition_with_route_and_note(self):
        # A changed source needs a fresh review; running this isolated pure fixture
        # is not an instruction to execute arbitrary repositories during extraction.
        self.assertEqual(hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                         "c274639dddbccfffe19f8df579dba7ac4789a05e055e5c16e7045301e591f036")
        plan_return = runpy.run_path(str(SOURCE))["plan_return"]
        for (reserved, damaged), expected in self.reader_answers().items():
            with self.subTest(reserved=reserved, damaged=damaged):
                self.assertEqual(plan_return(reserved=reserved, damaged=damaged), expected)

    def test_overlap_distinguishes_two_otherwise_matching_readings(self):
        # Two plausible but wrong transcriptions, not model-generated answers.
        def hold_always_wins(reserved, damaged):
            if reserved:
                return "hold-shelf", ("check-hold",)
            return ("repair" if damaged else "open-shelf"), ()

        def repair_drops_note(reserved, damaged):
            if damaged:
                return "repair", ()
            return ("hold-shelf", ("check-hold",)) if reserved else ("open-shelf", ())

        for reading in (hold_always_wins, repair_drops_note):
            with self.subTest(reading=reading.__name__):
                mismatches = {
                    pair for pair, expected in self.reader_answers().items()
                    if reading(*pair) != expected
                }
                self.assertEqual(mismatches, {(True, True)})


if __name__ == "__main__":
    unittest.main()
