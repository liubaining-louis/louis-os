from __future__ import annotations

import base64
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import degraded_monetization_cycle as runtime
from tests.test_capability_first_payable_scout import issue, maintainer_payment_comment


class DegradedRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.state = self.root / 'results/degraded'
        (self.root / 'config').mkdir()
        for name in ['production_policy.json', 'degraded_runtime.json']:
            (self.root / 'config' / name).write_text((runtime.ROOT / 'config' / name).read_text())
        self.set_driver('github_actions')
        self.item = issue(1)
        self.item['updated_at'] = runtime.now()
        self.item['body'] = 'In `README.md`, replace https://old.example/docs with https://new.example/docs.'
        self.content = '# Docs\nhttps://old.example/docs\n'
        self.repo = {'full_name': 'acme/docs', 'archived': False, 'disabled': False,
                     'owner': {'type': 'Organization'}, 'stargazers_count': 150, 'forks_count': 20,
                     'created_at': '2020-01-01T00:00:00Z', 'pushed_at': runtime.now(),
                     'default_branch': 'main', 'description': 'Documentation'}
        self.requests = []

    def set_driver(self, driver):
        path = self.root / 'config/degraded_runtime.json'
        cfg = json.loads(path.read_text())
        cfg['submission_driver'] = driver
        path.write_text(json.dumps(cfg))

    def test_operator_receives_valid_package_even_when_runner_has_pat(self):
        self.set_driver('connected_github_operator')
        out = self.prepare(True)
        self.assertEqual(out['cycle_outcome'], 'prepared_for_connected_operator')
        brief = runtime.operator_briefing(self.state, self.root)
        self.assertTrue(brief['package_available_for_review'])
        self.assertFalse(brief['submission_authorized'])
        self.assertFalse((self.state / 'intents.json').exists())
        with patch.object(runtime, 'submit_patch') as send:
            self.assertEqual(runtime.submit(self.root, self.state)['status'], 'delegated_to_connected_operator')
            send.assert_not_called()

    def test_takeover_blocks_previously_prepared_automatic_submission(self):
        out = self.prepare(True)
        self.set_driver('connected_github_operator')
        with patch.dict(os.environ, {'LOUIS_DEGRADED_CHECKPOINT': out['run_id']}), \
             patch.object(runtime, 'submit_patch') as send:
            self.assertEqual(runtime.submit(self.root, self.state)['status'], 'delegated_to_connected_operator')
            send.assert_not_called()
        brief = runtime.operator_briefing(self.state, self.root)
        self.assertFalse(brief['package_available_for_review'])
        self.assertEqual(brief['next_action'], 'reconcile_intents')

    def test_operator_reservation_survives_next_runner_and_prevents_duplicate(self):
        self.set_driver('connected_github_operator')
        self.prepare()
        ready = runtime.read(self.state / 'ready.json', {})
        runtime.save(self.state / 'intents.json', {'items': [{
            'candidate_id': ready['candidate']['id'], 'status': 'operator_reserved',
            'run_id': 'operator-session', 'source_run_id': ready['run_id']}]})
        self.assertFalse(runtime.operator_briefing(self.state, self.root)['package_available_for_review'])
        out = self.prepare()
        self.assertEqual(out['qualified'], 0)
        self.assertFalse((self.state / 'ready.json').exists())
        brief = runtime.operator_briefing(self.state, self.root)
        self.assertEqual(brief['next_action'], 'reconcile_intents')
        self.assertIsNone(brief['candidate_id'])

    def test_invalid_driver_fails_closed_before_network_or_submission(self):
        self.set_driver('typo')
        with self.assertRaisesRegex(ValueError, 'unknown_submission_driver'):
            self.prepare(True)
        with patch.object(runtime, 'submit_patch') as send:
            with self.assertRaisesRegex(ValueError, 'unknown_submission_driver'):
                runtime.submit(self.root, self.state, self.getter)
            send.assert_not_called()
        self.assertEqual(self.requests, [])

    def getter(self, url):
        self.requests.append(url)
        if '/search/issues?' in url:
            return {'items': [copy.deepcopy(self.item)]}
        if '/comments' in url:
            return [maintainer_payment_comment(1)]
        if '/issues/1' in url:
            return copy.deepcopy(self.item)
        if '/contents/' in url:
            return {'encoding': 'base64', 'content': base64.b64encode(self.content.encode()).decode(), 'sha': 'blob-one'}
        if url == 'https://api.github.com/repos/acme/docs':
            return self.repo
        raise AssertionError(url)

    def prepare(self, credential=False):
        with patch.dict(os.environ, {'LOUIS_EXTERNAL_CREDENTIAL_PRESENT': str(credential).lower()}):
            return runtime.prepare(self.root, self.state, self.getter)

    def test_prepares_real_hash_validated_patch_without_cloud_or_write_credentials(self):
        out = self.prepare()
        self.assertEqual(out['cycle_outcome'], 'prepared_external_credential_missing')
        ready = runtime.read(self.state / 'ready.json', {})
        workspace = self.state / ready['workspace']
        generated = (workspace / 'patch_files/README.md').read_text()
        self.assertIn('https://new.example/docs', generated)
        manifest = runtime.read(self.state / ready['manifest_path'], {})
        self.assertEqual(len(runtime.validate_patch_manifest(manifest, workspace)), 1)
        self.assertFalse((self.root / 'results/monetization.json').exists())
        self.assertTrue(all(u.startswith('https://api.github.com/') for u in self.requests))

    def test_kill_switch_disables_all_network_work(self):
        path = self.root / 'config/production_policy.json'
        policy = json.loads(path.read_text()); policy['kill_switch'] = True
        path.write_text(json.dumps(policy))
        out = self.prepare()
        self.assertEqual(out['runtime_status'], 'disabled')
        self.assertEqual(self.requests, [])

    def test_corrupt_intents_do_not_reset_duplicate_protection(self):
        self.state.mkdir(parents=True)
        (self.state / 'intents.json').write_text('corrupt')
        with self.assertRaises(json.JSONDecodeError):
            self.prepare()
        self.assertEqual(self.requests, [])

    def test_submission_requires_remote_checkpoint(self):
        out = self.prepare(True)
        self.assertEqual(out['cycle_outcome'], 'prepared_for_submission')
        with patch.dict(os.environ, {'LOUIS_DEGRADED_CHECKPOINT': ''}):
            with self.assertRaisesRegex(ValueError, 'not_remotely_checkpointed'):
                runtime.submit(self.root, self.state, self.getter)

    def test_stale_package_cannot_be_submitted_by_another_run(self):
        self.prepare(True)
        with patch.dict(os.environ, {'GITHUB_RUN_ID': 'different-run'}):
            with self.assertRaisesRegex(ValueError, 'stale_submission_package'):
                runtime.submit(self.root, self.state, self.getter)

    def test_uncertain_external_result_is_never_retried(self):
        out = self.prepare(True)
        with patch.dict(os.environ, {'LOUIS_DEGRADED_CHECKPOINT': out['run_id']}), \
             patch.object(runtime, 'submit_patch', side_effect=TimeoutError) as send:
            result = runtime.submit(self.root, self.state, self.getter)
            self.assertEqual(result['cycle_outcome'], 'submission_uncertain')
            self.assertEqual(send.call_count, 1)
        next_cycle = self.prepare(True)
        self.assertEqual(next_cycle['qualified'], 0)
        self.assertEqual(runtime.read(self.state / 'intents.json', {})['items'][0]['status'],
                         'attempted_requires_reconciliation')

    def test_verified_receipt_is_durable_and_not_counted_as_payment(self):
        out = self.prepare(True)
        receipt = {'candidate_id': runtime.read(self.state / 'ready.json', {})['candidate']['id'],
                   'pull_request_url': 'https://github.com/acme/docs/pull/2', 'verified': True}
        with patch.dict(os.environ, {'LOUIS_DEGRADED_CHECKPOINT': out['run_id']}), \
             patch.object(runtime, 'submit_patch', return_value=receipt):
            result = runtime.submit(self.root, self.state, self.getter)
        self.assertEqual(result['submitted_this_cycle'], 1)
        self.assertEqual(result['paid_verified_this_cycle'], 0)
        self.assertEqual(runtime.read(self.state / 'receipts.json', {})['receipts'], [receipt])

    def test_changed_upstream_blocks_submission(self):
        out = self.prepare(True)
        def changed(url):
            value = self.getter(url)
            if '/contents/' in url:
                value['sha'] = 'changed'
            return value
        with patch.dict(os.environ, {'LOUIS_DEGRADED_CHECKPOINT': out['run_id']}), \
             patch.object(runtime, 'submit_patch') as send:
            with self.assertRaisesRegex(ValueError, 'upstream_changed'):
                runtime.submit(self.root, self.state, changed)
            send.assert_not_called()

    def test_wrong_host_and_request_budget_fail_before_network(self):
        getter = runtime.BoundedGitHub(0)
        with self.assertRaisesRegex(ValueError, 'non_github'):
            getter('https://attacker.example/credentials')
        with self.assertRaisesRegex(RuntimeError, 'budget_exhausted'):
            getter('https://api.github.com/search/issues?q=test')

    def test_output_rejects_known_credentials(self):
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'synthetic-secret-for-test'}):
            with self.assertRaisesRegex(ValueError, 'credential_detected'):
                runtime.save(self.state / 'bad.json', {'value': 'synthetic-secret-for-test'})


if __name__ == '__main__':
    unittest.main()
