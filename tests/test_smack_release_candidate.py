"""Exact candidate pair and lossless store runtime contract, without Docker."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
NAME = 'willitmod-dev-5tratsmack'
RECORD = json.loads((ROOT / 'SMACK-RELEASE-CANDIDATE-2026-09-29.json').read_text())


def validate_model(current):
    restored = copy.deepcopy(current)
    allowed = {('services', 'app', 'image'), ('services', 'swap', 'image'),
               ('services', 'app', 'stop_signal')}
    allowed.update(('services', 'app', 'environment', key) for key in
                   ('APP_IMAGE', 'APP_VERSION', 'APP_REVISION', 'FIVETRAT_RELEASE_TAG'))
    if RECORD['channel'] == 'main':
        allowed.add(('services', 'app', 'hostname'))
    assert {tuple(row['path']) for row in RECORD['approvedRuntimeChanges']} == allowed
    for row in RECORD['approvedRuntimeChanges']:
        node = restored
        for key in row['path'][:-1]:
            node = node[key]
        assert node[row['path'][-1]] == row['after']
        if row['existed']:
            node[row['path'][-1]] = row['before']
        else:
            del node[row['path'][-1]]
    sha = hashlib.sha256(json.dumps(restored, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert sha == RECORD['baselineComposeSha256'], 'unapproved runtime change'


class SmackCandidateTests(unittest.TestCase):
    def test_exact_pair_versions_source_and_manifest_bytes(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-5tratsmack-metadata.py')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        model = yaml.safe_load((ROOT / NAME / 'docker-compose.yml').read_text())
        self.assertEqual(model['services']['app']['image'], RECORD['appImageRef'])
        self.assertEqual(model['services']['swap']['image'], RECORD['kdfImageRef'])
        self.assertEqual(model['services']['app']['environment']['APP_REVISION'], RECORD['sourceRevision'])
        self.assertEqual(RECORD['version'], '0.11.16')
        self.assertEqual(RECORD['platforms'], ['linux/amd64', 'linux/arm64'])
        self.assertEqual(RECORD['registryEvidenceSha256'], 'd47b0eb8a904d44d966e16bae06b3865257eb71dd4a22e7ea8d578d3216973e9')

    def test_all_other_runtime_fields_are_exact_channel_baseline(self):
        current = yaml.safe_load((ROOT / NAME / 'docker-compose.yml').read_text())
        validate_model(current)
        # A paired release cannot silently relocate data, alter mining ports,
        # change Core/CKPool images, or widen its shutdown policy to the node.
        for service, field, value in [
            ('node-a', 'image', 'different-core'), ('ckpool', 'image', 'different-pool'),
            ('app', 'volumes', ['/different:/data']), ('app', 'ports', ['1234:3000']),
            ('swap', 'volumes', ['/different-wallet:/data']),
            ('node-a', 'stop_signal', 'SIGINT')]:
            with self.subTest(service=service, field=field):
                changed = copy.deepcopy(current)
                changed['services'][service][field] = value
                with self.assertRaises(AssertionError):
                    validate_model(changed)

    def test_metadata_validator_rejects_stale_version_source_or_pair(self):
        with tempfile.TemporaryDirectory(prefix='smack-store-metadata-') as raw:
            root = Path(raw)
            (root / 'scripts').mkdir()
            (root / NAME).mkdir()
            for name in ['scripts/validate-5tratsmack-metadata.py', 'README.md',
                         NAME + '/umbrel-app.yml', NAME + '/5tratstore-app.yml']:
                (root / name).write_bytes((ROOT / name).read_bytes())
            original = (ROOT / NAME / 'docker-compose.yml').read_text()
            for before, after in [
                ('      APP_VERSION: 0.11.16', '      APP_VERSION: 0.11.15'),
                (RECORD['sourceRevision'], '0' * 40),
                (RECORD['kdfImageRef'], RECORD['kdfImageRef'].replace('@sha256:', '@sha256:0')),
                ('    stop_signal: SIGINT', '    stop_signal: SIGTERM')]:
                with self.subTest(before=before):
                    (root / NAME / 'docker-compose.yml').write_text(original.replace(before, after))
                    result = subprocess.run([sys.executable, str(root / 'scripts/validate-5tratsmack-metadata.py')],
                                            capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)

    def test_candidate_claims_and_browser_ack_scope_remain_honest(self):
        for key in ('nodeAcceptancePassed', 'independentPackageInstallPassed', 'publicPromotion'):
            self.assertIs(RECORD[key], False)
        manifest = yaml.safe_load((ROOT / NAME / 'umbrel-app.yml').read_text())
        self.assertNotIn('has completed public-chain', manifest['description'])
        for phrase in ('Block alerts in this browser', 'local to that browser',
                       'OS and MUX notification acknowledgements remain separate',
                       'Trade Pulse', 'Gleec', 'final transaction approval'):
            self.assertIn(phrase, manifest['releaseNotes'])
        if RECORD['channel'] == 'main':
            rollup = json.loads((ROOT / 'MAIN-NODE-ROLLUP-2026-09-28.json').read_text())
            self.assertEqual(len(rollup['apps']), 9)
            self.assertNotIn(NAME, rollup['apps'])
            self.assertEqual(rollup['smackCandidate']['recordSha256'], hashlib.sha256(
                (ROOT / rollup['smackCandidate']['record']).read_bytes()).hexdigest())


if __name__ == '__main__':
    unittest.main()
