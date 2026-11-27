"""A configured project can read pinned source before any knowledge is authored."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


CLI = Path(__file__).resolve().parents[1] / "knowledge.py"


class FirstSourceScanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.project = root / "knowledge"
        self.project.mkdir()
        self.repo = root / "source"
        self.git("init", "-q", str(self.repo), cwd=root)
        directory = self.repo / "checkout"
        directory.mkdir()
        self.data = b"export const canCollect = (paid: boolean) => paid;\n"
        (directory / "rule.ts").write_bytes(self.data)
        (directory / "empty.ts").touch()
        self.git("add", "checkout")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                 "-c", "commit.gpgsign=false", "commit", "-qm", "synthetic checkout")
        self.commit = self.git("rev-parse", "HEAD").strip()
        (directory / "working-copy-only.ts").write_bytes(self.data)
        self.config_file = self.project / "知识库配置.json"
        self.config = {
            "standard_version": "c2kb-file/1",
            "knowledge_source_root": "draft/知识源",
            "repositories": {"source": {"path": str(self.repo), "commit": self.commit}},
        }
        self.write_config()

    def git(self, *args, cwd=None):
        return subprocess.check_output(["git", *args], cwd=cwd or self.repo, text=True)

    def write_config(self):
        self.config_file.write_text(json.dumps(self.config, ensure_ascii=False), encoding="utf-8")

    def cli(self, action, *args):
        result = subprocess.run(
            [sys.executable, "-B", str(CLI), action, "--project-root", str(self.project),
             "--output", "json", *args],
            check=False, capture_output=True, text=True,
        )
        return result.returncode, json.loads(result.stdout)

    def scan(self, scope, adapter="universal-l1"):
        return self.cli("analyze-candidates", "--repository-id", "source",
                        "--candidate-schema", "0.2", "--adapter", adapter, "--scope", scope)

    def snapshot(self):
        return self.cli("evidence-snapshot", "--anchor", "source:checkout/rule.ts:1")

    def test_inventory_and_evidence_are_available_before_creating_an_outline(self):
        before = self.config_file.read_bytes()
        code, response = self.scan("checkout")
        self.assertEqual(code, 0, response)
        self.assertEqual(response["result"]["snapshot"]["commit"], self.commit)
        self.assertEqual([item["anchor"] for item in response["result"]["candidates"]],
                         ["source:checkout/rule.ts:1"])
        code, evidence = self.snapshot()
        self.assertEqual(code, 0, evidence)
        self.assertEqual(evidence["result"]["snippet_sha256"], hashlib.sha256(self.data).hexdigest())
        self.assertEqual([path.name for path in self.project.iterdir()], [self.config_file.name])
        self.assertEqual(self.config_file.read_bytes(), before)
        code, check = self.cli("check")
        self.assertNotEqual(code, 0)
        self.assertIn("知识源目录尚未创建", check["diagnostics"][0])
        (self.project / "draft/知识源").mkdir(parents=True)
        code, check = self.cli("check")
        self.assertNotEqual(code, 0)
        self.assertIn("大纲", check["diagnostics"][0])

    def test_missing_pinned_scope_is_not_a_successful_filtered_scan(self):
        for adapter in ("universal-l1", "builtin-mixed"):
            for scope in ("chekout", "checkout/working-copy-only.ts"):
                with self.subTest(adapter=adapter, scope=scope):
                    code, response = self.scan(scope, adapter)
                    self.assertNotEqual(code, 0)
                    self.assertEqual(response["status"], "failed")
                    self.assertEqual(response["response_schema_version"], "0.1")
                    self.assertIsNone(response["result"])
                    self.assertIn(self.commit, response["diagnostics"][0])
                    self.assertIn(scope, response["diagnostics"][0])
            code, response = self.scan("checkout/empty.ts", adapter)
            self.assertEqual(code, 0, response)
            self.assertEqual(response["result"]["coverage"], {"text_files": 0, "skipped": {"empty_or_large": 1}})

    def test_missing_knowledge_directory_does_not_relax_config_validation(self):
        for path, diagnostic in (("../elsewhere", "项目内相对路径"), ("知识库配置.json", "项目内的目录")):
            with self.subTest(path=path):
                self.config["knowledge_source_root"] = path
                self.write_config()
                for call in (lambda: self.scan("checkout"), self.snapshot):
                    code, response = call()
                    self.assertNotEqual(code, 0)
                    self.assertIn(diagnostic, response["diagnostics"][0])
        self.config["knowledge_source_root"] = "draft/知识源"
        self.config["repositories"]["source"]["commit"] = "0" * len(self.commit)
        self.write_config()
        for call in (lambda: self.scan("checkout"), self.snapshot):
            code, response = call()
            self.assertNotEqual(code, 0)
            self.assertIn("固定 commit 不存在", response["diagnostics"][0])

    def test_future_directory_path_must_not_pass_through_a_file(self):
        (self.project / "package.json").write_text("{}", encoding="utf-8")
        paths = ["package.json/child"]
        try:
            (self.project / "file-link").symlink_to("package.json")
        except (OSError, NotImplementedError):
            pass  # The ordinary-file case still runs where symlinks are unavailable.
        else:
            paths.append("file-link/child")
        for path in paths:
            self.config["knowledge_source_root"] = path
            self.write_config()
            for call in (lambda: self.scan("checkout"), self.snapshot, lambda: self.cli("check")):
                with self.subTest(path=path, call=call):
                    code, response = call()
                    self.assertNotEqual(code, 0)
                    self.assertIn("项目内的目录", response["diagnostics"][0])

    def test_future_directory_preserves_existing_symlink_boundary(self):
        (self.project / "retained").mkdir()
        try:
            (self.project / "inside-link").symlink_to("retained", target_is_directory=True)
            (self.project / "outside-link").symlink_to(self.repo, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are not available")
        for path, error in (("inside-link", "不能是符号链接"), ("outside-link/not-yet", "项目内的目录"),
                            ("inside-link/not-yet", None)):
            self.config["knowledge_source_root"] = path
            self.write_config()
            for call in (lambda: self.scan("checkout"), self.snapshot):
                with self.subTest(path=path, call=call):
                    code, response = call()
                    if error:
                        self.assertNotEqual(code, 0)
                        self.assertIn(error, response["diagnostics"][0])
                    else:
                        self.assertEqual(code, 0, response)
        self.assertNotEqual(self.cli("check")[0], 0)
        self.assertFalse((self.project / "retained/not-yet").exists())


if __name__ == "__main__":
    unittest.main()
