"""Read fixed Git text for one command and retain only anchor line counts."""

from __future__ import annotations

import os
import subprocess


def read_pinned_text(repository: dict[str, str], path: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", repository["path"], "show", f"{repository['commit']}:{path}"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return None if result.returncode else result.stdout


class PinnedReads:
    def __init__(self) -> None:
        self._repository_paths: dict[str, str] = {}
        self._line_counts: dict[tuple[str, str, str], int] = {}

    def _key(self, repository: dict[str, str], path: str) -> tuple[str, str, str]:
        root = repository["path"]
        if root not in self._repository_paths:
            self._repository_paths[root] = os.path.realpath(root)
        return self._repository_paths[root], repository["commit"], path

    def read_text(self, repository: dict[str, str], path: str) -> str | None:
        # The inventory reads its manifest first. Retain its line count for
        # later anchors without keeping the parsed source text in memory.
        text = read_pinned_text(repository, path)
        if text is not None and "\x00" not in text:
            self._line_counts[self._key(repository, path)] = len(text.splitlines())
        return text

    def line_count(self, repository: dict[str, str], path: str) -> int | None:
        key = self._key(repository, path)
        if key not in self._line_counts:
            self.read_text(repository, path)
        return self._line_counts.get(key)
