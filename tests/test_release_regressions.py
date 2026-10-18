import json
from pathlib import Path
import subprocess
import sys

from support import CLIBase, example


class TimestampOffsets(CLIBase):
    def test_rejects_out_of_range_offsets_on_every_input_timestamp(self):
        self.initialize()
        for offset in ('+00:60', '-00:60', '+01:99', '-23:99', '+24:00', '-24:00'):
            for field in ('context', 'acceptance', 'evidence'):
                with self.subTest(offset=offset, field=field):
                    value = example()
                    stamp = '2026-10-17T12:30:00' + offset
                    if field == 'context':
                        value['context_as_of'] = stamp
                    elif field == 'acceptance':
                        value['acceptance_claims'][0]['accepted_at'] = stamp
                    else:
                        value['evidence'][0]['observed_at'] = stamp
                    self.result('record', '--input', '-', value=value, expected=65)
        self.assertEqual(list((self.store / 'records').iterdir()), [])

    def test_invalid_stored_offset_blocks_selection_without_previous_fallback(self):
        self.initialize()
        first = self.record()
        latest = self.record(example(predecessor=first['record_id']))
        path = self.stored_path(latest['record_id'])
        value = json.loads(path.read_text())
        value['created_at'] = '2026-10-17T12:30:00+00:60'
        path.write_text(json.dumps(value))
        result = self.result('pickup', '--task', 'alpha', expected=74)
        self.assertIsNone(result['data']['record'])
        self.assertIsNone(result['data']['continuation'])
        self.assertEqual(result['data']['integrity'], 'invalid')

    def test_valid_offset_edges_normalize_without_changing_instant(self):
        self.initialize()
        cases = [('+23:59', '2026-10-16T12:31:00Z'),
                 ('-23:59', '2026-10-18T12:29:00Z'),
                 ('+00:59', '2026-10-17T11:31:00Z'),
                 ('-00:59', '2026-10-17T13:29:00Z'),
                 ('+00:00', '2026-10-17T12:30:00Z'),
                 ('-00:00', '2026-10-17T12:30:00Z')]
        for index, (offset, expected) in enumerate(cases):
            value = example(task=str(index))
            value['context_as_of'] = '2026-10-17T12:30:00' + offset
            record = self.record(value)
            shown = self.result('show', record['record_id'])['data']['record']
            self.assertEqual(shown['context_as_of'], expected)


class CleanupReceipts(CLIBase):
    def test_cleanup_failure_preserves_commit_identity_and_closes_all_descriptors(self):
        self.initialize()
        for mode in ('unlock', 'records_fd', 'lock_fd', 'root', 'unknown', 'precommit', 'fault'):
            with self.subTest(mode=mode):
                audit = self.root / (mode + '.audit.json')
                value = example(task=mode)
                result = subprocess.run(
                    [sys.executable, str(Path(__file__).with_name('cleanup_writer.py')),
                     mode, str(self.store), str(audit)],
                    input=json.dumps(value), text=True, capture_output=True,
                    env=self.env, cwd=self.scratch, timeout=10)
                expected = 69 if mode == 'precommit' else 73 if mode == 'fault' else 74
                self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
                payload = json.loads(result.stdout)
                if expected == 74:
                    self.assertEqual(payload['code'], 'commit_unknown')
                    candidate = payload['data']['candidate_record_id']
                    self.assertTrue(self.result('show', candidate)['data']['current'])
                else:
                    self.assertIsNone(payload['data'])
                    self.assertEqual(self.result('list', '--task', mode)['data']['matching_total'], 0)
                self.assertEqual(json.loads(audit.read_text()),
                                 {'records_fd': True, 'lock_fd': True, 'root': True})
