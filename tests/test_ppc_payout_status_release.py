"""Payout-status delivery preserves every other PPC runtime/manifest field."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ppc_payout_status_release', ROOT / 'scripts/ppc_payout_status_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PpcPayoutStatusReleaseTests(unittest.TestCase):
    def test_current_package_is_exact_app_image_and_text_successor(self):
        row = release.validate()
        current = yaml.safe_load((ROOT / release.APP / 'docker-compose.yml').read_text())
        before = release.predecessor('docker-compose.yml')
        self.assertEqual(release.previous_model(release.APP, current), before)
        self.assertEqual(release.previous_model(release.APP, before), before)
        self.assertEqual(current['services']['app']['environment'], before['services']['app']['environment'])
        self.assertEqual(current['services']['app']['volumes'], before['services']['app']['volumes'])
        for service in ('app_proxy', 'init', 'ppcd', 'pool', 'redis'):
            self.assertEqual(current['services'][service], before['services'][service])
        self.assertEqual(release.package_version(release.APP, row['previousPackageVersion']), row['packageVersion'])
        self.assertEqual(release.package_version(release.APP, row['packageVersion']), row['packageVersion'])
        with self.assertRaises(AssertionError):
            release.package_version(release.APP, 'arbitrary-version')

    def test_runtime_adapter_rejects_settings_mount_signal_node_pool_and_network_changes(self):
        current = release.expected_model()
        for service, field, value in [('app', 'image', 'moving:latest'), ('app', 'volumes', []),
                                      ('app', 'environment', {}), ('app', 'networks', {}),
                                      ('app', 'stop_signal', 'SIGTERM'), ('app', 'user', '0:0'),
                                      ('ppcd', 'image', 'changed-node'), ('ppcd', 'volumes', []),
                                      ('ppcd', 'stop_grace_period', '10s'), ('pool', 'image', 'changed-pool'),
                                      ('pool', 'ports', ['9999:3333']), ('init', 'command', []),
                                      ('redis', 'image', 'changed-redis')]:
            changed = copy.deepcopy(current)
            changed['services'][service][field] = value
            with self.subTest(service=service, field=field), self.assertRaises(AssertionError):
                release.previous_model(release.APP, changed)
        changed = copy.deepcopy(current)
        changed['unreviewed'] = True
        with self.assertRaises(AssertionError):
            release.previous_model(release.APP, changed)

    def test_manifest_adapter_allows_only_exact_version_note_and_address_help(self):
        current = release.expected_manifest()
        before = release.predecessor('umbrel-app.yml')
        self.assertEqual(release.previous_manifest(release.APP, current), before)
        self.assertEqual(release.previous_manifest(release.APP, before), before)
        self.assertIn('bare native Peercoin receiving address', current['description'])
        self.assertNotIn('must be a Base58', current['description'])
        for field, value in [('id', 'other-app'), ('version', '99.0.0'), ('port', 9999),
                             ('backupIgnore', []), ('description', before['description']),
                             ('releaseNotes', before['releaseNotes'])]:
            changed = copy.deepcopy(current)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                release.previous_manifest(release.APP, changed)

    def test_record_edits_cannot_authorize_other_publication_or_runtime_changes(self):
        original = json.loads((ROOT / release.RECORD_NAME).read_text())
        for field, value in [('imageRef', 'moving:latest'), ('sourceRevision', '0' * 40),
                             ('sourceTree', '0' * 40), ('publicationRun', 1),
                             ('packageVersion', '99.0.0'), ('platforms', {}),
                             ('afterModelSHA256', '0' * 64),
                             ('runtimeChanges', [['services', 'pool', 'image']])]:
            with tempfile.TemporaryDirectory(prefix='ppc-record-') as directory:
                root = Path(directory)
                changed = copy.deepcopy(original)
                changed[field] = value
                (root / release.RECORD_NAME).write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaises(AssertionError):
                    release.record(root)

    def test_adapter_is_disjoint_and_never_mutates_its_input(self):
        other = {'services': {'app': {'image': 'unchanged'}}}
        self.assertEqual(release.previous_model('other-app', other), other)
        self.assertEqual(release.previous_manifest('other-app', other), other)
        self.assertEqual(release.package_version('other-app', 'retained'), 'retained')
        current = release.expected_model()
        original = copy.deepcopy(current)
        release.previous_model(release.APP, current)
        self.assertEqual(current, original)
        row = release.record()
        self.assertEqual(set(row['platforms']), {'amd64', 'arm64'})
        self.assertEqual(row['applicationVersion'], '0.2.38')
        self.assertEqual(row['runtimeChanges'], [['services', 'app', 'image']])
        self.assertEqual(row['qualificationScope']['isolatedNativeArm64ExactImageMigration']['platform'], 'linux/arm64')
        self.assertFalse(row['qualificationScope']['ordinaryAppManagerUpdateClaimed'])


if __name__ == '__main__':
    unittest.main()
