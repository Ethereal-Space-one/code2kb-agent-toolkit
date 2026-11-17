"""CI-only regression checks; no workflow dispatches or external writes."""

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / ".github/scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = load("ci_gate")
smoke = load("smoke_installed_cli")


class CIGateTest(unittest.TestCase):
    def successful(self):
        return {job: {"result": "success"} for job in gate.REQUIRED_JOBS}

    def test_every_required_job_must_succeed(self):
        self.assertEqual(gate.failures(self.successful()), [])
        for job in gate.REQUIRED_JOBS:
            for result in ("failure", "cancelled", "skipped", "pending", "", None):
                with self.subTest(job=job, result=result):
                    needs = self.successful()
                    needs[job] = {"result": result}
                    self.assertTrue(gate.failures(needs))

    def test_missing_malformed_and_unexpected_results_fail(self):
        for value in (None, [], "success", {}, {"test": "success"}):
            self.assertTrue(gate.failures(value))
        for job in gate.REQUIRED_JOBS:
            needs = self.successful()
            del needs[job]
            self.assertTrue(gate.failures(needs))
        needs = self.successful()
        needs["unexpected"] = {"result": "success"}
        self.assertTrue(gate.failures(needs))

    def test_command_fails_closed_on_missing_or_invalid_json(self):
        environment = os.environ.copy()
        for value in (None, "not json", json.dumps(self.successful())):
            if value is None:
                environment.pop("CI_NEEDS_JSON", None)
            else:
                environment["CI_NEEDS_JSON"] = value
            result = subprocess.run([sys.executable, "-B", str(ROOT / ".github/scripts/ci_gate.py")],
                                    env=environment, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0 if value == json.dumps(self.successful()) else 1)

    def test_workflow_waits_for_the_same_dependencies(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("needs: [" + ", ".join(gate.REQUIRED_JOBS) + "]", workflow)
        self.assertIn("if: ${{ always() }}", workflow)


class InstalledSmokeTest(unittest.TestCase):
    def test_requires_the_real_completed_cli_envelope(self):
        response = {"response_schema_version": "0.1", "command": "run-create", "status": "completed",
                    "error_code": None, "result": {"run_id": "ci-smoke"}}
        smoke.require_completed(response, "run-create")
        for key, value in (("status", "ok"), ("status", "failed"), ("command", "publish"),
                           ("error_code", "E_IO"), ("result", None), ("result", {"run_id": "other"})):
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                smoke.require_completed(dict(response, **{key: value}), "run-create")

    def test_rejects_source_imports_including_symlink_aliases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkout = root / "checkout"
            checkout.mkdir()
            source = checkout / "validation.py"
            source.touch()
            alias = root / "alias"
            alias.symlink_to(checkout, target_is_directory=True)
            for path in (source, alias / "validation.py"):
                with self.assertRaises(RuntimeError):
                    smoke.require_installed(path, checkout)
            smoke.require_installed(root / "venv/site-packages/validation.py", checkout)


if __name__ == "__main__":
    unittest.main()
