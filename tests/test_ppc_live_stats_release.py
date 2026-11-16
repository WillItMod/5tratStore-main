"""The live-statistics app release retains node, pool and every stored-data mount."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('ppc_live_stats_release', ROOT / 'scripts/ppc_live_stats_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class PpcLiveStatsReleaseTests(unittest.TestCase):
    def test_complete_package_and_historical_reversal(self):
        row = release.validate(ROOT)
        current = yaml.safe_load((ROOT / release.APP / 'docker-compose.yml').read_text())
        before = yaml.safe_load(release.baseline_bytes(ROOT, release.APP + '/docker-compose.yml'))
        self.assertEqual(release.previous_model(release.APP, current, ROOT), before)
        self.assertEqual(release.previous_model(release.APP, before, ROOT), before)
        for name in before['services']:
            if name != 'app':
                self.assertEqual(current['services'][name], before['services'][name])
        old_app, new_app = copy.deepcopy(before['services']['app']), copy.deepcopy(current['services']['app'])
        old_app.pop('image')
        new_app.pop('image')
        if row['channel'] == 'DEV':
            self.assertEqual(new_app['environment']['APP_VERSION_SUFFIX'], '-dev')
            new_app['environment']['APP_VERSION_SUFFIX'] = old_app['environment']['APP_VERSION_SUFFIX']
        self.assertEqual(new_app, old_app)
        for name in row['beforeManifestSHA256']:
            current_manifest = yaml.safe_load((ROOT / release.APP / name).read_text())
            before_manifest = yaml.safe_load(release.baseline_bytes(ROOT, release.APP + '/' + name))
            self.assertEqual(release.previous_manifest(release.APP, current_manifest, name, ROOT), before_manifest)
            self.assertEqual(current_manifest['version'], row['packageVersion'])
        self.assertEqual(release.package_version(release.APP, row['previousPackageVersion']), row['packageVersion'])

    def test_arbitrary_runtime_changes_are_refused(self):
        current = yaml.safe_load((ROOT / release.APP / 'docker-compose.yml').read_text())
        for service, key, value in [('app', 'image', 'moving:latest'), ('app', 'environment', {}),
                                    ('app', 'volumes', []), ('app', 'user', '0:0'),
                                    ('ppcd', 'image', 'other:node'), ('ppcd', 'volumes', []),
                                    ('pool', 'image', 'other:pool'), ('pool', 'ports', ['1:1']),
                                    ('redis', 'image', 'other:redis'), ('init', 'command', [])]:
            changed = copy.deepcopy(current)
            changed['services'][service][key] = value
            with self.subTest(service=service, key=key), self.assertRaises(AssertionError):
                release.previous_model(release.APP, changed, ROOT)

    def test_arbitrary_manifest_changes_and_bad_versions_are_refused(self):
        current = yaml.safe_load((ROOT / release.APP / 'umbrel-app.yml').read_text())
        for key, value in [('version', '9.0.0'), ('port', 1), ('id', 'other'),
                           ('releaseNotes', 'unreviewed'), ('backupIgnore', [])]:
            changed = copy.deepcopy(current)
            changed[key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                release.previous_manifest(release.APP, changed, 'umbrel-app.yml', ROOT)
        with self.assertRaises(AssertionError):
            release.package_version(release.APP, 'unreviewed')

    def test_record_edits_never_authorize_replacement_images_or_claims(self):
        row = json.loads((ROOT / release.RECORD).read_text())
        for key, value in [('imageRef', 'moving:latest'), ('sourceRevision', '0' * 40),
                           ('publicationRun', 0), ('nodeImageRef', 'changed:node'),
                           ('runtimeChanges', [['services', 'pool', 'image']]),
                           ('afterModelSHA256', '0' * 64)]:
            with tempfile.TemporaryDirectory(prefix='ppc-live-record-') as directory:
                root = Path(directory)
                changed = copy.deepcopy(row)
                changed[key] = value
                (root / release.RECORD).write_text(json.dumps(changed))
                with self.subTest(key=key), self.assertRaisesRegex(AssertionError, 'Unreviewed'):
                    release.record(root)

    def test_unrelated_apps_pass_through_without_mutation(self):
        current = {'services': {'app': {'image': 'unrelated'}}}
        self.assertEqual(release.previous_model('other-app', current), current)
        self.assertEqual(release.previous_manifest('other-app', current), current)
        self.assertEqual(release.package_version('other-app', 'unchanged'), 'unchanged')
        self.assertEqual(release.previous_bytes(ROOT, 'other-app/file', b'unchanged'), b'unchanged')


if __name__ == '__main__':
    unittest.main()
