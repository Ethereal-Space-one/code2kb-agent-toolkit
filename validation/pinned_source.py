"""Read fixed Git text for one command and retain only anchor line counts."""

from __future__ import annotations

import os

try:
    from .evidence_snapshot import EvidenceError, decode_source_text, git, regular_blob_oid, safe_path
except ImportError:  # Direct invocation of validation/knowledge.py.
    from evidence_snapshot import EvidenceError, decode_source_text, git, regular_blob_oid, safe_path


def read_pinned_text(repository: dict[str, str], path: str) -> str | None:
    if not safe_path(path):
        return None
    repo = repository["path"]
    try:
        oid = regular_blob_oid(repo, repository["commit"], path)
        text = decode_source_text(git(repo, "cat-file", "blob", oid))
    except EvidenceError:
        return None
    # Preserve the reader's universal newlines; other Unicode separators are
    # characters within the physical line used by the raw-byte snapshot.
    return text.replace("\r\n", "\n").replace("\r", "\n")


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
        if text is not None:
            self._line_counts[self._key(repository, path)] = text.count("\n") + int(bool(text) and not text.endswith("\n"))
        return text

    def line_count(self, repository: dict[str, str], path: str) -> int | None:
        key = self._key(repository, path)
        if key not in self._line_counts:
            self.read_text(repository, path)
        return self._line_counts.get(key)
