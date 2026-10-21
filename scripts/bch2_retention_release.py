"""Closed recipe-only successor preserving the reviewed BCH2 runtime images."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-axebch2'
RECORD = 'BCH2-RETENTION-PERMISSIONS-2026-10-21.json'
BASELINES = {'MAIN': 'c5cc3768419b4bc41f70660d22261525e0c589dd', 'DEV': '88c855af13a1570f70a4e705cb34a0bc4dcdcb6c'}
RECORD_SHA256 = {'MAIN': '2d57551d4ec6388dfc339759e1366201fedceb00e396462b402475adbf4ff74a', 'DEV': '4ab8aad6b1c6a86d5a918cf58e164f408707f96b478d3fe38fde7a7f7e51a219'}
VERSIONS = {'MAIN': '0.2.3', 'DEV': '0.2.3-dev'}
NOTE = 'Startup permission repair preserves the OS-owned pool log retention lease. This prevents app restarts from blocking later OS updates. App checkpoint and accounting files remain writable. This recipe-only update retains the reviewed 0.2.2 application image, node and pool images, mining settings, payouts and stored data. An already blocked OS update needs the targeted recovery step before retrying.'
OLD_PERMISSIONS = ('        chown -R 1000:1000 /data/ui /data/pool || true\n'
                   '        chmod -R ug+rwX /data/ui /data/pool || true\n')
NEW_PERMISSIONS = '''        # The host owns retention leases. Never change their metadata or
        # promote existing bytes into a protected lease. Leave symlinks and
        # multiply-linked files alone; the app still owns its checkpoint/lock.
        find /data/ui /data/pool -name ckpool-retention-capability.json -prune -o \\( -type d -o \\( -type f -links 1 \\) \\) -exec chown -h 1000:1000 {} + || true
        find /data/ui /data/pool -name ckpool-retention-capability.json -prune -o \\( -type d -o \\( -type f -links 1 \\) \\) -exec chmod ug+rwX {} + || true
'''
MANIFESTS = ('umbrel-app.yml', 'global-app.yml')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def channel(root=ROOT):
    value = json.loads((root / 'BCH-HEALTH-RELEASE-2026-10-16.json').read_text())['channel']
    assert value in VERSIONS
    return value


def baseline_bytes(root, name):
    return git(root, 'show', BASELINES[channel(root)] + ':' + name)


def expected_bytes(root, name):
    before = baseline_bytes(root, name)
    version = VERSIONS[channel(root)]
    previous = '0.2.2' + ('-dev' if channel(root) == 'DEV' else '')
    if name == APP + '/docker-compose.yml':
        assert before.count(OLD_PERMISSIONS.encode()) == 1
        assert before.count(('APP_VERSION: "' + previous + '"').encode()) == 1
        return before.replace(OLD_PERMISSIONS.encode(), NEW_PERMISSIONS.encode()).replace(
            ('APP_VERSION: "' + previous + '"').encode(), ('APP_VERSION: "' + version + '"').encode())
    if name in {APP + '/' + filename for filename in MANIFESTS}:
        assert before.count(('version: "' + previous + '"').encode()) == 1
        return before.replace(('version: "' + previous + '"').encode(), ('version: "' + version + '"').encode()).replace(
            b'releaseNotes: >-\n', ('releaseNotes: >-\n  ' + NOTE + '\n\n').encode(), 1)
    return before


def record(root=ROOT):
    release_channel = channel(root)
    raw = (root / RECORD).read_bytes()
    assert RECORD_SHA256[release_channel] and sha(raw) == RECORD_SHA256[release_channel], 'Unreviewed BCH2 recipe release record'
    value = json.loads(raw)
    assert (value['schemaVersion'], value['status']) == (1, 'qualified-recipe-fixtures')
    assert (value['appId'], value['channel'], value['version'], value['baselineCommit']) == (
        APP, release_channel, VERSIONS[release_channel], BASELINES[release_channel])
    assert value['runtimeImagesChanged'] is False and value['applicationSourceChanged'] is False
    assert value['liveMinerRecoveryPerformed'] is False and value['physicalMiningQualified'] is False
    return value


def previous_file_bytes(raw, name, root=ROOT):
    row = record(root)
    assert raw == expected_bytes(root, name), 'Only the exact BCH2 retention permission repair and version metadata may change'
    assert sha(raw) == row['packageFiles'][name]['sha256'], 'BCH2 recipe package hash changed'
    return baseline_bytes(root, name)


def previous_model(current, root=ROOT):
    before = yaml.safe_load(baseline_bytes(root, APP + '/docker-compose.yml'))
    expected = yaml.safe_load(expected_bytes(root, APP + '/docker-compose.yml'))
    record(root)
    assert current == expected, 'Unreviewed BCH2 retention permission runtime delta'
    return copy.deepcopy(before)


def previous_manifest(current, filename, root=ROOT):
    record(root)
    assert current == yaml.safe_load(expected_bytes(root, APP + '/' + filename)), 'Unreviewed BCH2 recipe manifest delta'
    return yaml.safe_load(baseline_bytes(root, APP + '/' + filename))


def package_version(app_id, historical, root=ROOT):
    if app_id != APP:
        return historical
    record(root)
    old = '0.2.2' + ('-dev' if channel(root) == 'DEV' else '')
    assert historical in (old, VERSIONS[channel(root)]), 'Unreviewed BCH2 recipe predecessor version'
    return VERSIONS[channel(root)]


def validate(root=ROOT, *, check_baseline=False):
    row = record(root)
    names = git(root, 'ls-tree', '-r', '--name-only', row['baselineCommit'], '--', APP).decode().splitlines()
    paths = {str(p.relative_to(root)): p for p in (root / APP).rglob('*') if p.is_file() or p.is_symlink()}
    assert set(paths) == set(names) == set(row['packageFiles']), 'BCH2 package inventory changed'
    for name, path in paths.items():
        assert stat.S_ISREG(path.lstat().st_mode), 'BCH2 package symlink forbidden'
        mode = oct(stat.S_IMODE(path.stat().st_mode))
        assert mode == row['packageFiles'][name]['mode']
        assert git(root, 'ls-tree', row['baselineCommit'], '--', name).decode().split()[0] == ('100755' if path.stat().st_mode & 0o111 else '100644')
        previous_file_bytes(path.read_bytes(), name, root)
    before = previous_model(yaml.safe_load((root / APP / 'docker-compose.yml').read_text()), root)
    current = yaml.safe_load((root / APP / 'docker-compose.yml').read_text())
    images = {name: service['image'] for name, service in current['services'].items() if 'image' in service}
    assert images == row['runtimeImages'] == {name: service['image'] for name, service in before['services'].items() if 'image' in service}
    assert current['x-5tratumos-stop-policy'] == before['x-5tratumos-stop-policy'], 'Retention admission identity changed'
    for name, digest in row['historicalRecordsSHA256'].items():
        assert sha((root / name).read_bytes()) == digest == sha(baseline_bytes(root, name)), 'Historical release evidence changed'
    proof_raw = (root / row['fixtureProof']['path']).read_bytes()
    assert sha(proof_raw) == row['fixtureProof']['sha256'], 'BCH2 fixture proof changed'
    proof = json.loads(proof_raw)
    assert proof['result'] == 'PASS' and proof['schemaVersion'] == 1
    assert proof['testSourceSHA256'] == sha((root / 'tests/test_bch2_retention_permissions.py').read_bytes())
    assert proof['initImage'] == current['services']['init_permissions']['image']
    assert proof['initCommandSHA256'] == sha(current['services']['init_permissions']['command'][-1].encode())
    assert proof['actualAlpineInitializerExecuted'] is True
    assert proof['nativeInstallAndUpdateGeneratorsPreserveInitializer'] is True
    assert proof['liveAppNodeOrMinerStarted'] is False and proof['liveDataAccessed'] is False
    if check_baseline:
        protected = [n for n in git(root, 'ls-tree', '-r', '--name-only', row['baselineCommit']).decode().splitlines()
                     if n.startswith('willitmod-') and not n.startswith(APP + '/')]
        assert not git(root, 'diff', '--name-only', row['baselineCommit'], '--', *protected).strip(), 'Other application changed'
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-baseline', action='store_true')
    args = parser.parse_args()
    row = validate(check_baseline=args.check_baseline)
    print(json.dumps({'result': 'PASS', 'channel': row['channel'], 'version': row['version'],
                      'scope': 'Recipe-only Alpine fixtures and native rendering; no live miner recovery'}))
