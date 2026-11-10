"""The 2026-11-10 node-only releases change exactly the node image and its app reference."""
import copy
import importlib.util
from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('node_core_release_unit', ROOT / 'scripts/node_core_release.py')
node = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(node)


class NodeCoreReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = node.record(ROOT)

    def test_exact_packages_and_reverse_to_previous_release(self):
        node.validate(ROOT)
        for app_id, app in self.row['apps'].items():
            with self.subTest(app=app_id):
                current = yaml.safe_load((ROOT / app_id / 'docker-compose.yml').read_text())
                before = yaml.safe_load(node.baseline_bytes(ROOT, app_id + '/docker-compose.yml'))
                self.assertEqual(node.previous_node_model(app_id, current, ROOT), before)
                for change in app['changes']:
                    value = current
                    for key in change['path']:
                        value = value[key]
                    self.assertEqual(value, app['nodeImageRef'])
                for name, service in before['services'].items():
                    if (('services', name) not in {tuple(c['path'][:2]) for c in app['changes']}) and name != 'app':
                        self.assertEqual(current['services'][name], service)
                for filename in app['beforeManifestSHA256']:
                    manifest = yaml.safe_load((ROOT / app_id / filename).read_text())
                    previous = yaml.safe_load(node.baseline_bytes(ROOT, f'{app_id}/{filename}'))
                    self.assertEqual(manifest['version'], app['version'])
                    self.assertTrue(manifest['releaseNotes'].startswith(app['note']))
                    self.assertEqual(node.previous_node_manifest(app_id, manifest, filename, ROOT), previous)
                self.assertEqual(node.node_package_version(app_id, app['previousVersion'], ROOT), app['version'])
                self.assertIn('Only the node image changes', app['note'])

    def test_other_changes_are_not_reversed(self):
        for app_id, app in self.row['apps'].items():
            current = yaml.safe_load((ROOT / app_id / 'docker-compose.yml').read_text())
            node_service = next(c['path'][1] for c in app['changes'] if c['path'][1] != 'app')
            for service, key, value in [('app', 'image', 'changed:latest'), (node_service, 'volumes', []),
                                        (node_service, 'image', app['previousNodeImageRef']),
                                        (node_service, 'ports', ['1:1'])]:
                changed = copy.deepcopy(current)
                changed['services'][service][key] = value
                with self.subTest(app=app_id, service=service, key=key):
                    # Unreviewed models pass through unchanged, so older contracts reject them.
                    self.assertEqual(node.previous_node_model(app_id, changed, ROOT), changed)
            with self.assertRaises(AssertionError):
                node.node_package_version(app_id, 'arbitrary-version', ROOT)

    def test_images_are_multi_arch_and_record_is_public(self):
        raw = (ROOT / node.RECORD).read_text()
        for private in ('/Users/', '/home/forge', '10.10.10.', 'PAYOUT_ADDRESS', 'APP_PASSWORD'):
            self.assertNotIn(private, raw)
        for app_id, app in self.row['apps'].items():
            with self.subTest(app=app_id):
                self.assertRegex(app['nodeImageRef'], r'^ghcr\.io/willitmod/[a-z0-9-]+:[A-Za-z0-9_.-]+@sha256:[0-9a-f]{64}$')
                self.assertEqual(set(app['images']), {'amd64', 'arm64'})
                for digests in app['images'].values():
                    self.assertEqual(set(digests), {'manifestDigest', 'configDigest'})
                self.assertFalse(app['reindexRequested'])
        btc = next((a for k, a in self.row['apps'].items() if k.endswith('btc')), None)
        if btc is not None:
            self.assertTrue(btc['core']['knots']['unchanged'])


if __name__ == '__main__':
    unittest.main()
