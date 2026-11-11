"""Regression tests for packaging boundaries, using only temporary repositories."""

import io
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import package_plugins


class PackagePluginsTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="code2kb-package-test-")
        self.addCleanup(temporary.cleanup)
        self.work = Path(temporary.name)
        self.repo = self.work / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Packaging test")
        self.git("config", "user.email", "packaging@example.invalid")
        self.git("config", "commit.gpgsign", "false")
        self.docs = self.repo / "docs"
        self.docs.mkdir()
        (self.docs / "guide.md").write_text("committed\n", encoding="utf-8")
        self.stage = self.work / "stage"
        self.stage.mkdir()
        settings = patch.multiple(package_plugins, ROOT=self.repo, COMMON=("docs",), HOSTS={"claude": ()})
        settings.start()
        self.addCleanup(settings.stop)

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def commit(self):
        self.git("add", "--all")
        self.git("commit", "-qm", "Packaging fixture")
        return self.git("rev-parse", "HEAD")

    def test_reads_commit_even_when_worktree_has_private_files(self):
        revision = self.commit()
        (self.docs / "guide.md").write_text("local edit\n", encoding="utf-8")
        (self.docs / "private.md").write_text("local draft\n", encoding="utf-8")
        package_plugins.stage_commit(revision, self.stage, "claude")
        self.assertEqual(set(package_plugins.staged_files(self.stage)), {"docs/guide.md"})
        self.assertEqual((self.stage / "docs/guide.md").read_text(encoding="utf-8"), "committed\n")

    def test_rejects_committed_configuration_with_secrets(self):
        (self.docs / ".env.local").touch()
        with self.assertRaisesRegex(ValueError, r"\.env\.local"):
            package_plugins.stage_commit(self.commit(), self.stage, "claude")

    def test_rejects_committed_symlink(self):
        (self.docs / "link.md").symlink_to("guide.md")
        with self.assertRaisesRegex(ValueError, "link.md"):
            package_plugins.stage_commit(self.commit(), self.stage, "claude")

    def test_checks_links_in_a_stage_reached_through_a_symlink(self):
        (self.stage / "guide.md").write_text("[license](LICENSE)\n", encoding="utf-8")
        (self.stage / "LICENSE").touch()
        alias = self.work / "staging-alias"
        alias.symlink_to(self.stage, target_is_directory=True)
        self.assertEqual(package_plugins.check_markdown_links(alias), 0)

    def test_rejects_changed_npm_member(self):
        (self.stage / "guide.md").write_bytes(b"expected")
        artifact = self.work / "package.tgz"
        with tarfile.open(artifact, mode="w:gz") as archive:
            member = tarfile.TarInfo("package/guide.md")
            content = b"changed"
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
        with self.assertRaisesRegex(ValueError, "guide.md"):
            package_plugins.verify_npm(self.stage, artifact)


if __name__ == "__main__":
    unittest.main()
