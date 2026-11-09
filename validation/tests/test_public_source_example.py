"""The committed-source sample must survive command additions and formatting."""
import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'examples'))
from check_runner_public_source import command_anchor


class PublicSourceAnchorTests(unittest.TestCase):
    def test_added_commands_and_formatting_keep_exact_anchor(self):
        for source, expected in (
            ('ACTIONS = ("check", "publish")\n', 1),
            ('ACTIONS = (\n    "check", "preflight", "publish",\n)\n', 2),
            ("# 'check' is a comment\nACTIONS = ['preflight',\n 'check',\n 'publish']\n", 3),
        ):
            with self.subTest(source=source):
                self.assertEqual(command_anchor(source), expected)

    def test_missing_command_does_not_use_unrelated_string(self):
        for source in ('OTHER = ("check", "publish")\n', 'ACTIONS = ("publish",)\nTEXT = "check"\n'):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'does not declare'):
                command_anchor(source)
