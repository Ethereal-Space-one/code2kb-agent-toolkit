"""Render reviewed factual clauses for each audience without model rewriting."""

from __future__ import annotations

try:
    from . import content_language
except ImportError:
    import content_language


HEADER = "| fact_id | 适用条件 | 结论 | 例外与失败 | 未知边界 |"
FACT_HEADER = "| fact_id | 单一结论与条件 | 证据等级 | 固定提交锚点 | 影响的知识文件 |"


class FactRenderError(ValueError):
    pass


def normalized_facts(spec, core) -> dict[str, dict]:
    if "## 规范化事实" not in spec.body:
        return {}
    raw = {row[0]: row for row in core.table_rows(spec.body, "## 入口与调用链", FACT_HEADER)}
    result = {}
    for fact_id, condition, conclusion, exception, unknown in core.table_rows(spec.body, "## 规范化事实", HEADER):
        if fact_id in result or fact_id not in raw:
            raise FactRenderError("规范化事实编号重复或未在主事实表登记")
        if any(not value or "\n" in value for value in (condition, conclusion, exception, unknown)):
            raise FactRenderError("规范化事实条件、结论、例外或未知不能为空；没有时写 无")
        if conclusion not in raw[fact_id][1]:
            raise FactRenderError("规范化事实结论与主事实表不一致")
        result[fact_id] = {
            "fact_id": fact_id, "condition": condition, "conclusion": conclusion,
            "exception": exception, "unknown": unknown,
            "level": raw[fact_id][2], "source_anchors": raw[fact_id][3],
        }
    return result


def render_topic(topic: dict, fact_ids: list[str], facts: dict[str, dict], *, language: str = content_language.DEFAULT) -> dict:
    if not fact_ids or any(fact_id not in facts for fact_id in fact_ids):
        raise FactRenderError("主题缺少已规范化且已复核的事实")
    ordered = [facts[fact_id] for fact_id in sorted(set(fact_ids))]
    conditions = [item["condition"] for item in ordered if item["condition"] != "无"]
    conclusions = [item["conclusion"] for item in ordered]
    exceptions = [item["exception"] for item in ordered if item["exception"] != "无"]
    unknowns = [item["unknown"] for item in ordered if item["unknown"] != "无"]
    def section(name: str, values: list[str]) -> str:
        return f"## {name}\n\n" + "\n".join(f"- {value}" for value in values) + "\n\n" if values else ""
    def title(zh, en):
        return content_language.choose(language, zh, en)
    common = (section(title("适用条件", "Applicability"), conditions) + section(title("结论", "Conclusions"), conclusions)
              + section(title("例外与失败", "Branches and failures"), exceptions) + section(title("仍不能确定", "Unverified outcomes"), unknowns)).rstrip() + "\n"
    engineering = common + "\n" + title("## 事实与源码", "## Facts and source") + "\n\n" + "\n".join(
        f"- {item['fact_id']}（{item['level']}）：{item['source_anchors']}" for item in ordered
    ) + "\n"
    retrieval = (common if topic["audience"] == "business" else engineering).rstrip()
    retrieval += f"\n\n{content_language.SOURCES[language]}\n\n- {topic['source_document']} · {topic['source_heading']}\n"
    return {
        "topic_id": topic["topic_id"], "audience": topic["audience"],
        "fact_ids": sorted(set(fact_ids)), "business": common,
        "engineering": engineering, "retrieval": retrieval,
    }


def render_mapped(spec, mapping: dict, core, external_specs: dict | None = None, *, language: str = content_language.DEFAULT) -> list[dict]:
    facts = normalized_facts(spec, core)
    if external_specs:
        for module_id, external in external_specs.items():
            if module_id == spec.module_id:
                continue
            for fact_id, item in normalized_facts(external, core).items():
                qualified = f"{module_id}#{fact_id}"
                facts[qualified] = {**item, "fact_id": qualified}
    linked: dict[str, list[str]] = {}
    for link in mapping["links"]:
        if link["from_type"] == "fact" and link["to_type"] == "topic" and link["status"] == "verified":
            linked.setdefault(link["to_id"], []).append(link["from_id"])
    return [render_topic(topic, linked[topic["topic_id"]], facts, language=language) for topic in mapping["topics"] if topic["topic_id"] in linked]


def render_ui(spec, model: dict, core, entry_names: dict, *, language: str = content_language.DEFAULT) -> list[dict]:
    """Render review candidates from a validated UI block; this never publishes."""
    details = {row[0]: row for row in core.table_rows(spec.body, "## 入口与调用链", FACT_HEADER)}
    normalized = normalized_facts(spec, core)
    zh = language != "en"
    dimensions = {
        "visible": ("显示", "Visible"), "enabled": ("已启用", "Enabled"), "busy": ("等待中", "Busy"),
    }
    values = {
        True: ("是", "yes"), False: ("否", "no"),
        "unknown": ("未知", "unknown"), "not_applicable": ("不适用", "not applicable"),
    }
    effect_labels = {
        "stay": ("留在", "Stay at"), "open_panel": ("打开", "Open"), "close_panel": ("关闭", "Close"),
        "navigate": ("前往", "Navigate to"), "external": ("外部交互", "External interaction"),
        "unknown": ("结果未验证", "Result unverified"),
    }

    def title(pair):
        return pair[0 if zh else 1]

    def bounds(ids):
        clauses = []
        for key, zh_label, en_label in (
            ("condition", "适用条件", "Applicability"),
            ("exception", "例外与失败", "Exceptions and failures"),
            ("unknown", "仍不能确定", "Unverified outcomes"),
        ):
            texts = dict.fromkeys(normalized[ref][key] for ref in ids if ref in normalized and normalized[ref][key] != "无")
            clauses.extend(f"  - {zh_label if zh else en_label}：{text}" for text in texts)
        return clauses

    def heading(text):
        return " ".join(text.split())

    segments = []
    for control in model["controls"]:
        display = f"{heading(control['scope'])} · {heading(control['label'])}"
        lines = [f"## {display}", ""]
        states = {item["state_id"]: item["when"] for item in control["states"]}
        refs = set()
        for item in control["states"]:
            refs.update(item["fact_ids"])
            presentation = item["presentation"]
            summary = ("；" if zh else "; ").join(
                f"{title(label)}：{title(values[presentation[key]])}" for key, label in dimensions.items()
            )
            line = f"- {item['when']}：{item['meaning']}。{summary}。" if zh else f"- {item['when']}: {item['meaning']}. {summary}."
            lines.append(line)
            for key, labels in (("label", ("文案", "Label")), ("feedback", ("反馈", "Feedback"))):
                if key in presentation:
                    lines.append(f"  - {title(labels)}：{presentation[key]}")
            lines.extend(bounds(item["fact_ids"]))
        for item in control["transitions"]:
            refs.update(item["fact_ids"])
            effect = item["effect"]
            target = entry_names[effect["target"]] if effect["kind"] == "navigate" else effect["target"]
            outcome = f"{title(effect_labels[effect['kind']])}：{target}"
            if zh:
                lines.append(f"- 在「{states[item['from']]}」，当「{item['guard']}」并触发「{item['trigger']}」时，转为「{states[item['to']]}」。{outcome}。反馈：{item['feedback']}")
            else:
                lines.append(f"- From “{states[item['from']]}”: on “{item['trigger']}” if “{item['guard']}”, move to “{states[item['to']]}”. {outcome}. Feedback: {item['feedback']}")
            lines.extend(bounds(item["fact_ids"]))
        business = "\n".join(lines).rstrip() + "\n"
        evidence_heading = "证据与源码" if zh else "Evidence and source"
        engineering = business + f"\n### {evidence_heading}\n\n" + "\n".join(
            f"- {ref}（{details[ref][2]}）：{details[ref][3]}" for ref in sorted(refs)
        ) + "\n"
        segments.append({"control_id": control["control_id"], "fact_ids": sorted(refs),
                         "business": business, "engineering": engineering})
    return segments
