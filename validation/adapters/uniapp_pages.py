"""Read registered UniApp routes from one configured Git snapshot."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import PurePosixPath

try:
    from ..evidence_snapshot import EvidenceError, git, safe_path
    from ..pinned_source import read_pinned_text
except ImportError:  # Direct invocation of validation/knowledge.py.
    from evidence_snapshot import EvidenceError, git, safe_path
    from pinned_source import read_pinned_text


def read_uniapp_manifest(repository: dict[str, str], manifest_path: str, *,
                         read_text: Callable[[dict[str, str], str], str | None] = read_pinned_text) -> tuple[str, str]:
    # Compatibility: Git normalizes <commit>:./path relative to its configured
    # repository directory. Normalize this argument, not stored evidence paths.
    path = manifest_path
    if path.startswith("./"):
        path = PurePosixPath(manifest_path).as_posix()
        if manifest_path.endswith(("/", "/.")) or not safe_path(path):
            raise ValueError(f"UniApp 页面清单路径无效：{manifest_path}")
        try:
            # Git resolved the old :./path syntax from the configured
            # directory, which need not be the checkout root.
            prefix = git(repository["path"], "rev-parse", "--show-prefix").removesuffix(b"\n").decode("utf-8")
        except (EvidenceError, UnicodeError) as exc:
            raise ValueError(f"固定提交中找不到 UniApp 页面清单：{manifest_path}") from exc
        path = prefix + path
    if not safe_path(path):
        raise ValueError(f"UniApp 页面清单路径无效：{manifest_path}")
    text = read_text(repository, path)
    if text is None:
        raise ValueError(f"固定提交中找不到 UniApp 页面清单：{manifest_path}")
    return path, text


def read_uniapp_pages(repository: dict[str, str], manifest_path: str, *,
                      read_text: Callable[[dict[str, str], str], str | None] = read_pinned_text) -> set[str]:
    path, text = read_uniapp_manifest(repository, manifest_path, read_text=read_text)
    return parse_uniapp_pages(text, path)


def parse_uniapp_pages(text: str, manifest_path: str) -> set[str]:
    try:
        manifest = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{manifest_path} 不是标准 JSON，需配置适配后的清单") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("pages"), list):
        raise ValueError(f"{manifest_path} 缺少 pages 列表")
    routes: set[str] = set()
    packages = [{"root": "", "pages": manifest["pages"]}]
    packages.extend(manifest.get("subPackages", []))
    for package in packages:
        if not isinstance(package, dict) or not isinstance(package.get("pages"), list):
            raise ValueError(f"{manifest_path} 的分包结构无效")
        root = str(package.get("root", "")).strip("/")
        for page in package["pages"]:
            if not isinstance(page, dict) or not isinstance(page.get("path"), str) or not page["path"]:
                raise ValueError(f"{manifest_path} 存在缺少 path 的页面")
            routes.add(f"{root}/{page['path']}".strip("/"))
    return routes
