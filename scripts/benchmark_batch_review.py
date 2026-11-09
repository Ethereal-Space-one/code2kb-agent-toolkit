#!/usr/bin/env python3
"""Compare only final redundant impact calls, using disposable synthetic inputs.

No review, approval or preparation is skipped in a real project by this script.
Fixture creation is excluded from timing; only empty final impacts + check versus
one final check are measured. No credentials, services or private data are used.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'validation/tests'))
import test_knowledge as fixture
from governance import Governance, replace_meta


def snapshot(project):
    return {p.relative_to(project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in project.rglob('*') if p.is_file()
            and not {'.git', '.code2kb'}.intersection(p.relative_to(project).parts)}


def make_batch(case, count):
    originals = {p.name: p.read_text(encoding='utf-8') for p in case.module.glob('*.md')
                 if p.name != '发布清单.md'}
    outline = (case.source / '功能大纲.md').read_text(encoding='utf-8')
    metadata = outline.split('---', 2)[1]
    shutil.rmtree(case.source)
    modules, entries, audiences, ids = [], [], [], []
    for index in range(1, count + 1):
        module_id, name = f'example.batch.unit{index}', f'Unit{index}'
        ids.append(module_id)
        replacements = {'example.order.query': module_id,
                        'ENT-001': f'ENT-{index:04d}1', 'ENT-002': f'ENT-{index:04d}2'}
        for filename, text in originals.items():
            text = re.sub('|'.join(re.escape(key) for key in replacements),
                          lambda match: replacements[match.group(0)], text)
            text = replace_meta(text, {'review_status': 'draft', 'reviewed_by': None, 'reviewed_at': None, 'approval_note': None})
            fixture.write(case.source / 'Batch' / name / filename, text)
        modules.append(f'| {module_id} | Batch | {name} | Synthetic query | 知识草稿 |')
        for suffix, kind, label, anchor in (('1', '按钮', 'Query', 'frontend:dummy.txt:1'), ('2', '页面', 'Page', 'frontend:src/pages.json:1')):
            entry = f'ENT-{index:04d}{suffix}'
            entries.append(f'| {entry} | {kind} | {label} | {module_id} | {anchor} | 已归类 |')
            audiences.append(f'| {entry} | 用户操作 | 范围内 |')
    fixture.write(case.source / '功能大纲.md', '---' + metadata + '---\n\n# Synthetic batch\n\n'
        + '## 模块清单\n\n| module_id | 业务域 | 子模块 | 发现入口 | 状态 |\n| --- | --- | --- | --- | --- |\n' + '\n'.join(modules)
        + '\n\n## 入口证据索引\n\n| entry_id | 类型 | 入口或动作 | module_id | 证据 | 状态 |\n| --- | --- | --- | --- | --- | --- |\n' + '\n'.join(entries)
        + '\n\n## 入口受众\n\n| entry_id | 受众 | 范围 |\n| --- | --- | --- |\n' + '\n'.join(audiences)
        + '\n\n## 盘点覆盖说明\n\n合成页面、按钮、非按钮、前端调用、后端；只度量重复校验，不声称语义完整。\n')
    config_path = case.project / '知识库配置.json'
    config = json.loads(config_path.read_text())
    config.pop('inventory_adapter')
    fixture.write(config_path, json.dumps(config, ensure_ascii=False))
    source, config = fixture.core.read_config(case.project)
    docs, inventory = fixture.core.read_documents(source)
    governance = Governance(case.project, source, config, docs, inventory, fixture.core)
    # Synthetic recorded projections only; not an assertion of independent review.
    for module in ids:
        governance.confirm_claims(module)
    return ids


def replay(case, ids, mode):
    commands = [('impact', '--module-id', module) for module in ids] if mode == 'repeated' else []
    commands.append(('check',))
    before = snapshot(case.project)
    started = datetime.now(timezone.utc).isoformat()
    wall = time.perf_counter()
    results = []
    final = None
    for command in commands:
        command_started = datetime.now(timezone.utc).isoformat()
        begin = time.perf_counter()
        result = case.run_cli(*command)
        elapsed = time.perf_counter() - begin
        if result.returncode:
            raise RuntimeError(result.stderr)
        data = json.loads(result.stdout)
        if command[0] == 'impact':
            if data['pending_impacts'] != []:
                raise AssertionError('Fixture is not at a stable zero-impact boundary')
        else:
            if data['pending_claim_impacts'] != 0:
                raise AssertionError('Final check has unresolved impacts')
            final = data
        results.append({'command': list(command), 'started_at': command_started,
                        'ended_at': datetime.now(timezone.utc).isoformat(),
                        'elapsed_seconds': round(elapsed, 6), 'exit_code': result.returncode})
    seconds = time.perf_counter() - wall
    if before != snapshot(case.project):
        raise AssertionError('Read-only replay changed project inputs')
    return {'mode': mode, 'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
            'wall_seconds': round(seconds, 6), 'commands': results, 'final_check': final,
            'input_digest': hashlib.sha256(json.dumps(before, sort_keys=True).encode()).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules', type=int, nargs='+', default=[12, 96])
    parser.add_argument('--repetitions', type=int, default=3)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if min(args.modules) < 1 or args.repetitions < 1:
        parser.error('Module counts and repetitions must be positive')
    tool_files = [*sorted((ROOT / 'validation').rglob('*.py')), Path(__file__).resolve()]
    tool_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tool_files}
    report = {'scope': 'synthetic_final_check_only', 'python': platform.python_version(),
              'platform': platform.system() + ' ' + platform.machine(), 'version': (ROOT / 'VERSION').read_text().strip(),
              'head': subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
              'implementation_sha256': tool_hashes, 'batches': []}
    for count in args.modules:
        case = fixture.KnowledgeTests()
        try:
            case.setUp()
            case.project = case.project.resolve()
            case.source = case.source.resolve()
            case.module = case.module.resolve()
            ids = make_batch(case, count)
            runs = []
            for repeat in range(args.repetitions):
                for mode in (('repeated', 'batch') if repeat % 2 == 0 else ('batch', 'repeated')):
                    run = replay(case, ids, mode)
                    if runs and run['final_check'] != runs[0]['final_check']:
                        raise AssertionError('Final gate results differ')
                    runs.append(run)
                    print(f'{count} modules: {mode} {run["wall_seconds"]:.3f}s', file=sys.stderr, flush=True)
            summary = {mode: {'command_count': len(next(r for r in runs if r['mode'] == mode)['commands']),
                              'median_seconds': statistics.median(r['wall_seconds'] for r in runs if r['mode'] == mode),
                              'range_seconds': [min(r['wall_seconds'] for r in runs if r['mode'] == mode), max(r['wall_seconds'] for r in runs if r['mode'] == mode)]}
                       for mode in ('repeated', 'batch')}
            report['batches'].append({'module_count': count, 'summary': summary, 'runs': runs})
        finally:
            case.doCleanups()
    if tool_hashes != {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tool_files}:
        raise AssertionError('Tool inputs changed during the benchmark; discard these timings')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
