"""Exact native release identities and lossless channel runtime contract."""
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
RECORD = json.loads((ROOT / 'SMACK-RELEASE-2026-10-01.json').read_text())

def validate_model(current):
    restored = copy.deepcopy(current)
    allowed = {('services', 'app', 'image'), ('services', 'app', 'healthcheck', 'test')}
    allowed.update(('services', 'app', 'environment', key) for key in
                   ('APP_IMAGE', 'APP_VERSION', 'APP_REVISION', 'FIVETRAT_RELEASE_TAG'))
    if RECORD['channel'] == 'main':
        allowed.update({('services', 'swap', 'image'), ('services', 'app', 'stop_signal'),
                        ('services', 'app', 'hostname')})
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
    return restored

class SmackReleaseTests(unittest.TestCase):
    def test_exact_images_version_source_and_manifests(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/validate-5tratsmack-metadata.py')],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(RECORD['version'], '0.11.18')
        self.assertEqual(RECORD['sourceRevision'], 'fa08d11623b51159f78c47ac2e2a93cab639cb71')
        self.assertEqual(RECORD['platforms'], ['linux/amd64', 'linux/arm64'])

    def test_all_other_runtime_fields_are_exact_channel_baseline(self):
        current = yaml.safe_load((ROOT / NAME / 'docker-compose.yml').read_text())
        validate_model(current)
        for service, field, value in [
            ('node-a', 'image', 'different-core'), ('ckpool', 'image', 'different-pool'),
            ('app', 'volumes', ['/different:/data']), ('app', 'ports', ['1234:3000']),
            ('swap', 'volumes', ['/different-wallet:/data']),
            ('node-a', 'stop_signal', 'SIGINT'), ('app', 'healthcheck', {'test': ['CMD', 'true']}),
            ('app', 'environment', {'APP_CHANNEL': 'wrong'})]:
            with self.subTest(service=service, field=field):
                changed = copy.deepcopy(current)
                changed['services'][service][field] = value
                with self.assertRaises((AssertionError, KeyError)):
                    validate_model(changed)

    def test_metadata_rejects_stale_version_source_broker_or_python_healthcheck(self):
        with tempfile.TemporaryDirectory(prefix='smack-store-metadata-') as raw:
            root = Path(raw)
            (root / 'scripts').mkdir()
            (root / NAME).mkdir()
            for name in ['scripts/validate-5tratsmack-metadata.py', 'README.md',
                         'SMACK-RELEASE-2026-10-01.json', 'SMACK-PUBLISHED-IMAGES-2026-10-01.json',
                         NAME + '/umbrel-app.yml', NAME + '/5tratstore-app.yml']:
                (root / name).write_bytes((ROOT / name).read_bytes())
            original = (ROOT / NAME / 'docker-compose.yml').read_text()
            for before, after in [
                ('      APP_VERSION: 0.11.18', '      APP_VERSION: 0.11.17'),
                (RECORD['sourceRevision'], '0' * 40),
                (RECORD['kdfImageRef'], RECORD['kdfImageRef'].replace('@sha256:', '@sha256:0')),
                ('    stop_signal: SIGINT', '    stop_signal: SIGTERM'),
                ('"CMD", "curl"', '"CMD", "python3"'),
                (RECORD['appImageRef'], RECORD['appImageRef'].replace('@sha256:', '@sha256:0'))]:
                with self.subTest(before=before):
                    (root / NAME / 'docker-compose.yml').write_text(original.replace(before, after))
                    result = subprocess.run([sys.executable, str(root / 'scripts/validate-5tratsmack-metadata.py')],
                                            capture_output=True, text=True, timeout=10)
                    self.assertNotEqual(result.returncode, 0)

    def test_provenance_is_public_and_has_no_host_configuration(self):
        data = (ROOT / 'SMACK-PUBLISHED-IMAGES-2026-10-01.json').read_text()
        for private in ('/Users/', '/home/forge', '10.10.10.', 'PAYOUT_ADDRESS', 'APP_PASSWORD'):
            self.assertNotIn(private, data)
        evidence = json.loads(data)
        self.assertEqual(set(evidence['images']), {'amd64', 'arm64'})
        self.assertEqual(evidence['images']['amd64']['configDigest'],
                         'sha256:d58680f81abd75ed5591395c156674ab111f4d68f1281de4dc9e1d7328fe710d')
        self.assertEqual(evidence['images']['arm64']['configDigest'],
                         'sha256:ceb13072ad877f7f57149d86d3bcf67ab8d6d14ce77bd408fe2032690d2661fb')

if __name__ == '__main__':
    unittest.main()
