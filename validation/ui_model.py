"""Optional, fact-backed UI interaction records embedded in a module spec.

This module validates authored records. It never executes source expressions,
discovers runtime states, or promotes the evidence level of an existing fact.
"""

from __future__ import annotations

from copy import deepcopy
import json
import re


SCHEMA = "c2kb-ui/0.1"
HEADING = "## 界面交互规格"
FACT_HEADER = "| fact_id | 单一结论与条件 | 证据等级 | 固定提交锚点 | 影响的知识文件 |"
VERIFIED_LEVELS = {"CODE_VERIFIED", "RUN_VERIFIED", "BUSINESS_CONFIRMED"}
ROOT_FIELDS = {"schema_version", "controls"}
CONTROL_FIELDS = {"control_id", "entry_id", "scope", "role", "label", "states", "transitions"}
STATE_FIELDS = {"state_id", "when", "presentation", "meaning", "fact_ids"}
TRANSITION_FIELDS = {"transition_id", "from", "trigger", "guard", "to", "effect", "feedback", "fact_ids"}
PRESENTATION_REQUIRED = {"visible", "enabled", "busy"}
PRESENTATION_FIELDS = PRESENTATION_REQUIRED | {"label", "feedback"}
EFFECTS = {"stay", "open_panel", "close_panel", "navigate", "external", "unknown"}
ID = re.compile(r"[A-Za-z][A-Za-z0-9_.-]*\Z")
CONTROL_ID = re.compile(r"UI-[A-Za-z0-9-]+\Z")
ENTRY_ID = re.compile(r"ENT-[A-Za-z0-9-]+\Z")
FACT_ID = re.compile(r"[A-Za-z][A-Za-z0-9-]+\Z")


class UIError(ValueError):
    pass


def _object(value, fields, where):
    if not isinstance(value, dict) or set(value) != fields:
        raise UIError(f"{where}: 界面交互字段无效")


def _text(value, where):
    if (not isinstance(value, str) or not value.strip()
            or any(char in value for char in "\x00\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029")):
        raise UIError(f"{where}: 须为非空单行文字")


def _identifier(value, pattern, where):
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise UIError(f"{where}: 界面交互 ID 无效")


def _unique_object(items):
    result = {}
    for key, value in items:
        if key in result:
            raise UIError(f"界面交互 JSON 包含重复字段：{key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise UIError(f"界面交互 JSON 不允许常量：{value}")


def parse_spec(spec):
    """Read one optional H2 section; headings inside code fences are examples."""
    lines = spec.body.splitlines()
    headings = []
    fence = None
    for index, line in enumerate(lines):
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if fence is not None:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= fence[1] and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = (marker[1][0], len(marker[1]))
            continue
        if re.match(r"^##[ \t]+", line):
            headings.append((index, line.rstrip()))
    selected = [(index, heading) for index, heading in headings if re.match(r"^##[ \t]+界面交互规格(?:[ \t]|$)", heading)]
    if not selected:
        return None
    if len(selected) != 1 or selected[0][1] != HEADING:
        raise UIError("界面交互规格须为唯一的固定 H2 章节")
    start = selected[0][0]
    stop = next((index for index, _ in headings if index > start), len(lines))
    section = "\n".join(lines[start + 1:stop]).strip()
    if len(section.encode("utf-8")) > 1024 * 1024:
        raise UIError("界面交互规格超过大小上限")
    match = re.fullmatch(r"```json[ \t]*\n([\s\S]*?)\n```", section)
    if match is None:
        raise UIError("界面交互规格须只包含一个完整的 json 代码块")
    try:
        value = json.loads(match[1], object_pairs_hook=_unique_object, parse_constant=_invalid_constant)
    except (json.JSONDecodeError, RecursionError) as exc:
        raise UIError("界面交互规格不是有效 JSON") from exc
    _object(value, ROOT_FIELDS, HEADING)
    if value["schema_version"] != SCHEMA:
        raise UIError("不支持的界面交互规格版本")
    return value


def _facts(value, fact_levels, where):
    if not isinstance(value, list) or not value:
        raise UIError(f"{where}: 须引用非空的已验证事实列表")
    seen = set()
    for fact_id in value:
        _identifier(fact_id, FACT_ID, where)
        if fact_id in seen or fact_levels.get(fact_id) not in VERIFIED_LEVELS:
            raise UIError(f"{where}: 事实重复、未定义或未验证：{fact_id}")
        seen.add(fact_id)


def _semantic_target(value, where):
    _text(value, where)
    # Targets are reader-facing destinations, never executable handlers, URLs,
    # repository paths, or internal API/METHOD identities.
    if (any(char in value for char in "\n\r/\\`{};=")
            or re.search(r"\b(?:ENT|API|METHOD|FACT)-[A-Za-z0-9-]+\b|\b\w+\s*\(|\b\w+\.(?:vue|tsx?|jsx?|php|java|py)\b", value)):
        raise UIError(f"{where}: 目标须为业务语义标签，不能是代码或路径")


def validate(data, *, module_id, entries, fact_levels, standard_version):
    """Validate only explicit records against current-module entries and facts."""
    _object(data, ROOT_FIELDS, HEADING)
    if data["schema_version"] != SCHEMA:
        raise UIError("不支持的界面交互规格版本")
    if standard_version != "c2kb-file/1":
        raise UIError("界面交互规格仅支持 c2kb-file/1，旧规范未启用时保持兼容")
    if not isinstance(data["controls"], list) or not data["controls"]:
        raise UIError("界面交互规格 controls 须为非空列表")
    owned_entries = {row[0] for row in entries if row[3] == module_id}
    controls = set()
    for control in data["controls"]:
        _object(control, CONTROL_FIELDS, "control")
        control_id = control["control_id"]
        _identifier(control_id, CONTROL_ID, "control_id")
        _identifier(control["entry_id"], ENTRY_ID, control_id)
        for name in ("scope", "role", "label"):
            _text(control[name], f"{control_id}.{name}")
        if control_id in controls or control["entry_id"] not in owned_entries:
            raise UIError(f"{control_id}: 控件身份重复，或入口未归属本模块")
        controls.add(control_id)
        if not isinstance(control["states"], list) or not control["states"]:
            raise UIError(f"{control_id}: states 须为非空列表")
        states = set()
        for state in control["states"]:
            _object(state, STATE_FIELDS, control_id)
            state_id = state["state_id"]
            _identifier(state_id, ID, f"{control_id}.state_id")
            if state_id in states:
                raise UIError(f"{control_id}: 状态 ID 重复：{state_id}")
            states.add(state_id)
            for name in ("when", "meaning"):
                _text(state[name], f"{control_id}.{state_id}.{name}")
            presentation = state["presentation"]
            if not isinstance(presentation, dict) or not PRESENTATION_REQUIRED <= set(presentation) <= PRESENTATION_FIELDS:
                raise UIError(f"{control_id}.{state_id}: presentation 须独立记录 visible/enabled/busy")
            for name in PRESENTATION_REQUIRED:
                value = presentation[name]
                if type(value) is not bool and (not isinstance(value, str) or value not in {"unknown", "not_applicable"}):
                    raise UIError(f"{control_id}.{state_id}.{name}: 仅支持布尔值、unknown 或 not_applicable")
            for name in ("label", "feedback"):
                if name in presentation:
                    _text(presentation[name], f"{control_id}.{state_id}.{name}")
            _facts(state["fact_ids"], fact_levels, f"{control_id}.{state_id}")
        if not isinstance(control["transitions"], list):
            raise UIError(f"{control_id}: transitions 须为列表")
        transitions = set()
        for transition in control["transitions"]:
            _object(transition, TRANSITION_FIELDS, control_id)
            transition_id = transition["transition_id"]
            _identifier(transition_id, ID, f"{control_id}.transition_id")
            if transition_id in transitions:
                raise UIError(f"{control_id}: 转换 ID 重复：{transition_id}")
            transitions.add(transition_id)
            for name in ("from", "to"):
                _identifier(transition[name], ID, f"{control_id}.{transition_id}.{name}")
                if transition[name] not in states:
                    raise UIError(f"{control_id}.{transition_id}: 转换引用本控件未定义状态：{transition[name]}")
            for name in ("trigger", "guard", "feedback"):
                _text(transition[name], f"{control_id}.{transition_id}.{name}")
            effect = transition["effect"]
            _object(effect, {"kind", "target"}, f"{control_id}.{transition_id}.effect")
            if not isinstance(effect["kind"], str) or effect["kind"] not in EFFECTS:
                raise UIError(f"{control_id}.{transition_id}: 未支持的界面动作类型")
            if effect["kind"] == "navigate":
                _identifier(effect["target"], ENTRY_ID, f"{control_id}.{transition_id}.target")
                if effect["target"] not in owned_entries:
                    raise UIError(f"{control_id}.{transition_id}: 导航目标入口未归属本模块")
            else:
                _semantic_target(effect["target"], f"{control_id}.{transition_id}.target")
            _facts(transition["fact_ids"], fact_levels, f"{control_id}.{transition_id}")


def analyze_spec(spec, outline, core, standard_version):
    """Return the raw contract after validation, or None for an old/plain spec."""
    data = parse_spec(spec)
    if data is None:
        return None
    fact_levels = {row[0]: row[2] for row in core.table_rows(spec.body, "## 入口与调用链", FACT_HEADER)}
    validate(data, module_id=spec.module_id, entries=outline.entries,
             fact_levels=fact_levels, standard_version=standard_version)
    return data


def fact_dependencies(data, *, entries):
    """Canonical per-fact dependencies, so unrelated old claims keep old hashes."""
    result = {}
    entry_rows = {row[0]: list(row) for row in entries}
    for control in sorted(data["controls"], key=lambda item: item["control_id"]):
        identity = {name: control[name] for name in sorted(CONTROL_FIELDS - {"states", "transitions"})}
        states = {}
        for state in control["states"]:
            normalized = deepcopy(state)
            normalized["fact_ids"] = sorted(normalized["fact_ids"])
            states[state["state_id"]] = normalized
        for state_id in sorted(states):
            record = {"schema_version": SCHEMA, "control": identity, "state": states[state_id]}
            for fact_id in states[state_id]["fact_ids"]:
                result.setdefault(fact_id, []).append(record)
        for transition in sorted(control["transitions"], key=lambda item: item["transition_id"]):
            normalized = deepcopy(transition)
            normalized["fact_ids"] = sorted(normalized["fact_ids"])
            record = {"schema_version": SCHEMA, "control": identity, "transition": normalized,
                      "from_state": states[transition["from"]], "to_state": states[transition["to"]]}
            if normalized["effect"]["kind"] == "navigate":
                target = normalized["effect"]["target"]
                if target not in entry_rows:
                    raise UIError(f"{control['control_id']}.{transition['transition_id']}: 导航目标入口未定义")
                # Rendering resolves the entry ID to its current reader-facing
                # name. Its identity/evidence must also remain bound to review.
                record["navigation_target"] = deepcopy(entry_rows[target])
            for fact_id in normalized["fact_ids"]:
                result.setdefault(fact_id, []).append(record)
    return result
