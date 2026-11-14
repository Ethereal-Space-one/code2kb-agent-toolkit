"""Read-only evidence lookup from the audited current retrieval release."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
from urllib.parse import quote

try:
    from . import content_language
    from .retrieval_evaluate import lexical, load_units
    from .retrieval_model import RetrievalError, contained_file, digest, strict_json
except ImportError:
    import content_language
    from retrieval_evaluate import lexical, load_units
    from retrieval_model import RetrievalError, contained_file, digest, strict_json


ATX_HEADING = re.compile(r"(?m)^#{1,6}[ \t]+([^\n]+)")
PLAIN_HEADING = re.compile(r"[a-zA-Z0-9\u3400-\u4dbf\u4e00-\u9fff :：.。,，、!?！？()（）'’\-]+")
COMPLEX_HEADING_CONTEXT = re.compile(
    r"(?m)<|^[ \t]*(?:>|`{3,}|~{3,}|[=-]+[ \t]*$)|^[ \t]+#{1,6}[ \t]"
    r"|^(?:[ \t]*(?:[-+*]|[0-9]{1,9}[.)])[ \t]+)+(?:#|>|`{3,}|~{3,})"
)


def section_anchors(body: str) -> dict[str, tuple[str, str]]:
    """Resolve unambiguous plain ATX headings using GitHub-style anchors."""
    titles = [match[1].strip() for match in ATX_HEADING.finditer(body)]
    if COMPLEX_HEADING_CONTEXT.search(body) or any(not PLAIN_HEADING.fullmatch(title) for title in titles):
        return {}
    slugs = [re.sub(r"[^a-z0-9\u3400-\u4dbf\u4e00-\u9fff \-]", "", title.lower()).replace(" ", "-") for title in titles]
    if "" in slugs:
        return {}
    counts = Counter(slugs)
    keys = [title.strip("：:") for title in titles]
    key_counts = Counter(keys)
    # A duplicate heading can also claim another heading's numeric suffix.
    duplicates = [re.escape(slug) for slug, count in counts.items() if count > 1]
    return {key: (title, slug) for key, title, slug in zip(keys, titles, slugs)
            if counts[slug] == 1 and key_counts[key] == 1
            and not any(re.fullmatch(base + r"(?:-[0-9]+)+", slug) for base in duplicates)}


def source_locations(project: Path, base_view: str, unit: dict, source_hashes: dict[str, str],
                     anchor_cache: dict[str, dict[str, tuple[str, str]]], core) -> list[dict]:
    try:
        _, _, footer = content_language.split_sources(unit["body"])
    except ValueError:
        footer = ""
    headings = set(unit["meta"]["source_headings"].split(" | "))
    by_file = {}
    for line in footer.splitlines():
        if line.startswith("- "):
            source, separator, names = line[2:].partition(" · ")
            if separator:
                by_file.setdefault(source, set()).update(names.split(" | "))

    sources = unit["entry"]["source_documents"]
    locations = []
    for source in sources:
        path = f"发布/{base_view}/{source}"
        href = quote(path, safe="/")
        heading = None
        names = by_file.get(source, set())
        if not names and len(sources) == 1:
            names = headings
        if len(names) == 1 and names <= headings:
            title = next(iter(names))
            if path not in anchor_cache:
                _, body, original = core.parse_frontmatter(contained_file(project, path))
                if digest(original.encode("utf-8")) != source_hashes.get(source):
                    raise RetrievalError(f"检索出处与基础版本摘要不一致：{path}")
                anchor_cache[path] = section_anchors(body)
            if match := anchor_cache[path].get(title):
                heading, anchor = match
                href += "#" + quote(anchor, safe="")
        locations.append({"path": path, "heading": heading, "href": href})
    return locations


def query_current(project: Path, query: str, audience: str, top_k: int, core) -> dict:
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        raise RetrievalError("查询文本须为 1–1000 个字符")
    if audience not in {"business", "engineering"} or type(top_k) is not int or not 1 <= top_k <= 20:
        raise RetrievalError("检索受众或 top-k 无效")
    try:
        from .governance import Governance
        from .retrieval_audit import audit_in_release
    except ImportError:
        from governance import Governance
        from retrieval_audit import audit_in_release

    release = project / "发布"
    base = Governance(project, project / "知识源", {}, [], None, core).audit_release(None)
    release_id = base["release_id"]
    audit_in_release(release, release_id, require_ready=True)
    manifest_path = release / "检索清单" / f"{release_id}.json"
    manifest = strict_json(manifest_path)
    units = load_units(release, manifest)
    allowed = [unit for unit in units.values() if audience == "engineering" or unit["meta"]["audience"] == "business"]
    ranked = lexical(query.strip(), allowed, top_k)
    hits = []
    anchor_cache = {}
    for rank, unit_id in enumerate(ranked, start=1):
        unit = units[unit_id]
        meta, entry = unit["meta"], unit["entry"]
        base_view = "业务版" if meta["audience"] == "business" else "研发版"
        locations = source_locations(project, base_view, unit, base["views"][meta["audience"]]["files"], anchor_cache, core)
        hits.append({
            "rank": rank,
            "unit_id": unit_id,
            "module_id": meta["module_id"],
            "audience": meta["audience"],
            "topic": meta["topic"],
            "unit_path": entry["path"],
            "source_paths": [location["path"] for location in locations],
            "source_locations": locations,
            "text": unit["body"],
        })
    return {
        "schema_version": "0.1",
        "release_id": release_id,
        "base_registry_sha256": manifest["base_registry_sha256"],
        "retrieval_manifest_sha256": digest(manifest_path.read_bytes()),
        "audience": audience,
        "query": query.strip(),
        "retriever_id": "lexical-v1",
        "answerability": "not_assessed",
        "hits": hits,
    }
