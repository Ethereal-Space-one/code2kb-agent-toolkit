from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from validation.adapters.ts_java import scan
from validation.adapters.platform import scan as scan_platform
from validation.adapters.sdk import validate_result


class CandidateAdapterTests(unittest.TestCase):
    def test_platform_reports_levels_and_never_verifies_route_bridge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "api.ts").write_text("const request = { url: '/orders' };\nconst dynamic = { url: routeFromServer };\n", encoding="utf-8")
            (repo / "Order.java").write_text("@GetMapping(\"/orders\")\npublic Order getOrder() { return null; }\n", encoding="utf-8")
            (repo / "tool.sh").write_text("echo ready\n", encoding="utf-8")
            (repo / "ignored.sql").write_text("select 1;\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture"], check=True)
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            settings = {"path": str(repo), "commit": commit}
            first = scan_platform("source", settings)
            self.assertEqual(first["schema_version"], "0.2")
            self.assertTrue(any(item["language"] == "shell" and item["capability"] == "L1" for item in first["candidates"]))
            self.assertTrue(all(edge["status"] == "candidate" and len(edge["evidence"]) == 2 for edge in first["edges"]))
            self.assertEqual(len(first["edges"]), 1)
            self.assertTrue(any(item["status"] == "unresolved" for item in first["candidates"]))
            (repo / "api.ts").write_text("const changed = { url: '/other' };\n", encoding="utf-8")
            self.assertEqual(first, scan_platform("source", settings))
            scoped = scan_platform("source", settings, scope="tool.sh")
            self.assertEqual({item["source_path"] for item in scoped["candidates"]}, {"tool.sh"})
            self.assertEqual(scoped["edges"], [])
            with patch("validation.adapters.platform.MAX_FILES", 1), patch("validation.adapters.ts_java.MAX_FILES", 1):
                self.assertEqual({item["source_path"] for item in scan_platform("source", settings, scope="tool.sh")["candidates"]}, {"tool.sh"})
            with self.assertRaisesRegex(ValueError, "扫描范围"):
                scan_platform("source", settings, scope="../tool.sh")
            fallback = scan_platform("source", settings, adapter_name="universal-l1")
            self.assertEqual(fallback["adapter"]["name"], "universal-l1")
            self.assertEqual({item["kind"] for item in fallback["candidates"]}, {"source_file"})
            invalid = dict(first)
            invalid["candidates"] = [dict(item) for item in first["candidates"]]
            invalid["candidates"][0]["status"] = "verified"
            with self.assertRaisesRegex(ValueError, "状态无效"):
                validate_result(invalid)
            invalid_edge = dict(first)
            invalid_edge["edges"] = [dict(first["edges"][0], evidence=["wrong:anchor:1", first["edges"][0]["evidence"][1]])]
            with self.assertRaisesRegex(ValueError, "桥接关系"):
                validate_result(invalid_edge)

    def test_fixed_commit_candidates_and_unresolved_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo = Path(temporary)
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
            (repo / "pages.json").write_text(json.dumps({"pages": [{"path": "pages/home"}]}, ensure_ascii=False), encoding="utf-8")
            (repo / "api.ts").write_text("const request = { url: '/orders' };\nconst dynamic = { url: routeFromServer };\nconst template = { url: `/orders/${id}` };\n", encoding="utf-8")
            (repo / "Order.java").write_text("@GetMapping(\"/orders\")\npublic Order getOrder() { return null; }\n@RequestMapping(path = routeFromConfig)\n@PostMapping(\"/orders/\" + suffix)\n", encoding="utf-8")
            subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
            subprocess.run(["git", "-C", str(repo), "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture"], check=True)
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            settings = {"path": str(repo), "commit": commit}
            first = scan("source", settings, uniapp_manifest="pages.json")
            self.assertEqual(first["capability"], "deterministic_candidates_only")
            self.assertEqual(first["unresolved"], 4)
            self.assertEqual({item["kind"] for item in first["candidates"]}, {"typescript_path", "typescript_dynamic_path", "java_route", "java_method", "uniapp_route"})
            self.assertEqual(sum(item["expression"] == "/orders" for item in first["candidates"]), 2)
            (repo / "api.ts").write_text("const request = { url: '/changed' };\n", encoding="utf-8")
            self.assertEqual(first, scan("source", settings, uniapp_manifest="pages.json"))


class ScopedInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.repo = self.root / "source"
        self.repo.mkdir()
        self.git("init", "-q")
        files = {
            "src/main.rs": b"fn main() {}\n",
            "vendor/internal/engine.ex": b"defmodule Engine do\nend\n",
            "vendor/internal/Dockerfile": b"FROM scratch\n",
            "vendor/internal/api.ts": b"const request = { url: '/status' };\n",
            "vendor/internal/Endpoint.java": b'@GetMapping("/status")\n',
            "vendor/internal/node_modules/dependency.js": b"export default 1;\n",
            "vendor/internal/build/generated.rs": b"fn generated() {}\n",
            "vendor/internalized/outside.py": b"value = 1\n",
            "vendor/other.py": b"value = 2\n",
            "vendor/internal/empty.txt": b"",
            "vendor/internal/binary.bin": b"\x00payload",
            "vendor/internal/non_utf8.txt": b"\xff\xfe",
        }
        for name, body in files.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        (self.repo / "vendor/internal/link.rs").symlink_to("../../../../outside.rs")
        self.git("add", ".")
        self.commit()
        first = self.git("rev-parse", "HEAD")
        self.git("update-index", "--add", "--cacheinfo", f"160000,{first},vendor/internal/external")
        self.commit()
        self.settings = {"path": str(self.repo), "commit": self.git("rev-parse", "HEAD")}

    def git(self, *args: str) -> str:
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True).strip()

    def commit(self) -> None:
        self.git("-c", "user.name=Example", "-c", "user.email=example@example.invalid", "commit", "-qm", "public scope fixture")

    def test_explicit_scope_includes_owned_source_and_keeps_nested_filters(self) -> None:
        for adapter in ("universal-l1", "builtin-mixed"):
            with self.subTest(adapter=adapter):
                whole = scan_platform("source", self.settings, adapter_name=adapter)
                self.assertEqual({c["source_path"] for c in whole["candidates"]}, {"src/main.rs"})
                selected = scan_platform("source", self.settings, scope="vendor/internal", adapter_name=adapter)
                sources = {c["source_path"]: c for c in selected["candidates"] if c["kind"] == "source_file"}
                self.assertEqual(set(sources), {"vendor/internal/engine.ex", "vendor/internal/Dockerfile", "vendor/internal/api.ts", "vendor/internal/Endpoint.java"})
                self.assertEqual(sources["vendor/internal/engine.ex"]["language"], "unknown")
                self.assertEqual(sources["vendor/internal/Dockerfile"]["capability"], "L1")
                self.assertEqual(selected["coverage"]["skipped"], {"generated_or_dependency": 2, "non_regular": 2, "empty_or_large": 1, "binary": 1, "non_utf8": 1})
                narrowed = scan_platform("source", self.settings, scope="vendor/internal/engine.ex", adapter_name=adapter)
                self.assertEqual(narrowed["candidates"], [sources["vendor/internal/engine.ex"]])
                dependency = scan_platform("source", self.settings, scope="vendor/internal/node_modules/dependency.js", adapter_name=adapter)
                self.assertEqual({c["source_path"] for c in dependency["candidates"]}, {"vendor/internal/node_modules/dependency.js"})
                (self.repo / "vendor/internal/engine.ex").write_text("changed worktree\n", encoding="utf-8")
                self.assertEqual(selected, scan_platform("source", self.settings, scope="vendor/internal", adapter_name=adapter))

    def test_explicit_scope_does_not_relax_path_or_resource_limits(self) -> None:
        for scope in ("../source", "/vendor/internal", "vendor//internal", "vendor/./internal", "vendor\\internal"):
            with self.subTest(scope=scope), self.assertRaisesRegex(ValueError, "扫描范围"):
                scan_platform("source", self.settings, scope=scope)
        for adapter in ("universal-l1", "builtin-mixed"):
            with self.subTest(adapter=adapter):
                with patch("validation.adapters.platform.MAX_FILES", 1), patch("validation.adapters.ts_java.MAX_FILES", 1):
                    with self.assertRaisesRegex(ValueError, "扫描上限"):
                        scan_platform("source", self.settings, scope="vendor/internal", adapter_name=adapter)
                    self.assertEqual(len(scan_platform("source", self.settings, scope="vendor/internal/engine.ex", adapter_name=adapter)["candidates"]), 1)
                with patch("validation.adapters.platform.MAX_BYTES", 1):
                    result = scan_platform("source", self.settings, scope="vendor/internal/engine.ex", adapter_name=adapter)
                    self.assertEqual(result["candidates"], [])
                    self.assertEqual(result["coverage"]["skipped"], {"empty_or_large": 1})

    def test_cli_scoped_candidate_output_remains_schema_02(self) -> None:
        project = self.root / "knowledge"
        (project / "知识源").mkdir(parents=True)
        (project / "知识库配置.json").write_text(json.dumps({
            "standard_version": "c2kb-file/1", "knowledge_source_root": "知识源",
            "coverage_terms": ["文件"], "repositories": {"source": self.settings},
        }), encoding="utf-8")
        script = Path(__file__).resolve().parents[1] / "knowledge.py"
        result = subprocess.run([sys.executable, "-B", str(script), "analyze-candidates", "--project-root", str(project),
                                 "--repository-id", "source", "--candidate-schema", "0.2", "--adapter", "universal-l1",
                                 "--scope", "vendor/internal/engine.ex"], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["schema_version"], "0.2")
        self.assertEqual(report["snapshot"]["scope"], "vendor/internal/engine.ex")
        self.assertEqual(report["candidates"][0]["source_path"], "vendor/internal/engine.ex")


if __name__ == "__main__":
    unittest.main()
