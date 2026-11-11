"""The XEC node release changes exactly two recipe references (Bitcoin ABC 0.34.3)."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-xec'
RECORD = 'XEC-NODE-2026-11-10.json'
PREVIOUS_NODE = 'ghcr.io/willitmod/xecd-abc:0.33.4-nojemalloc-r1'
BEFORE_MODEL_SHA256 = '43a4a4c0894866a90f30bda2d21804fa0f4d9de2a27939ee3f614484ca8ee9fe'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def record():
    return json.loads((ROOT / RECORD).read_text())


def package_version(app_id, historical):
    return record()['version'] if app_id == APP else historical


def is_current(app_id, model):
    return app_id == APP and digest(model) == record()['runtimeContract']['afterModelSHA256']


def previous_xec_node_model(app_id, current):
    if app_id != APP:
        return copy.deepcopy(current)
    release = record()
    contract = release['runtimeContract']
    expected = {('services', 'xecd', 'image'), ('services', 'app', 'environment', 'XECD_IMAGE')}
    assert len(contract['changes']) == 2 and {tuple(r['path']) for r in contract['changes']} == expected
    assert digest(current) == contract['afterModelSHA256'], 'Only the XEC node image may change'
    restored = copy.deepcopy(current)
    for row in contract['changes']:
        node = restored
        for key in row['path'][:-1]:
            node = node[key]
        assert node[row['path'][-1]] == row['after'] == release['nodeImageRef']
        assert row['before'] == release['previousNodeImageRef'] == PREVIOUS_NODE
        node[row['path'][-1]] = row['before']
    assert contract['beforeModelSHA256'] == BEFORE_MODEL_SHA256
    assert digest(restored) == contract['beforeModelSHA256']
    return restored


class XecNodeReleaseTests(unittest.TestCase):
    def test_current_node_and_exact_prior_runtime(self):
        r = record()
        self.assertEqual((r['appId'], r['channel'], r['version']), (APP, 'MAIN', '0.1.25'))
        self.assertEqual((r['coreVersion'], r['previousCoreVersion']), ('0.34.3', '0.33.4'))
        self.assertEqual(r['upstreamRevision'], '5621f13e073c007bed66a35fdfda3bc67772bab6')
        self.assertRegex(r['nodeImageRef'], r'^ghcr\.io/willitmod/xecd-abc:0\.34\.3-nojemalloc-r1@sha256:[a-f0-9]{64}$')
        current = yaml.safe_load((ROOT / APP / 'docker-compose.yml').read_text())
        restored = previous_xec_node_model(APP, current)
        self.assertEqual(restored['services']['xecd']['image'], PREVIOUS_NODE)
        for service in ('app', 'ckpool', 'init'):
            self.assertEqual(current['services'][service]['image'], restored['services'][service]['image'])
        manifest = yaml.safe_load((ROOT / APP / 'umbrel-app.yml').read_text())
        self.assertEqual(manifest['version'], package_version(APP, None))
        for value in ('Bitcoin ABC 0.34.3', '15 November 2026', 'Only the node image changes'):
            self.assertIn(value, manifest['releaseNotes'])

    def test_unrelated_runtime_and_configuration_changes_fail(self):
        current = yaml.safe_load((ROOT / APP / 'docker-compose.yml').read_text())
        for service, key, value in [('app', 'image', 'changed'), ('ckpool', 'image', 'changed'),
                                    ('xecd', 'volumes', []), ('xecd', 'ports', ['1:1']),
                                    ('xecd', 'image', 'ghcr.io/willitmod/xecd-abc:0.34.3-nojemalloc-r1')]:
            changed = copy.deepcopy(current)
            changed['services'][service][key] = value
            with self.subTest(service=service, field=key), self.assertRaises(AssertionError):
                previous_xec_node_model(APP, changed)

    def test_public_record_contains_no_host_evidence(self):
        raw = (ROOT / RECORD).read_text()
        for private in ('/Users/', '/home/forge', '10.10.10.', 'PAYOUT_ADDRESS', 'APP_PASSWORD'):
            self.assertNotIn(private, raw)
        r = record()
        self.assertEqual(set(r['images']), {'amd64', 'arm64'})
        for row in r['images'].values():
            self.assertEqual(set(row), {'configDigest', 'manifestDigest'})
            for value in row.values():
                self.assertRegex(value, r'^sha256:[a-f0-9]{64}$')
        self.assertFalse(r['reindexRequested'])


if __name__ == '__main__':
    unittest.main()
