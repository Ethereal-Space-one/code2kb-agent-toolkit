#!/usr/bin/env python3
"""Read-only receipt for an exact Code2KB source revision. Never publishes."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import zipfile

import release_validation as rv

ROOT = Path(__file__).resolve().parents[1]
ERRORS = (ValueError, TypeError, KeyError, OSError, subprocess.SubprocessError, tarfile.TarError, zipfile.BadZipFile)


def status(state, **details):
    return dict(state=state, **details)


def ci(reads, commit, run_id):
    if type(run_id) is not int or run_id <= 0:
        return status("pending", reason="supply_exact_main_push_CI_run_ID")
    run = reads.json(f"/actions/runs/{run_id}", github=True, missing_ok=True)
    if run is None: return status("pending", reason="no_visible_run_for_id")
    if (run.get("id") != run_id or run.get("head_sha") != commit or run.get("path") != ".github/workflows/ci.yml" or
        run.get("event") != "push" or run.get("head_branch") != "main" or
        any(not isinstance(run.get(k), dict) or run[k].get("full_name") != rv.REPOSITORY for k in ("repository", "head_repository"))):
        raise ValueError("CI run identity, branch, workflow or commit mismatch")
    attempt = run.get("run_attempt")
    if type(attempt) is not int or attempt <= 0: raise ValueError("invalid CI attempt")
    identity = dict(run_id=run_id, attempt=attempt, url=f"https://github.com/{rv.REPOSITORY}/actions/runs/{run_id}/attempts/{attempt}")
    if run.get("status") != "completed": return status("pending", **identity, reason="CI_not_completed")
    if run.get("conclusion") != "success": return status("failed", **identity, conclusion=run.get("conclusion"))
    jobs = reads.json(f"/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100", github=True)
    items = jobs.get("jobs")
    if not isinstance(items, list) or type(jobs.get("total_count")) is not int or not 0 < len(items) == jobs["total_count"] <= 100:
        raise ValueError("CI jobs inventory incomplete")
    gates = [j for j in items if isinstance(j, dict) and j.get("name") == "CI Gate"]
    names = {j.get("name") for j in items if isinstance(j, dict)}
    if not {"macos-smoke", "plugin-packages"} <= names or not any(isinstance(n, str) and n.startswith("test (") for n in names):
        raise ValueError("missing matrix, macOS or packaging job")
    if len(gates) != 1 or any(not isinstance(j, dict) or j.get("run_id") != run_id or j.get("head_sha") != commit or
                              j.get("status") != "completed" or j.get("conclusion") != "success" for j in items):
        raise ValueError("missing/duplicate CI Gate or non-successful/wrong-subject job")
    return status("verified", **identity, jobs=len(items))


def build(repo, commit, directory=None, manifest_sha=None, reads=None, run_id=None):
    if not isinstance(commit, str) or not rv.SHA.fullmatch(commit):
        raise ValueError("expected full 40-character Git commit")
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE).decode().strip()
    if git("rev-parse", "--verify", commit + "^{commit}") != commit: raise ValueError("source commit mismatch")
    version = git("show", commit + ":VERSION")
    if not rv.VERSION.fullmatch(version): raise ValueError("invalid pinned VERSION")
    rows = dict(source=status("verified", commit=commit, version=version,
                              scope="committed_tree_only_not_worktree"), ci=status("pending", reason="offline"),
                package=status("pending", reason="expected_bundle_not_supplied"),
                npm=status("pending", reason="offline"), github_release=status("pending", reason="offline"))
    manifest = None
    if bool(directory) != bool(manifest_sha): raise ValueError("bundle dir and independently recorded manifest SHA256 must be supplied together")
    if directory:
        try:
            manifest = rv.verify_bundle(directory, commit, manifest_sha)
            if manifest["version"] != version: raise ValueError("bundle version disagrees with pinned VERSION")
            rows["package"] = status("verified", manifest_sha256=manifest_sha, artifacts=manifest["artifacts"],
                                     scope="locally_verified_bytes_not_remote_publication")
        except ERRORS as exc:
            manifest = None; rows["package"] = status("failed", reason=str(exc))
    if reads is not None:
        def observe(key, fn):
            try:
                rows[key] = fn()
            except ERRORS as exc:
                rows[key] = status("unverified", reason=str(exc))
        observe("ci", lambda: ci(reads, commit, run_id))
        if manifest is None:
            rows["npm"] = rows["github_release"] = status("pending", reason="needs_verified_expected_bundle")
        else:
            def npm():
                n, latest = rv.observe_npm(manifest, reads)
                if reads.json(f"/{rv.PACKAGE}/latest", missing_ok=True) != latest: raise ValueError("latest changed during read")
                if n["version_state"] == "absent": return status("pending", reason="version_not_in_public_registry", observed_latest=n["observed_latest"])
                tags = reads.json(f"/-/package/{rv.PACKAGE}/dist-tags")
                if tags.get("release-" + version) != version: raise ValueError("version-specific npm dist-tag missing or mismatched")
                if tags.get("latest") != n["observed_latest"]: raise ValueError("latest changed during tag read")
                return status("verified", package=rv.PACKAGE, version=version, observed_latest=n["observed_latest"],
                              integrity=manifest["artifacts"]["dsh"]["integrity"], scope="verified_public_tarball_bytes")
            def github():
                g, release = rv.observe_github(directory, manifest, reads)
                if release is None: return status("pending", reason="release_not_publicly_visible")
                if release.get("draft") is not False or release.get("prerelease") is not False or release.get("immutable") is not True:
                    return status("pending", reason="immutable_final_release_not_verified")
                return status("verified", tag="v"+version, scope=g["asset_metadata"])
            observe("npm", npm); observe("github_release", github)
    states = {entry["state"] for entry in rows.values()}
    result = "verified" if states == {"verified"} else ("blocked" if states.intersection({"failed", "unverified"}) else "pending")
    return dict(schema="code2kb.release-observation/1", observed_at=datetime.now(timezone.utc).isoformat(),
                result=result, checks=rows, writes=False, scope="Point-in-time observations only; not authorization, provenance signature or permission to release.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--expected-commit", required=True); p.add_argument("--bundle-dir", type=Path)
    p.add_argument("--manifest-sha256"); p.add_argument("--online", action="store_true", help="Unauthenticated GETs only")
    p.add_argument("--ci-run", type=int)
    a = p.parse_args()
    try:
        if a.ci_run is not None and (not a.online or a.ci_run <= 0):
            raise ValueError("a positive --ci-run requires --online")
        result = build(ROOT, a.expected_commit, a.bundle_dir, a.manifest_sha256,
                       rv.PublicReads(attempts=1) if a.online else None, a.ci_run)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return {"verified": 0, "pending": 2, "blocked": 1}[result["result"]]
    except ERRORS as exc:
        print(str(exc), file=sys.stderr); return 1


if __name__ == "__main__":
    raise SystemExit(main())
