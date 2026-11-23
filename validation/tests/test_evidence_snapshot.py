from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
import tempfile
import unittest

from validation.evidence_snapshot import EvidenceError, snapshot, verify
from validation.pinned_source import PinnedReads
from validation.relation_upgrade_project import changed_paths


class EvidenceSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "source"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "main.java").write_text("class Example {\n  int count = 1;\n}\n", encoding="utf-8")
        self.commit()
        self.repositories = {"source": {"path": str(self.repo), "commit": self.head()}}

    def commit(self) -> None:
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run([
            "git", "-C", str(self.repo), "-c", "user.name=Fixture", "-c",
            "user.email=fixture@example.invalid", "commit", "-q", "-m", "fixture",
        ], check=True)

    def head(self) -> str:
        return subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()

    def test_fixed_commit_ignores_worktree_and_newer_commit(self) -> None:
        old = snapshot("source:main.java:2", self.repositories)
        verify(old, self.repositories)
        (self.repo / "main.java").write_text("class Example {\n  int count = 2;\n}\n", encoding="utf-8")
        verify(old, self.repositories)
        self.commit()
        verify(old, self.repositories)
        self.repositories["source"]["commit"] = self.head()
        with self.assertRaisesRegex(EvidenceError, "不一致"):
            verify(old, self.repositories)
        new = snapshot("source:main.java:2", self.repositories)
        self.assertNotEqual(old["snippet_sha256"], new["snippet_sha256"])
        self.assertNotEqual(old["blob_oid"], new["blob_oid"])

    def test_rejects_invalid_line_and_symlink(self) -> None:
        with self.assertRaisesRegex(EvidenceError, "越界"):
            snapshot("source:main.java:20", self.repositories)
        with self.assertRaisesRegex(EvidenceError, "不安全"):
            snapshot("source:../main.java:1", self.repositories)
        (self.repo / "linked.java").symlink_to("main.java")
        self.commit()
        self.repositories["source"]["commit"] = self.head()
        with self.assertRaisesRegex(EvidenceError, "非普通"):
            snapshot("source:linked.java:1", self.repositories)

    def test_lightweight_checks_and_snapshots_use_the_same_text_and_lines(self) -> None:
        # One physical line may contain UI text with Unicode display separators.
        path = "menu:rules.ts"
        physical_lines = ["title = 'A\u2028B\u0085C';\r\n".encode(), b"allow = true;\r", b"finish()"]
        (self.repo / path).write_bytes(b"".join(physical_lines))
        (self.repo / "alias.ts").symlink_to(path)
        (self.repo / "legacy.ts").write_bytes(b"old_encoding = '\xff';\n")
        (self.repo / "binary.ts").write_bytes(b"a\0b")
        (self.repo / "empty.ts").touch()
        self.commit()
        repo = self.repositories["source"]
        repo["commit"] = self.head()
        cache = PinnedReads()
        for invalid in ("alias.ts", "legacy.ts", "binary.ts", "missing.ts"):
            with self.subTest(invalid=invalid):
                self.assertIsNone(cache.read_text(repo, invalid))
                self.assertIsNone(cache.line_count(repo, invalid))
                with self.assertRaises(EvidenceError):
                    snapshot(f"source:{invalid}:1", self.repositories)
        self.assertEqual(cache.line_count(repo, "empty.ts"), 0)
        with self.assertRaisesRegex(EvidenceError, "越界"):
            snapshot("source:empty.ts:1", self.repositories)
        self.assertEqual(cache.line_count(repo, path), len(physical_lines))
        for number, raw_line in enumerate(physical_lines, 1):
            record = snapshot(f"source:{path}:{number}", self.repositories)
            self.assertEqual(record["snippet_sha256"], hashlib.sha256(raw_line).hexdigest())
        with self.assertRaisesRegex(EvidenceError, "越界"):
            snapshot(f"source:{path}:4", self.repositories)

    def test_literal_path_is_the_same_file_during_upgrade(self) -> None:
        path = ":(literal)rules.ts"
        (self.repo / path).write_bytes(b"export const count = 2;\n")
        self.commit()
        new_commit = self.head()
        old = self.repositories["source"]
        report = changed_paths(old, new_commit)[2]
        record = snapshot(f"source:{path}:1", {"source": {**old, "commit": new_commit}})
        self.assertEqual([(item["path"], item["new_blob_oid"]) for item in report],
                         [(path, record["blob_oid"])])

    def test_tampered_excerpt_digest_is_rejected(self) -> None:
        record = snapshot("source:main.java:1-2", self.repositories)
        changed = {**record, "snippet_sha256": "0" * 64}
        with self.assertRaisesRegex(EvidenceError, "不一致"):
            verify(changed, self.repositories)


if __name__ == "__main__":
    unittest.main()
