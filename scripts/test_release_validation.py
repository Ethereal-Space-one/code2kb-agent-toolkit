"""Offline regressions for release bytes, retries and non-mutating decisions."""

import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
import zipfile

import package_plugins as packaging
import release_validation as release
import release_receipt as receipt


class BundleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="code2kb-release-tests-")
        cls.root = Path(cls.temporary.name)
        cls.repo = cls.root / "repo"
        cls.repo.mkdir()
        files = {
            "VERSION": "2.5.0\n",
            "LICENSE": "Synthetic test license\n",
            "docs/guide.md": "Synthetic public fixture\n",
            ".claude-plugin/plugin.json": '{"name":"fixture","version":"2.5.0"}\n',
            "plugin.json": '{"name":"fixture","version":"2.5.0"}\n',
            "package.json": json.dumps({"name": release.PACKAGE, "version": "2.5.0", "private": True, "files": []}),
            "index.mjs": "export default {};\n",
            "cordis.patch.yml": "plugins: {}\n",
            "dsh/icon.svg": "<svg/>\n",
            "locale/en.json": "{}\n",
        }
        for name, data in files.items():
            path = cls.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(data, encoding="utf-8")
        def git(*args):
            return subprocess.check_output(["git", "-C", str(cls.repo), *args], text=True).strip()
        git("init", "-q")
        git("config", "user.name", "Release fixture")
        git("config", "user.email", "release@example.invalid")
        git("config", "commit.gpgsign", "false")
        git("add", ".")
        git("commit", "-qm", "Synthetic release fixture")
        cls.commit = git("rev-parse", "HEAD")
        cls.original = cls.root / "original"
        with patch.multiple(packaging, ROOT=cls.repo, COMMON=("VERSION", "LICENSE", "docs")):
            packaging.build_release(cls.commit, tuple(packaging.HOSTS), cls.original)
        cls.manifest = release.verify_bundle(cls.original, cls.commit)

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="code2kb-release-case-")
        self.addCleanup(self.work.cleanup)
        self.bundle = Path(self.work.name) / "bundle"
        shutil.copytree(self.original, self.bundle)
        self.digest = hashlib.sha256((self.bundle / packaging.MANIFEST).read_bytes()).hexdigest()

    def published(self):
        record = self.manifest["artifacts"]["dsh"]
        return {"name": release.PACKAGE, "version": "2.5.0", "gitHead": self.commit,
                "dist": {"integrity": record["integrity"], "tarball": f"{release.REGISTRY}/{release.PACKAGE}/-/{release.PACKAGE}-2.5.0.tgz"}}

    def test_complete_bundle_and_independent_anchor(self):
        self.assertEqual(release.verify_bundle(self.bundle, self.commit, self.digest), self.manifest)
        with self.assertRaisesRegex(ValueError, "独立记录"):
            release.verify_bundle(self.bundle, self.commit, "0" * 64)
        with self.assertRaisesRegex(ValueError, "提交"):
            release.verify_bundle(self.bundle, "0" * 40, self.digest)

    def test_repeated_builds_are_time_stable_and_ignore_dirty_worktree(self):
        other = Path(self.work.name) / "later"
        (self.repo / "docs/guide.md").write_text("Uncommitted local edit", encoding="utf-8")
        try:
            with patch.multiple(packaging, ROOT=self.repo, COMMON=("VERSION", "LICENSE", "docs")), patch("time.time", return_value=2_000_000_000):
                packaging.build_release(self.commit, tuple(packaging.HOSTS), other)
            self.assertEqual({p.name: p.read_bytes() for p in self.original.iterdir()}, {p.name: p.read_bytes() for p in other.iterdir()})
            for path in other.glob("*.zip"):
                with zipfile.ZipFile(path) as archive:
                    self.assertTrue(all(entry.date_time == (1980, 1, 1, 0, 0, 0) for entry in archive.infolist()))
        finally:
            (self.repo / "docs/guide.md").write_text("Synthetic public fixture\n", encoding="utf-8")

    def test_output_retry_never_overwrites_existing_bundle(self):
        before = {p.name: p.read_bytes() for p in self.bundle.iterdir()}
        with self.assertRaisesRegex(ValueError, "输出目录"):
            packaging.build_release(self.commit, tuple(packaging.HOSTS), self.bundle)
        self.assertEqual(before, {p.name: p.read_bytes() for p in self.bundle.iterdir()})

    def test_corrupt_archive_extra_files_and_checksum_mismatch(self):
        artifact = self.bundle / self.manifest["artifacts"]["dsh"]["filename"]
        artifact.write_bytes(artifact.read_bytes() + b"corrupt")
        with self.assertRaisesRegex(ValueError, "清单不一致"):
            release.verify_bundle(self.bundle)
        shutil.copyfile(self.original / artifact.name, artifact)
        extra = self.bundle / "unexpected.txt"
        extra.touch()
        with self.assertRaisesRegex(ValueError, "额外"):
            release.verify_bundle(self.bundle)
        extra.unlink()
        (self.bundle / packaging.CHECKSUMS).write_text("0" * 64 + "  something\n", encoding="ascii")
        with self.assertRaisesRegex(ValueError, "SHA256SUMS"):
            release.verify_bundle(self.bundle)

    def test_symlink_and_duplicate_json_rejected(self):
        path = self.bundle / packaging.MANIFEST
        path.unlink()
        path.symlink_to(self.original / packaging.MANIFEST)
        with self.assertRaisesRegex(ValueError, "符号链接"):
            release.verify_bundle(self.bundle)
        with self.assertRaisesRegex(ValueError, "重复 JSON"):
            release.parse_json(b'{"version":"2.5.0","version":"2.4.0"}')

    def test_receipt_offline_does_not_promote_or_infer_remote_state(self):
        r = receipt.build(self.repo, self.commit, self.bundle, self.digest)
        self.assertEqual(r["result"], "pending")
        self.assertEqual(r["checks"]["package"]["state"], "verified")
        self.assertTrue(all(r["checks"][k]["state"] == "pending" for k in ("ci","npm","github_release")))
        self.assertFalse(r["writes"])
        invalid = receipt.build(self.repo, self.commit, self.bundle, "0"*64, self.reads())
        self.assertEqual(invalid["result"], "blocked")
        self.assertEqual(invalid["checks"]["package"]["state"], "failed")
        self.assertEqual(invalid["checks"]["npm"]["state"], "pending")

    def test_receipt_ci_provenance_and_exact_attempt(self):
        names = ["test (3.9)", "macos-smoke", "plugin-packages", "CI Gate"]
        run = dict(id=7, head_sha=self.commit, path=".github/workflows/ci.yml", event="push", head_branch="main",
                   repository={"full_name":release.REPOSITORY},head_repository={"full_name":release.REPOSITORY},
                   run_attempt=2, status="completed",conclusion="success")
        jobs = dict(total_count=len(names),jobs=[dict(name=n,head_sha=self.commit,run_id=7,status="completed",conclusion="success") for n in names])
        for changes in ({"head_sha":"0"*40},{"head_branch":"other"},{"event":"pull_request"},
                        {"head_repository":{"full_name":"fork/other"}},{"path":"static/other"}):
            reads = Mock(); reads.json.return_value = {**run,**changes}
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "mismatch"):
                receipt.ci(reads,self.commit,7)
        reads = Mock(); reads.json.side_effect = [run,jobs]
        self.assertEqual(receipt.ci(reads,self.commit,7)["state"], "verified")
        self.assertIn("/attempts/2/jobs?",reads.json.call_args.args[0])
        for mutation in ("missing", "cancelled", "partial", "wrong-job"):
            data = copy.deepcopy(jobs)
            if mutation == "missing": data["jobs"][-1]["name"] = "other"
            if mutation == "cancelled": data["jobs"][1]["conclusion"] = "cancelled"
            if mutation == "partial": data["total_count"] = 120
            if mutation == "wrong-job": data["jobs"][2]["head_sha"] = "0"*40
            reads = Mock(); reads.json.side_effect = [run,data]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                receipt.ci(reads,self.commit,7)

    def test_receipt_isolates_registry_release_and_ci_failures(self):
        assets = [{"name":p.name,"size":p.stat().st_size,"digest":"sha256:"+hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.bundle.iterdir()]
        live = dict(tag_name="v2.5.0",draft=False,prerelease=False,immutable=True,assets=assets)
        reads = self.reads(live)
        base = reads.json.side_effect
        def get(path, **kwargs):
            if "dist-tags" in path: return {"latest":"2.5.0","release-2.5.0":"2.5.0"}
            return base(path,**kwargs)
        reads.json.side_effect = get
        with patch.object(receipt, "ci", return_value={"state":"verified"}):
            r = receipt.build(self.repo,self.commit,self.bundle,self.digest,reads,7)
            self.assertEqual(r["result"],"verified")
            self.assertEqual(r["checks"]["github_release"]["scope"],"matching_not_independently_downloaded")
            reads.read.return_value=b"different tarball"
            r = receipt.build(self.repo,self.commit,self.bundle,self.digest,reads,7)
            self.assertEqual(r["result"],"blocked")
            self.assertEqual(r["checks"]["npm"]["state"],"unverified")
            self.assertEqual(r["checks"]["github_release"]["state"],"verified")
            r = receipt.build(self.repo,self.commit,self.bundle,self.digest,self.reads(published=False),7)
            self.assertEqual(r["result"],"pending")
            self.assertEqual(r["checks"]["npm"]["state"],"pending")

    def test_registry_matching_retry_skips_publish_and_never_lowers_latest(self):
        for latest in ("2.5.0", "2.6.0", "2.10.0"):
            plan = release.registry_plan(self.manifest, self.published(), {"name": release.PACKAGE, "version": latest})
            self.assertEqual((plan["publish"], plan["latest"]), ("skip", "keep"))
        plan = release.registry_plan(self.manifest, self.published(), {"name": release.PACKAGE, "version": "2.4.0"})
        self.assertEqual(plan["latest"], "promotion_needs_separate_approval")

    def test_registry_mismatch_or_uncertain_state_never_suggests_republish(self):
        for key, value in (("name", "other"), ("version", "2.4.0"), ("gitHead", "0" * 40), ("dist", {"integrity": "sha512-wrong"})):
            published = self.published()
            published[key] = value
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "不匹配"):
                release.registry_plan(self.manifest, published, {"name": release.PACKAGE, "version": "2.4.0"})
        for latest in ("2.5.0", "2.6.0", "2.10.0"):
            with self.assertRaisesRegex(ValueError, "不得|禁止"):
                release.registry_plan(self.manifest, None, {"name": release.PACKAGE, "version": latest})
        with self.assertRaisesRegex(ValueError, "latest 缺失"):
            release.registry_plan(self.manifest, self.published(), None)
        with self.assertRaisesRegex(ValueError, "候选版本"):
            release.registry_plan(self.manifest, None, {"name": release.PACKAGE, "version": "2.4.1-rc.1"})
        plan = release.registry_plan(self.manifest, None, {"name": release.PACKAGE, "version": "2.4.0"})
        self.assertEqual((plan["publish"], plan["latest"]), ("not_performed", "do_not_change"))

    def reads(self, release_data=None, latest_again=None, published=True):
        latest = {"name": release.PACKAGE, "version": "2.5.0" if published else "2.4.0"}
        values = {
            f"/{release.PACKAGE}/2.5.0": self.published() if published else None,
            f"/{release.PACKAGE}/latest": latest,
            "/git/ref/tags/v2.5.0": {"object": {"type": "commit", "sha": self.commit}},
            "/releases/tags/v2.5.0": release_data,
        }
        reads = Mock()
        count = 0
        def get(path, **kwargs):
            nonlocal count
            if path.endswith("/latest"):
                count += 1
                if count > 1 and latest_again is not None:
                    return latest_again
            return copy.deepcopy(values[path])
        reads.json.side_effect = get
        reads.read.return_value = (self.bundle / self.manifest["artifacts"]["dsh"]["filename"]).read_bytes()
        return reads

    def test_reconciliation_checks_actual_registry_bytes_and_is_read_only(self):
        result = release.reconcile(self.bundle, self.manifest, self.reads())
        self.assertFalse(result["remote_writes"])
        self.assertEqual(result["npm"]["archive_bytes"], "matching")
        self.assertEqual(result["npm"]["publish"], "skip")
        reads = self.reads()
        reads.read.return_value = b"wrong bytes"
        with self.assertRaisesRegex(ValueError, "实际 registry"):
            release.reconcile(self.bundle, self.manifest, reads)

    def test_mid_reconciliation_latest_change_stops(self):
        with self.assertRaisesRegex(ValueError, "latest 已变化"):
            release.reconcile(self.bundle, self.manifest, self.reads(latest_again={"name": release.PACKAGE, "version": "2.6.0"}))

    def test_existing_github_release_is_never_modified_or_finalized(self):
        assets = [{"name": p.name, "size": p.stat().st_size, "digest": "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()} for p in self.bundle.iterdir()]
        for draft in (True, False):
            data = {"tag_name": "v2.5.0", "draft": draft, "immutable": False, "assets": assets}
            result = release.reconcile(self.bundle, self.manifest, self.reads(data))
            self.assertEqual(result["github"]["action"], "do_not_modify")
        data["assets"] = assets[:-1]
        with self.assertRaisesRegex(ValueError, "历史资产"):
            release.reconcile(self.bundle, self.manifest, self.reads(data))
        data["assets"] = copy.deepcopy(assets)
        data["assets"][0]["digest"] = "sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "禁止覆盖"):
            release.reconcile(self.bundle, self.manifest, self.reads(data))

    def test_wrong_tag_commit_cannot_be_repaired(self):
        with self.assertRaisesRegex(ValueError, "禁止移动"):
            release.github_plan(self.manifest, None, "0" * 40)
        self.assertEqual(release.github_plan(self.manifest, None, None)["action"], "await_reviewed_tag_and_draft")

    def test_unicode_versions_and_malformed_nested_state_stop(self):
        with self.assertRaisesRegex(ValueError, "X.Y.Z"):
            release.stable_version("2.5.1\u0661")
        with patch("package_plugins.git", return_value="2.5.1\u0661\n".encode("utf-8")), self.assertRaisesRegex(ValueError, "X.Y.Z"):
            packaging.build_release(self.commit, tuple(packaging.HOSTS), Path(self.work.name) / "invalid-version")
        published = self.published()
        published["dist"] = None
        with self.assertRaisesRegex(ValueError, "dist 不是对象"):
            release.registry_plan(self.manifest, published, {"name": release.PACKAGE, "version": "2.4.0"})
        reads = self.reads()
        original = reads.json.side_effect
        reads.json.side_effect = lambda path, **kwargs: {"object": []} if path.startswith("/git/ref/") else original(path, **kwargs)
        with self.assertRaisesRegex(ValueError, "object 或 SHA"):
            release.reconcile(self.bundle, self.manifest, reads)
        for assets in (None, {}, [None], [{"name": []}]):
            data = {"tag_name": "v2.5.0", "assets": assets}
            with self.subTest(assets=assets), self.assertRaisesRegex(ValueError, "资产字段格式"):
                release.reconcile(self.bundle, self.manifest, self.reads(data))


class PublicReadTest(unittest.TestCase):
    def response(self, data=b"{}"):
        response = Mock(status=200)
        response.read.return_value = data
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        return response

    @patch("release_validation.time.sleep")
    def test_only_get_and_bounded_retry(self, sleep):
        reads = release.PublicReads(attempts=2)
        reads.opener = Mock()
        reads.opener.open.side_effect = [URLError("temporary"), self.response()]
        self.assertEqual(reads.json("/code2kb-dsh/latest"), {})
        self.assertEqual(reads.opener.open.call_count, 2)
        self.assertTrue(all(call.args[0].get_method() == "GET" for call in reads.opener.open.call_args_list))
        sleep.assert_called_once()

    @patch("release_validation.time.sleep")
    def test_unknown_result_exhausts_reads_not_publication(self, sleep):
        reads = release.PublicReads(attempts=2)
        reads.opener = Mock()
        reads.opener.open.side_effect = URLError("unavailable")
        with self.assertRaisesRegex(ValueError, "不得盲目重新发布"):
            reads.json("/code2kb-dsh/latest")
        self.assertEqual(reads.opener.open.call_count, 2)

    def test_404_is_absence_only_when_explicitly_allowed(self):
        reads = release.PublicReads()
        reads.opener = Mock()
        reads.opener.open.side_effect = HTTPError("https://registry.npmjs.org/code2kb-dsh/latest", 404, "missing", {}, io.BytesIO())
        self.assertIsNone(reads.json("/code2kb-dsh/latest", missing_ok=True))
        with self.assertRaisesRegex(ValueError, "不得推断"):
            reads.read(release.REGISTRY + "/code2kb-dsh/-/code2kb-dsh-2.5.0.tgz", 100)

    def test_redirects_arbitrary_hosts_oversize_and_nonobject_json_fail(self):
        reads = release.PublicReads()
        reads.opener = Mock()
        with self.assertRaisesRegex(ValueError, "固定公开"):
            reads.read("https://example.invalid/token", 100)
        reads.opener.open.assert_not_called()
        with self.assertRaisesRegex(ValueError, "重定向"):
            release.NoRedirects().redirect_request(None, None, 302, "redirect", {}, "https://other.invalid")
        reads.opener.open.return_value = self.response(b"12345")
        with self.assertRaisesRegex(ValueError, "超过"):
            reads.read(release.REGISTRY + "/code2kb-dsh/latest", 4)
        reads.opener.open.return_value = self.response(b"[]")
        with self.assertRaisesRegex(ValueError, "不是 JSON 对象"):
            reads.json("/code2kb-dsh/latest")

    def test_http_200_null_never_means_missing_registry_or_github_state(self):
        reads = release.PublicReads()
        reads.opener = Mock()
        reads.opener.open.return_value = self.response(b"null")
        for path, github in (("/code2kb-dsh/2.5.0", False), ("/code2kb-dsh/latest", False),
                             ("/git/ref/tags/v2.5.0", True), ("/releases/tags/v2.5.0", True)):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "不是 JSON 对象"):
                reads.json(path, github=github, missing_ok=True)


if __name__ == "__main__":
    unittest.main()
