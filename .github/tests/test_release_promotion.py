"""Run the real consumer steps on one synthetic upload. No tags, credentials or network."""

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import package_plugins as packaging
import release_validation as release


VERSION = "999.0.1"  # Exists only inside the temporary fixture.
NOTES = "Offline fixture; this is not a release.\n"
WORKFLOW = ROOT / ".github/workflows/publish.yml"
ADAPTER = Path(__file__).parent / "fixtures/fake_release_service.py"


def workflow():
    # Ubuntu's runner includes Ruby/Psych; PyYAML is also usable locally.
    try:
        import yaml
    except ImportError:
        return json.loads(subprocess.check_output([
            "ruby", "-rpsych", "-rjson", "-e",
            "puts JSON.generate(Psych.safe_load(File.read(ARGV.first, encoding: 'UTF-8'), aliases: true))",
            str(WORKFLOW),
        ]))
    return yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture(root):
    """Build all real archive formats once from a new, unrelated local Git repository."""
    repo = root / "source"
    repo.mkdir()
    files = {
        "VERSION": VERSION + "\n", "LICENSE": "Synthetic fixture\n",
        f"docs/{VERSION}-release-notes.md": NOTES,
        ".claude-plugin/plugin.json": json.dumps({"name": "code2kb", "version": VERSION}),
        "plugin.json": json.dumps({"name": "code2kb", "version": VERSION}),
        "package.json": json.dumps({"name": "code2kb-dsh", "version": VERSION, "private": True,
                                    "files": [], "publishConfig": {"access": "public"}}),
        "index.mjs": "export default {};\n", "cordis.patch.yml": "plugins: {}\n",
        "dsh/icon.svg": "<svg/>\n", "locale/en.json": "{}\n",
    }
    for relative, data in files.items():
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(data, encoding="utf-8")
    # Real npm is used only for offline pack of this script-free private fixture.
    home = root / "build-home"
    home.mkdir()
    env = {"HOME": str(home), "PATH": os.environ["PATH"], "GIT_CONFIG_NOSYSTEM": "1",
           "npm_config_offline": "true", "npm_config_audit": "false", "npm_config_fund": "false"}
    with patch.dict(os.environ, env, clear=True):
        def git(*args):
            return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Offline fixture", "-c", "user.email=fixture@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "Synthetic unpublished fixture")
        commit = git("rev-parse", "HEAD")
        upload = root / "upload"
        with patch.multiple(packaging, ROOT=repo, COMMON=("VERSION", "LICENSE", "docs")):
            packaging.build_release(commit, tuple(packaging.HOSTS), upload)
    manifest = release.verify_bundle(upload, commit, digest(upload / packaging.MANIFEST))
    return upload, commit, manifest


class ReleasePromotionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temp = tempfile.TemporaryDirectory(prefix="code2kb-promotion-")
        cls.addClassCleanup(temp.cleanup)
        cls.root = Path(temp.name)
        # CI provides the pre-download producer outputs separately. Never derive those
        # trust anchors from the downloaded artifact, even if just one input is missing.
        inputs = ("BUNDLE", "COMMIT", "VERSION", "MANIFEST_SHA256", "SUMS_SHA256")
        if any("REHEARSAL_" + key in os.environ for key in inputs):
            source = {key: os.environ["REHEARSAL_" + key] for key in inputs}
            cls.upload, cls.commit = Path(source["BUNDLE"]), source["COMMIT"]
            cls.version = source["VERSION"]
            if not cls.version.startswith("999."):
                raise ValueError("offline promotion proof expects a synthetic 999.* version")
            cls.anchors = {k: source[k] for k in ("VERSION", "MANIFEST_SHA256", "SUMS_SHA256")}
            cls.anchors["SOURCE_COMMIT"] = cls.commit
            cls.manifest = release.verify_bundle(cls.upload, cls.commit, cls.anchors["MANIFEST_SHA256"])
        else:
            cls.upload, cls.commit, cls.manifest = fixture(cls.root)
            cls.version = VERSION
            cls.anchors = {
                "SOURCE_COMMIT": cls.commit, "VERSION": cls.version,
                "MANIFEST_SHA256": digest(cls.upload / packaging.MANIFEST),
                "SUMS_SHA256": digest(cls.upload / packaging.CHECKSUMS),
            }
        with zipfile.ZipFile(cls.upload / cls.manifest["artifacts"]["claude"]["filename"]) as archive:
            cls.notes = archive.read(f"docs/{cls.version}-release-notes.md").decode("utf-8")
        cls.jobs = workflow()["jobs"]
        cls.jobs_for_role = {"npm": "npm", "github": "github-release",
                             "preflight": "github-preflight"}

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="case-", dir=self.root)
        self.addCleanup(temp.cleanup)
        self.case = Path(temp.name)
        self.service = self.case / "fake-service"
        self.service.mkdir()
        self.bin = self.case / "bin"
        self.bin.mkdir()
        # Never fall through to real npm, gh, curl or the caller's HOME/token.
        (self.bin / "python3").symlink_to(sys.executable)
        (self.bin / "awk").symlink_to(shutil.which("awk"))
        for cmd in ("npm", "gh", "curl", "git"):
            (self.bin / cmd).symlink_to(ADAPTER.resolve())
        self.runners = {role: self.case / role for role in self.jobs_for_role}
        for runner in self.runners.values():
            runner.mkdir()
            if runner != self.runners["preflight"]:
                shutil.copytree(self.upload, runner / "downloaded-release-bundle")
        self.statefile = self.service / "state.json"
        self.state = {"version": self.version, "commit": self.commit, "latest": "2.4.0"}
        self.save_state()

    def save_state(self):
        self.statefile.write_text(json.dumps(self.state), encoding="utf-8")

    def consume(self, role, **overrides):
        """Execute every shell step of this job in declared order, with no hosted actions."""
        runner = self.runners[role]
        env = {"HOME": str(runner), "PATH": str(self.bin), "RUNNER_TEMP": str(runner),
               "FAKE_SERVICE": str(self.service), "GITHUB_RUN_ATTEMPT": "1",
               "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"}
        values = {**self.anchors, "ARMED": f"v{self.version}@{self.commit}", **overrides}
        context = {"runner.temp": str(runner), "github.workspace": str(runner), "github.token": "fake",
                   "github.sha": values["SOURCE_COMMIT"], "vars.RELEASE_ARMED_REF": values["ARMED"],
                   "needs.package.outputs.artifact_id": values.get("ARTIFACT_ID", "4242")}
        for key in ("VERSION", "SUMS_SHA256", "MANIFEST_SHA256"):
            context["needs.package.outputs." + key.lower()] = values[key]
        job = self.jobs[self.jobs_for_role[role]]
        for step in job["steps"]:
            if "run" not in step:
                self.assertIn(step["uses"].split("@")[0], {"actions/setup-node", "actions/download-artifact"})
                continue
            self.assertNotIn("if", step, "new conditional step must be modeled")
            step_env = dict(env)
            for key, expression in {**job.get("env", {}), **step.get("env", {})}.items():
                for name, value in context.items():
                    expression = expression.replace("${{ " + name + " }}", value)
                self.assertNotIn("${{", expression, "new consumer input must be modeled")
                step_env[key] = expression
            result = subprocess.run([shutil.which("bash"), "-eu", "-o", "pipefail", "-c", step["run"]],
                                    env=step_env, cwd=runner, capture_output=True, text=True, timeout=30)
            if result.returncode:
                return result
        return result

    def events(self, kind):
        path = self.service / "events.jsonl"
        items = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        return [i[1:] for i in items if i[0] == kind]

    def test_handoff_names_the_same_immutable_upload_and_independent_anchors(self):
        producer = self.jobs["package"]
        self.assertEqual(producer["outputs"]["artifact_id"], "${{ steps.upload.outputs.artifact-id }}")
        upload, = [step for step in producer["steps"] if step.get("id") == "upload"]
        self.assertTrue(upload["uses"].startswith("actions/upload-artifact@"))
        for key in ("version", "sums_sha256", "manifest_sha256"):
            self.assertEqual(producer["outputs"][key], "${{ steps.build.outputs." + key + " }}")
        for role in ("npm", "github"):
            job = self.jobs[self.jobs_for_role[role]]
            steps = job["steps"]
            download, = [s for s in steps if s.get("uses", "").startswith("actions/download-artifact@")]
            self.assertEqual(download["with"], {
                "artifact-ids": "${{ needs.package.outputs.artifact_id }}", "path": job["env"]["BUNDLE"]})
            checked, = [s for s in steps if s.get("id") == "verify_download"]
            write, = [s for s in steps if s.get("id") == role + "_write"]
            self.assertLess(steps.index(download), steps.index(checked))
            self.assertLess(steps.index(checked), steps.index(write))
            self.assertEqual(job["env"]["SOURCE_COMMIT"], "${{ github.sha }}")
            for key in ("VERSION", "SUMS_SHA256", "MANIFEST_SHA256"):
                self.assertEqual(job["env"][key], "${{ needs.package.outputs." + key.lower() + " }}")
        self.assertIn("github-preflight", self.jobs["npm"]["needs"])
        self.assertIn("npm", self.jobs["github-release"]["needs"])

    def test_tampered_download_bad_commit_and_anchor_stop_before_write(self):
        for role in ("npm", "github"):
            bundle = self.runners[role] / "downloaded-release-bundle"
            target = bundle / self.manifest["artifacts"]["dsh"]["filename"]
            for bad in ({"ARTIFACT_ID": ""}, {"SOURCE_COMMIT": "0" * 40}, {"MANIFEST_SHA256": "0" * 64},
                        {"SUMS_SHA256": "0" * 64}, {}):
                with self.subTest(consumer=role, override=bad):
                    if not bad:
                        target.write_bytes(target.read_bytes() + b"damaged after download")
                    self.assertNotEqual(self.consume(role, **bad).returncode, 0)
                    self.assertEqual(sorted(p.name for p in self.service.iterdir()), ["state.json"])

    def test_single_upload_both_sinks_and_ambiguous_npm_response(self):
        self.state["npm_response_lost"] = True
        self.save_state()
        for role in ("preflight", "npm", "github"):
            result = self.consume(role)
            self.assertEqual(result.returncode, 0, result.stderr)
        expected = {p.name: p.read_bytes() for p in self.upload.iterdir()}
        tarball = self.manifest["artifacts"]["dsh"]["filename"]
        self.assertEqual((self.service / "registry" / tarball).read_bytes(), expected[tarball])
        self.assertEqual({p.name: p.read_bytes() for p in (self.service / "assets").iterdir()}, expected)
        self.assertEqual(len(self.events("npm-write")), 1)
        self.assertEqual(len(self.events("github-write")), 7)  # New draft, five uploads, one finalize.
        for phase in ("draft", "public"):
            self.assertCountEqual([n for p, n in self.events("read-bytes") if p == phase], expected)
        published = json.loads((self.service / "release.json").read_bytes())
        self.assertEqual((published["body"], published["draft"], published["immutable"]), (self.notes, False, True))

        # A second matching npm observation does not write. An existing GitHub release blocks.
        result = self.consume("npm")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.events("npm-write")), 1)
        self.assertNotEqual(self.consume("github").returncode, 0)
        self.assertEqual(len(self.events("github-write")), 7)

    def test_preflight_requires_push_visibility_and_refuses_existing_draft(self):
        self.state["push"] = False
        self.save_state()
        self.assertNotEqual(self.consume("preflight").returncode, 0)
        self.state["push"] = True
        self.save_state()
        draft = self.service / "release.json"
        draft.write_text(json.dumps({"tag_name": "v" + self.version, "draft": True}))
        self.assertNotEqual(self.consume("preflight").returncode, 0)
        self.assertNotEqual(self.consume("github").returncode, 0)
        self.assertFalse(self.events("github-write"))

    def test_registry_503_channel_collision_and_mismatching_duplicate_do_not_publish(self):
        for key, value in (("registry_unavailable", True), ("extra_tags", {"release-" + self.version: "2.3.0"})):
            with self.subTest(key=key):
                self.state[key] = value
                self.save_state()
                self.assertNotEqual(self.consume("npm").returncode, 0)
                del self.state[key]
        self.save_state()
        registry = self.service / "registry"
        registry.mkdir()
        name = self.manifest["artifacts"]["dsh"]["filename"]
        (registry / name).write_bytes(b"different same-version bytes")
        self.assertNotEqual(self.consume("npm").returncode, 0)
        self.assertFalse(self.events("npm-write"))

    def test_unconfirmed_registry_after_publish_never_retries_write(self):
        self.state.update({"npm_response_lost": True, "post_write_read_fails": True})
        self.save_state()
        result = self.consume("npm")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self.events("npm-write")), 1)
        self.assertFalse(self.events("github-write"))

    def test_externally_moved_tag_and_disarmed_ref_block_both_writers(self):
        for role in ("npm", "github"):
            self.assertNotEqual(self.consume(role, ARMED="").returncode, 0)
        self.state["tag_commit"] = "0" * 40
        self.save_state()
        for role in ("npm", "github"):
            self.assertNotEqual(self.consume(role).returncode, 0)
        self.assertFalse(self.events("npm-write"))
        self.assertFalse(self.events("github-write"))

    def test_wrong_remote_bytes_leave_new_draft_unpublished_and_untouched_on_retry(self):
        self.state["corrupt_readback"] = True
        self.save_state()
        self.assertNotEqual(self.consume("github").returncode, 0)
        self.assertTrue(json.loads((self.service / "release.json").read_bytes())["draft"])
        writes = self.events("github-write")
        self.assertEqual(len(writes), 6)
        self.assertNotEqual(self.consume("github").returncode, 0)
        self.assertEqual(self.events("github-write"), writes)


if __name__ == "__main__":
    unittest.main()
