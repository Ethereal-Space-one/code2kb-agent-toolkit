#!/usr/bin/env python3
"""Build audited plugin archives from a committed public source tree."""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

from check_markdown_links import main as check_markdown_links
from check_public_content import main as check_public_content

ROOT = Path(__file__).resolve().parents[1]
COMMON = (
    "VERSION", "LICENSE", "NOTICE", "README.md", "README.en.md", "SPEC.md",
    "CHANGELOG.md", "ROADMAP.md", "CONTRIBUTING.md", "CODE_OF_CONDUCT.md", "SECURITY.md",
    "pyproject.toml", "setup.py", "skills", "validation", "templates", "spec", "docs",
    "conformance", "adapters", "hosts", "examples", "assets", "scripts/benchmark_batch_review.py",
)
HOSTS = {
    "dsh": ("package.json", "index.mjs", "cordis.patch.yml", "dsh", "locale"),
    "claude": (".claude-plugin/plugin.json",),
    "codex": ("plugin.json",),
}
FORBIDDEN = {
    ".git", ".DS_Store", "__pycache__", ".env", ".npmrc", ".code2kb",
    ".code2kb-public-denylist", "node_modules",
}


def git(*args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(ROOT), *args])


def stage_commit(commit: str, stage: Path, target: str) -> None:
    source = git("archive", commit, "--", *COMMON, *HOSTS[target])
    with tarfile.open(fileobj=io.BytesIO(source), mode="r:") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if (
                not path.parts or path.is_absolute() or ".." in path.parts
                or "\\" in member.name or ":" in member.name
                or FORBIDDEN.intersection(path.parts)
                or path.suffix in {".pyc", ".pyo", ".tgz", ".zip"}
                or any(part.startswith(".env.") for part in path.parts)
            ):
                raise ValueError(f"插件包含禁止路径：{member.name}")
            if member.isdir():
                continue
            if not member.isfile():
                raise ValueError(f"插件包只能包含普通文件：{member.name}")
            destination = stage.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.extractfile(member) as source_file, destination.open("xb") as output:
                shutil.copyfileobj(source_file, output)


def staged_files(stage: Path) -> dict[str, Path]:
    return {path.relative_to(stage).as_posix(): path for path in sorted(stage.rglob("*")) if path.is_file()}


def build_npm(stage: Path, output: Path, commit: str) -> Path:
    manifest = stage / "package.json"
    package = json.loads(manifest.read_text(encoding="utf-8"))
    if package.get("private") is not True or package.get("files") != []:
        raise ValueError("源码中的 npm 清单必须保持 private: true 和空 files 列表")
    del package["private"]
    package["gitHead"] = commit
    package["files"] = sorted(staged_files(stage))
    manifest.write_text(json.dumps(package, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = subprocess.check_output(
        ["npm", "pack", "--ignore-scripts", "--json", "--pack-destination", str(output)], cwd=stage,
    )
    filename = json.loads(result)[0]["filename"]
    artifact = output / filename
    verify_npm(stage, artifact)
    return artifact


def verify_npm(stage: Path, artifact: Path) -> None:
    expected = staged_files(stage)
    with tarfile.open(artifact, mode="r:gz") as archive:
        for member in archive:
            if not member.isfile() or not member.name.startswith("package/"):
                raise ValueError(f"npm 产物含非预期条目：{member.name}")
            relative = member.name.removeprefix("package/")
            path = expected.pop(relative, None)
            if path is None or archive.extractfile(member).read() != path.read_bytes():
                raise ValueError(f"npm 产物条目新增、重复或内容变化：{relative}")
    if expected:
        raise ValueError(f"npm 产物缺少文件：{', '.join(sorted(expected))}")


def build_zip(stage: Path, output: Path, target: str, version: str) -> Path:
    artifact = output / f"code2kb-{target}-{version}.zip"
    with zipfile.ZipFile(artifact, mode="x", compression=zipfile.ZIP_DEFLATED) as archive:
        for relative, path in staged_files(stage).items():
            archive.writestr(relative, path.read_bytes())
    return artifact


def build(commit: str, target: str, output: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix="code2kb-package-") as temporary:
        work = Path(temporary)
        stage = work / "source"
        stage.mkdir()
        stage_commit(commit, stage, target)
        version = (stage / "VERSION").read_text(encoding="utf-8").strip()
        manifest = json.loads((stage / HOSTS[target][0]).read_text(encoding="utf-8"))
        if manifest["version"] != version:
            raise ValueError(f"{target} 的插件版本与 VERSION 不一致")
        if check_public_content(stage) or check_markdown_links(stage):
            raise ValueError("插件文件未通过公开内容或链接检查")
        artifact = build_npm(stage, work, commit) if target == "dsh" else build_zip(stage, work, target, version)
        destination = output / artifact.name
        with artifact.open("rb") as source, destination.open("xb") as result:
            shutil.copyfileobj(source, result)
        return destination


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", default="HEAD", help="提交或标签，解析后只读取该 Git 提交")
    parser.add_argument("--target", choices=(*HOSTS, "all"), default="all")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        commit = git("rev-parse", "--verify", "--end-of-options", f"{args.commit}^{{commit}}").decode().strip()
        output = args.output_dir.resolve()
        output.mkdir(parents=True, exist_ok=True)
        for target in HOSTS if args.target == "all" else (args.target,):
            print(f"{target}: {build(commit, target, output)}")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, tarfile.TarError) as exc:
        print(f"插件打包失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
