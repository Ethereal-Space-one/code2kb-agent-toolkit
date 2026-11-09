"""Early structure checks must never certify review or mutate the project."""
from __future__ import annotations

import hashlib
import json
import unittest

import test_knowledge as fixture
import test_content_language as english

EN_MODULE = english.MODULE

MODULE = "example.order.query"


class PreflightTests(unittest.TestCase):
    setUp = fixture.KnowledgeTests.setUp
    run_cli = fixture.KnowledgeTests.run_cli

    def snapshot(self):
        return {p.relative_to(self.project).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in self.project.rglob('*') if p.is_file() and '.git' not in p.parts}

    def preflight(self):
        return self.run_cli('preflight', '--module-id', MODULE)

    def prepare(self):
        return self.run_cli('prepare', '--module-id', MODULE, '--refresh', '--business-topics', '查询', '--business-unknowns', '运行表现', '--business-keywords', '查询')

    def test_read_only_pending_impacts_and_failed_qa_are_not_approval(self):
        path = self.module / '功能与范围.md'
        fixture.write(path, path.read_text() + '\n仍须确认实际运行表现。\n')
        spec = self.module / '结构化规格.md'
        fixture.write(spec, spec.read_text().replace('| 已说明 | 通过 |', '| 未核实 | 待复核 |'))
        before = self.snapshot()
        impacts = self.run_cli('impact')
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        self.assertIn('qa_results', report['not_checked'])
        self.assertIn('impact_clear', report['not_checked'])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(impacts.stdout, self.run_cli('impact').stdout)
        self.assertNotEqual(self.prepare().returncode, 0)
        # Recording digests cannot make the failed question case pass formal prepare.
        self.assertEqual(self.run_cli('confirm-claims', '--module-id', MODULE).returncode, 0)
        failure = self.prepare()
        self.assertNotEqual(failure.returncode, 0)
        self.assertIn('问答自测未通过', failure.stderr)

    def test_unfinished_other_module_does_not_block_local_check(self):
        fixture.write(self.source / '销售/订单/模块概览.md', '# Unfinished draft\n')
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotEqual(self.run_cli('check').returncode, 0)
        self.assertNotEqual(self.prepare().returncode, 0)

    def test_shared_structure_failures_match_prepare(self):
        for name, old, new, error in (
            ('技术实现.md', 'backend=' + self.repos['backend']['commit'] + ', ', '', 'source_revisions'),
            ('接口与调用.md', '| 已匹配 |', '| 待核查 |', '一致'),
            ('技术实现.md', '## 说明', '## FACT-999', '事实编号未在'),
            ('功能与范围.md', '## 说明', '## 说明\n\n[详情](不存在.md)', '链接目标未发布'),
        ):
            with self.subTest(name=name, error=error):
                path = self.module / name
                original = path.read_text()
                fixture.write(path, original.replace(old, new))
                try:
                    for result in (self.preflight(), self.prepare()):
                        self.assertNotEqual(result.returncode, 0)
                        self.assertIn(error, result.stderr)
                finally:
                    fixture.write(path, original)

    def test_cross_module_references_are_explicitly_deferred(self):
        path = self.module / '技术实现.md'
        fixture.write(path, path.read_text() + '\napp.sales.order#FACT-999\n[相关](../../销售/订单/技术实现.md)\n')
        result = self.preflight()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('cross_module_consistency', json.loads(result.stdout)['not_checked'])
        failure = self.prepare()
        self.assertNotEqual(failure.returncode, 0)
        self.assertIn('事实编号未在', failure.stderr)

    def test_unknown_module_and_missing_required_file_fail(self):
        self.assertNotEqual(self.run_cli('preflight', '--module-id', '../../outside').returncode, 0)
        result = self.run_cli('preflight', '--module-id', MODULE, '--files', '模块概览.md')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('缺少', result.stderr)

    def test_changed_and_deleted_bindings_still_require_review(self):
        spec = self.module / '结构化规格.md'
        original = spec.read_text()
        for content in (original.replace('用户可提交查询', '用户需满足额外条件才能查询'),
                        original.replace('| 功能与范围.md |', '| 模块概览.md |')):
            fixture.write(spec, content)
            report = self.run_cli('check')
            self.assertNotEqual(report.returncode, 0)
            self.assertIn('发布清单已过期', report.stderr)
            self.assertTrue(json.loads(self.run_cli('impact').stdout)['pending_impacts'])
            before = self.run_cli('impact').stdout
            self.assertEqual(self.preflight().returncode, 0)
            self.assertEqual(before, self.run_cli('impact').stdout)
            self.assertNotEqual(self.prepare().returncode, 0)
        fixture.write(spec, original)


class EnglishPreflightTests(unittest.TestCase):
    setUp = english.EnglishKnowledgeTests.setUp
    run_cli = english.EnglishKnowledgeTests.run_cli
    assert_cli = english.EnglishKnowledgeTests.assert_cli
    document = english.EnglishKnowledgeTests.document

    def test_full_and_compact_preview_use_real_english_headings(self):
        for profile in ('full', 'compact'):
            fixture.write(self.project / 'Code2KB工程配置.json', json.dumps({'schema_version': '0.1', 'content_profile': profile}))
            before = {p: p.read_bytes() for p in self.project.rglob('*.md')}
            result = self.assert_cli('preflight', '--module-id', EN_MODULE)
            self.assertTrue(result['navigation_preview'])
            self.assertTrue(result['navigation_preview'][0]['titles'])
            self.assertEqual(before, {p: p.read_bytes() for p in self.project.rglob('*.md')})
            self.assertEqual(english.EnglishKnowledgeTests.prepare(self)['module_id'], EN_MODULE)
