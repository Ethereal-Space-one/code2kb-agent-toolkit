#!/usr/bin/env python3
"""Compare the installed extraction instructions to Git, without loading the plugin."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SKILL = Path("skills/extract-app-knowledge")


def verify_installed_skill(repo: Path, revision: str, installed_root: Path) -> tuple[str, int]:
    def git(*args: str) -> bytes:
        return subprocess.check_output(["git", "-C", str(repo), *args])

    commit = git("rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}").decode().strip()
    tree = git("ls-tree", "-rz", f"{commit}:{SKILL.as_posix()}")
    expected = {}
    for line in tree.split(b"\0"):
        if line:
            meta, raw_name = line.split(b"\t", 1)
            mode, kind, oid = meta.split()
            if kind != b"blob" or mode not in {b"100644", b"100755"}:
                raise ValueError(f"not a regular source file: {os.fsdecode(raw_name)}")
            expected[os.fsdecode(raw_name)] = oid.decode()
    if "SKILL.md" not in expected:
        raise ValueError("no extraction skill entry in the requested commit")

    directory = installed_root / SKILL
    if (installed_root / "skills").is_symlink() or directory.is_symlink() or not directory.is_dir():
        raise ValueError(f"missing or linked skill directory: {directory}")
    errors = []
    found = set()

    def walk_error(error: OSError) -> None:
        raise error

    for parent, folders, files in os.walk(directory, onerror=walk_error):
        for name in folders + files:
            path = Path(parent) / name
            relative = path.relative_to(directory).as_posix()
            if path.is_symlink() or (name in files and not path.is_file()):
                errors.append(f"not a regular installed path: {relative}")
            elif name in files:
                found.add(relative)
                if relative not in expected:
                    errors.append(f"unexpected: {relative}")
                elif path.read_bytes() != git("cat-file", "blob", expected[relative]):
                    errors.append(f"changed: {relative}")
    errors.extend(f"missing: {name}" for name in expected.keys() - found)
    if errors:
        raise ValueError("\n".join(sorted(errors)))
    return commit, len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True, help="release tag or exact source commit in this checkout")
    parser.add_argument("--installed-root", required=True, type=Path, help="toolkit directory actually selected by the host")
    args = parser.parse_args()
    try:
        commit, count = verify_installed_skill(ROOT, args.commit, args.installed_root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Skill verification failed: {error}", file=sys.stderr)
        return 1
    print(f"Matched {count} extraction skill files to {commit} (content only; not host activation).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
