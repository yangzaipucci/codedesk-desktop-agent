import asyncio
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from agent.capabilities import project_guidance
from agent.hooks import Hooks,PolicyDenied
from agent.reviewer import diff_arguments
from agent.skills import Skills
from agent.tools import Tools


class ContractTests(unittest.TestCase):
    def test_description_only_portable_skill_and_parent_rules(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);work=root/'project';nested=work/'src';nested.mkdir(parents=True)
            state=root/'state';state.mkdir()
            (state/'AGENTS.md').write_text('Global rules.',encoding='utf-8')
            (work/'AGENTS.md').write_text('Parent project rules.',encoding='utf-8')
            package=work/'skills'/'portable';package.mkdir(parents=True)
            (package/'SKILL.md').write_text('---\nname: portable\ndescription: Use this when 用户说“只在此时触发”。\n---\n先读再检查。\n',encoding='utf-8')
            registry=Skills(work,state)
            self.assertEqual(registry.select('只在此时触发'),['portable'])
            self.assertEqual(registry.select('不要只在此时触发'),[])
            self.assertEqual(registry.loaded,[])
            self.assertIn('先读再检查',registry.use_skill('portable')['text'])
            rules,sources=project_guidance(nested,state)
            self.assertEqual([s['layer'] for s in sources],['global','project'])
            self.assertIn('Parent project rules',rules)

    def test_force_push_is_policy_only_and_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            hook=Hooks(folder,folder)
            for command in ['git push --force','git push -f origin main','git -C project push --force-with-lease','git push origin +main','git reset --hard']:
                with self.subTest(command=command):
                    with self.assertRaises(PolicyDenied) as error:hook.before('bash',{'command':command})
                    self.assertIn('替代方案',str(error.exception))
            with patch.dict(os.environ,{'ENABLE_HOOKS':'0'}):
                hook.before('bash',{'command':'git push --force'})

    def test_reviewer_cannot_turn_diff_into_shell_or_external_command(self):
        with tempfile.TemporaryDirectory() as folder:
            tools=Tools(Path(folder),Path(folder)/'state')
            for command in ['git status','git diff; echo bad','git diff --output=secret','git diff --ext-diff','git diff -- ../outside','git diff $(echo bad)','git diff | powershell']:
                with self.subTest(command=command):
                    with self.assertRaises(ValueError):diff_arguments(command,tools)
            self.assertIn('--no-ext-diff',diff_arguments('git diff --stat',tools))


class CacheTests(unittest.IsolatedAsyncioTestCase):
    async def test_same_size_same_timestamp_repair_uses_source(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);tools=Tools(root,root/'state')
            code=root/'maths.py';test=root/'test_maths.py'
            test.write_text('import unittest\nfrom maths import value\nclass T(unittest.TestCase):\n def test_value(self): self.assertEqual(value(),0)\n',encoding='utf-8')
            code.write_text('def value(): return 1\n',encoding='utf-8')
            original=code.stat().st_mtime_ns
            red=await tools.hooks.after_edit('maths.py',tools)
            code.write_text('def value(): return 0\n',encoding='utf-8');os.utime(code,ns=(original,original))
            green=await tools.hooks.after_edit('maths.py',tools)
            self.assertEqual((red['status'],green['status']),('failed','passed'))
            self.assertEqual(len(red['summary'].splitlines()),3)
            self.assertNotIn('Traceback',red['summary'])
