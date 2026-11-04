"""Small presentation vocabulary; protocol tokens and paths are never translated."""

from __future__ import annotations

import re


DEFAULT = "zh-CN"
SUPPORTED = frozenset({DEFAULT, "en"})


def declared(meta: dict) -> str:
    value = meta.get("content_language", DEFAULT)
    if not isinstance(value, str) or value not in SUPPORTED:
        raise ValueError("content_language must be zh-CN or en")
    return value


def choose(language: str, chinese: str, english: str) -> str:
    return english if language == "en" else chinese


LABELS = {
    "模块概览": "Overview", "功能与范围": "Features and scope", "业务流程": "Workflow",
    "规则与限制": "Rules and limitations", "常见问答": "Frequently asked questions",
    "业务意图": "Business intent", "技术实现": "Implementation", "接口与调用": "APIs and calls",
    "方法与源码": "Methods and source", "事实编号对照": "Fact reference", "术语表": "Glossary",
    "目录": "Contents", "功能大纲": "Functional inventory", "发布信息": "Release information",
}


def label(stem: str, language: str) -> str:
    return LABELS.get(stem, stem) if language == "en" else stem


# These are authoring conventions, not a natural-language classifier.
SHARED_EN = {"applicability", "confirmed conditions", "answer boundaries", "unverified outcomes"}
GENERIC_EN = SHARED_EN | {"notes", "overview", "main workflow", "branches and failures", "platform and role differences"}
INDEX_EN = {"contents", "fact reference", "index", "api index", "method index"}
UNKNOWN_EN = re.compile(
    r"\b(?:unknown|unverified|not (?:been )?(?:verified|confirmed|tested|known)|cannot (?:yet )?(?:be )?determined)\b",
    re.IGNORECASE,
)
RISK_EN = re.compile(r"\b(?:permissions?|authorization|ownership|amounts?|quotas?|metrics?|status|states?)\b", re.IGNORECASE)
BUSINESS_EN = re.compile(
    r"\b(?:source (?:code|repository)|internal (?:endpoint|fact (?:id|identifier))|database field|"
    r"transaction annotation|self[- ]proxy|review (?:queue|package)|release manifest)\b",
    re.IGNORECASE,
)
SOURCES = {DEFAULT: "## 出处", "en": "## Sources"}


def is_unknown(line: str) -> bool:
    return any(term in line for term in ("未知", "不能确定", "未验证", "待确认", "不清楚")) or bool(UNKNOWN_EN.search(line))


def split_sources(body: str) -> tuple[str, str, str]:
    """Separate the generated footer, preserving any same-named source-text heading."""
    matches = list(re.finditer(r"\n## (?:出处|Sources)\n\n", body))
    if not matches:
        raise ValueError("Retrieval unit is missing its source section")
    match = matches[-1]
    return body[:match.start()], match[0], body[match.end():]
