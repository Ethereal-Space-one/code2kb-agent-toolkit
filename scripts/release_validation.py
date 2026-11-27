#!/usr/bin/env python3
"""Verify release bundles and make a GET-only reconciliation plan. Never publish."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import sys
import tarfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

from package_plugins import CHECKSUMS, FORBIDDEN, HOSTS, MANIFEST, MANIFEST_FORMAT, artifact_record


REPOSITORY = "Ethereal-Space-one/code2kb-agent-toolkit"
PACKAGE = "code2kb-dsh"
REGISTRY = "https://registry.npmjs.org"
API = f"https://api.github.com/repos/{REPOSITORY}"
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)")
SHA = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复 JSON 键：{key}")
        result[key] = value
    return result


def parse_json(data: bytes):
    return json.loads(data.decode("utf-8"), object_pairs_hook=unique_object)


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return bool(path.parts) and not (
        path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name
        or FORBIDDEN.intersection(path.parts)
        or any(part.startswith(".env.") for part in path.parts)
    ) and path.as_posix() == name


def archive_manifest(path: Path, target: str) -> dict:
    """Inspect, never extract or execute, package contents."""
    files = {}
    if target == "dsh":
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                if not member.isfile() or not member.name.startswith("package/"):
                    raise ValueError("npm 包含非普通文件或越界条目")
                name = member.name[len("package/"):]
                if not safe_member(name) or name in files:
                    raise ValueError("npm 包含不安全或重复路径")
                files[name] = archive.extractfile(member).read()
        manifest = parse_json(files.get("package.json", b"null"))
        if not isinstance(manifest, dict) or manifest.get("files") != sorted(files):
            raise ValueError("npm 文件清单不完整或不一致")
        if manifest.get("name") != PACKAGE or "private" in manifest or manifest.get("scripts"):
            raise ValueError("npm 包身份、私有标记或生命周期脚本不符合发布边界")
        if manifest.get("dependencies") or manifest.get("devDependencies"):
            raise ValueError("本发行契约不允许隐式增加 npm 依赖")
        return manifest
    with zipfile.ZipFile(path) as archive:
        for member in archive.infolist():
            kind = (member.external_attr >> 16) & 0o170000
            if member.is_dir() or kind not in (0, 0o100000) or not safe_member(member.filename) or member.filename in files:
                raise ValueError("ZIP 包含不安全、重复或非普通文件")
            files[member.filename] = archive.read(member)
    return parse_json(files.get(HOSTS[target][0], b"null"))


def verify_bundle(directory: Path, expected_commit: str | None = None,
                  manifest_sha256: str | None = None) -> dict:
    manifest_path = directory / MANIFEST
    if manifest_path.is_symlink():
        raise ValueError("发布清单不能是符号链接")
    data = manifest_path.read_bytes()
    if manifest_sha256 is not None and (
        not SHA256.fullmatch(manifest_sha256) or hashlib.sha256(data).hexdigest() != manifest_sha256
    ):
        raise ValueError("发布清单与独立记录的 SHA256 不一致")
    manifest = parse_json(data)
    if not isinstance(manifest, dict) or set(manifest) != {"format", "version", "source_commit", "artifacts"}:
        raise ValueError("发布清单字段不符合契约")
    version, commit = manifest["version"], manifest["source_commit"]
    if manifest["format"] != MANIFEST_FORMAT or not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("发布清单格式或正式版本无效")
    if not isinstance(commit, str) or not SHA.fullmatch(commit) or (expected_commit is not None and commit != expected_commit):
        raise ValueError("发布清单提交与预期不一致")
    if not isinstance(manifest["artifacts"], dict) or set(manifest["artifacts"]) != set(HOSTS):
        raise ValueError("完整发布必须恰好包含 Claude、Codex、DSH 三种产物")
    expected_files = {MANIFEST, CHECKSUMS}
    checksums = {MANIFEST: hashlib.sha256(data).hexdigest()}
    for target, record in manifest["artifacts"].items():
        name = f"code2kb-{target}-{version}.{'tgz' if target == 'dsh' else 'zip'}"
        if not isinstance(record, dict) or set(record) != {"filename", "size", "sha256", "integrity"} or record["filename"] != name:
            raise ValueError("发布产物文件名或字段不符合契约")
        if type(record["size"]) is not int or record["size"] <= 0:
            raise ValueError("发布产物大小无效")
        artifact = directory / name
        if artifact.is_symlink() or not artifact.is_file() or artifact_record(artifact) != record:
            raise ValueError(f"发布产物内容与清单不一致：{name}")
        package = archive_manifest(artifact, target)
        if not isinstance(package, dict) or package.get("version") != version:
            raise ValueError(f"{target} 归档版本不一致")
        if target == "dsh" and package.get("gitHead") != commit:
            raise ValueError("npm gitHead 与发布提交不一致")
        expected_files.add(name)
        checksums[name] = record["sha256"]
    actual = {path.name for path in directory.iterdir()}
    if actual != expected_files or any(path.is_symlink() or not path.is_file() for path in directory.iterdir()):
        raise ValueError("发布目录含缺失、额外或非普通文件")
    expected_sums = "".join(f"{checksums[name]}  {name}\n" for name in sorted(checksums))
    if (directory / CHECKSUMS).read_text(encoding="ascii") != expected_sums:
        raise ValueError("SHA256SUMS 与发布清单或产物不一致")
    return manifest


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("只读核对不跟随重定向")


class PublicReads:
    """Only fixed public GET endpoints; no tokens, writes or external redirects."""
    def __init__(self, attempts: int = 3):
        if not 1 <= attempts <= 5:
            raise ValueError("读取尝试次数必须在 1–5 之间")
        self.attempts = attempts
        self.opener = build_opener(NoRedirects())

    def read(self, url: str, limit: int, missing_ok: bool = False) -> bytes | None:
        if not url.startswith((REGISTRY + "/", API + "/")):
            raise ValueError("只允许固定公开 registry 与仓库端点")
        for attempt in range(self.attempts):
            try:
                request = Request(url, headers={"User-Agent": "code2kb-release-rehearsal", "Accept": "application/json", "Cache-Control": "no-cache"}, method="GET")
                with self.opener.open(request, timeout=15) as response:
                    if response.status != 200:
                        raise ValueError("公开读取状态不是 200")
                    data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError("公开响应超过预期大小")
                return data
            except HTTPError as exc:
                if exc.code == 404 and missing_ok:
                    return None
                if exc.code not in (429, 500, 502, 503, 504):
                    raise ValueError(f"公开读取失败 HTTP {exc.code}；不得推断发布结果") from exc
                error = exc
            except (URLError, TimeoutError, OSError) as exc:
                error = exc
            if attempt + 1 < self.attempts:
                time.sleep(min(attempt + 1, 3))
        raise ValueError("公开读取重试后仍失败；停止，不得盲目重新发布") from error

    def json(self, path: str, github: bool = False, missing_ok: bool = False):
        data = self.read((API if github else REGISTRY) + path, 2_000_000, missing_ok)
        if data is None:
            return None  # Only an explicitly allowed HTTP 404 means absence.
        result = parse_json(data)
        if not isinstance(result, dict):
            raise ValueError("公开 API 返回的不是 JSON 对象")
        return result


def stable_version(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("只接受已明确核对的 X.Y.Z latest；候选版本不在本批范围")
    return tuple(map(int, value.split(".")))


def registry_plan(manifest: dict, published: dict | None, latest: dict | None) -> dict:
    """Pure decision logic. Existing mismatches/unknown state always stop."""
    version, commit = manifest["version"], manifest["source_commit"]
    record = manifest["artifacts"]["dsh"]
    if latest is not None and (not isinstance(latest, dict) or latest.get("name") != PACKAGE or "version" not in latest):
        raise ValueError("latest 包身份无效")
    latest_version = None if latest is None else latest["version"]
    current = None if latest is None else stable_version(latest_version)
    wanted = stable_version(version)
    if published is not None:
        if not isinstance(published, dict) or not isinstance(published.get("dist"), dict):
            raise ValueError("已发布 npm 的 dist 不是对象；远端状态未知")
        if (published.get("name"), published.get("version"), published.get("gitHead"), published["dist"].get("integrity")) != (PACKAGE, version, commit, record["integrity"]):
            raise ValueError("已发布 npm 同版本不匹配；禁止覆盖、重试发布或移动 latest")
        if current is None:
            raise ValueError("版本存在但 latest 缺失；须人工核对")
        return {"version_state": "matching", "publish": "skip", "latest": "keep" if current >= wanted else "promotion_needs_separate_approval", "observed_latest": latest_version}
    if current is not None and current >= wanted:
        raise ValueError("版本缺失但 latest 不低于目标；禁止降低 latest 或猜测发布状态")
    return {"version_state": "absent", "publish": "not_performed", "latest": "do_not_change", "observed_latest": latest_version}


def github_plan(manifest: dict, release: dict | None, tag_commit: str | None) -> dict:
    if tag_commit is not None and tag_commit != manifest["source_commit"]:
        raise ValueError("远端标签指向其他提交；禁止移动或覆盖")
    if release is None:
        return {"release": "absent", "action": "await_reviewed_tag_and_draft" if tag_commit is None else "draft_creation_needs_separate_approval"}
    if not isinstance(release, dict):
        raise ValueError("已有 Release 不是对象；远端状态未知")
    if release.get("tag_name") != "v" + manifest["version"] or tag_commit is None:
        raise ValueError("已有 Release 的标签身份不能确认")
    # Existing releases are never updated, finalized or repaired by a retry.
    return {"release": "existing", "action": "do_not_modify", "immutable": release.get("immutable"), "draft": release.get("draft")}


def observe_npm(manifest: dict, reads: PublicReads):
    version, record = manifest["version"], manifest["artifacts"]["dsh"]
    published = reads.json(f"/{PACKAGE}/{version}", missing_ok=True)
    latest = reads.json(f"/{PACKAGE}/latest", missing_ok=True)
    npm = registry_plan(manifest, published, latest)
    if published is not None:
        url = f"{REGISTRY}/{PACKAGE}/-/{PACKAGE}-{version}.tgz"
        if published.get("dist", {}).get("tarball") != url:
            raise ValueError("npm tarball URL 不符合固定 registry 路径")
        data = reads.read(url, record["size"])
        if len(data) != record["size"] or hashlib.sha256(data).hexdigest() != record["sha256"] or "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode("ascii") != record["integrity"]:
            raise ValueError("实际 registry 归档与本次归档不一致；停止")
        npm["archive_bytes"] = "matching"
    return npm, latest


def observe_github(directory: Path, manifest: dict, reads: PublicReads):
    version = manifest["version"]
    tag = "v" + version
    ref = reads.json(f"/git/ref/tags/{tag}", github=True, missing_ok=True)
    tag_commit = None
    if ref is not None:
        obj = ref.get("object", {})
        for _ in range(5):
            if not isinstance(obj, dict) or not isinstance(obj.get("sha"), str) or not SHA.fullmatch(obj["sha"]):
                raise ValueError("标签 object 或 SHA 字段无效")
            if obj.get("type") == "commit":
                tag_commit = obj["sha"]
                break
            if obj.get("type") != "tag":
                raise ValueError("标签对象不能解析为提交")
            obj = reads.json(f"/git/tags/{obj['sha']}", github=True).get("object", {})
        if tag_commit is None:
            raise ValueError("标签解析深度超过上限")
    release = reads.json(f"/releases/tags/{tag}", github=True, missing_ok=True)
    github = github_plan(manifest, release, tag_commit)
    if release is not None:
        expected = {path.name: artifact_record(path) for path in directory.iterdir()}
        assets = release.get("assets", [])
        if not isinstance(assets, list) or any(not isinstance(asset, dict) or not isinstance(asset.get("name"), str) for asset in assets):
            raise ValueError("已有 Release 资产字段格式无效；远端状态未知")
        names = [asset.get("name") for asset in assets]
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("已有 Release 资产集合不同；禁止覆盖、删除或补传历史资产")
        for asset in assets:
            record = expected[asset["name"]]
            if asset.get("size") != record["size"] or asset.get("digest") != "sha256:" + record["sha256"]:
                raise ValueError("已有 Release 资产摘要不同或未知；禁止覆盖")
        github["asset_metadata"] = "matching_not_independently_downloaded"
    return github, release


def reconcile(directory: Path, manifest: dict, reads: PublicReads) -> dict:
    version = manifest["version"]
    npm, latest = observe_npm(manifest, reads)
    github, _ = observe_github(directory, manifest, reads)
    observed_again = reads.json(f"/{PACKAGE}/latest", missing_ok=True)
    if observed_again != latest:
        raise ValueError("核对期间 latest 已变化；结果不稳定，须重新只读核对")
    return {"mode": "read-only-rehearsal", "version": version, "source_commit": manifest["source_commit"], "npm": npm, "github": github, "remote_writes": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("verify-bundle", "reconcile"))
    parser.add_argument("--bundle-dir", required=True, type=Path)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--attempts", type=int, default=3)
    args = parser.parse_args()
    try:
        manifest = verify_bundle(args.bundle_dir, args.expected_commit, args.manifest_sha256)
        result = reconcile(args.bundle_dir, manifest, PublicReads(args.attempts)) if args.command == "reconcile" else {"mode": "local-verification", "version": manifest["version"], "source_commit": manifest["source_commit"], "verified": True, "remote_writes": False}
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, zipfile.BadZipFile) as exc:
        print(f"发布演练停止：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
