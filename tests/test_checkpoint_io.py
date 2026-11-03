import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from agent.capabilities import atomic_json, file_retry, read_json


@unittest.skipUnless(os.name == 'nt', 'Windows file sharing behavior')
class CheckpointIOTests(unittest.TestCase):
    def test_atomic_replace_survives_transient_lock_and_remains_readable(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'job.json'
            atomic_json(target, {'step': 1})
            original = Path.replace
            attempts = []
            def replace(path, destination):
                attempts.append(path)
                if len(attempts) < 3:
                    raise PermissionError('sharing violation')
                return original(path, destination)
            with patch.object(Path, 'replace', replace), patch('agent.capabilities.time.sleep'):
                atomic_json(target, {'step': 2})
            self.assertEqual(len(attempts), 3)
            self.assertEqual(read_json(target), {'step': 2})
            self.assertFalse(target.with_suffix('.tmp').exists())

    def test_permanent_denial_is_bounded_and_not_hidden(self):
        operation = Mock(side_effect=PermissionError('persistent denial'))
        with patch('agent.capabilities.time.sleep'):
            with self.assertRaises(PermissionError):
                file_retry(operation)
        self.assertEqual(operation.call_count, 10)

    def test_read_retries_a_transient_sharing_lock(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder)/'job.json'
            atomic_json(target, {'step': 4})
            original = Path.read_text
            attempts = []
            def read(path, *args, **kwargs):
                attempts.append(path)
                if len(attempts) == 1:
                    raise PermissionError('sharing violation')
                return original(path, *args, **kwargs)
            with patch.object(Path, 'read_text', read), patch('agent.capabilities.time.sleep'):
                self.assertEqual(read_json(target), {'step': 4})
            self.assertEqual(len(attempts), 2)
