"""Exact Core-only MAIN 0.9.183 successor: DigiByte Core 9.26.6 for Thaw Day."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-dgb'
BASELINE = '9c0fc81f22ea3e81060e098f7e5272480816b99f'
CHANNEL = 'MAIN'
VERSION = '0.9.183'
PREVIOUS_VERSION = '0.9.182'
RECORD = 'release-records/dgb-core-9.26.6-thaw-day-2026-11-10.json'
RECORD_SHA256 = '28747177e7864b7d3adfa8b4761a5eb99b636a3f5d5a1247d4baff5aa58b9014'
OLD_CORE = 'ghcr.io/willitmod/axedgb-core:0.9.181'
NEW_CORE = 'ghcr.io/willitmod/axedgb-core:9.26.6-dev.1@sha256:b10bb332316286348a6f0e52bc4da961135fe617ed9e1c4e415550c431f0a126'
UPSTREAM_COMMIT = '92330d952625e20aef2ee40671a179ef03872ac1'
COMPOSE = APP + '/docker-compose.yml'
MANIFEST = APP + '/umbrel-app.yml'
NOTE = ('Updates DigiByte Core from 9.26.5 to 9.26.6 for Thaw Day. Every DigiByte node and miner must run '
        '9.26.6 or newer from mainnet block 24,490,000; older nodes can disagree about valid blocks. Only the '
        'node image changes. App, pool and init images, ports, settings, the memory watchdog, the shutdown '
        'allowance and stored chain data are unchanged, and no reindex is requested. The first start after '
        'updating can take longer while Core checks DigiDollar history.')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def baseline_bytes(root, name):
    return git(root, 'show', BASELINE + ':' + name)


def record(root=ROOT):
    raw = (root / RECORD).read_bytes()
    assert sha(raw) == RECORD_SHA256, 'Unreviewed DGB Core record'
    row = json.loads(raw)
    assert (row['schemaVersion'], row['status']) == (1, 'qualified-core-image-package')
    assert (row['appId'], row['channel'], row['version'], row['previousVersion'], row['baselineCommit']) == (
        APP, CHANNEL, VERSION, PREVIOUS_VERSION, BASELINE)
    assert (row['previousCoreImage'], row['coreImage']) == (OLD_CORE, NEW_CORE)
    assert row['digibyteVersion'] == 'v9.26.6' and row['upstreamRelease']['commit'] == UPSTREAM_COMMIT
    evidence = row['imageEvidence']
    assert evidence['supervisorSHA256'] == evidence['previousSupervisorSHA256'], 'Memory supervisor must be unchanged'
    assert row['reindexRequested'] is False
    return row


def previous_model(current, root=ROOT):
    before = yaml.safe_load(baseline_bytes(root, COMPOSE))
    expected = copy.deepcopy(before)
    assert before['services']['dgbd']['image'] == OLD_CORE
    assert before['services']['app']['environment']['DGB_IMAGE'] == OLD_CORE
    expected['services']['dgbd']['image'] = NEW_CORE
    expected['services']['app']['environment']['DGB_IMAGE'] = NEW_CORE
    assert current == expected, 'Only the exact DGB Core image may change'
    return before


def previous_compose_bytes(raw, root=ROOT):
    row = record(root)
    before = baseline_bytes(root, COMPOSE)
    assert sha(before) == row['beforeComposeSHA256']
    image = f'    image: {OLD_CORE}\n'.encode()
    reference = f'      DGB_IMAGE: "{OLD_CORE}"\n'.encode()
    assert before.count(image) == 1 and before.count(reference) == 1
    expected = before.replace(image, f'    image: {NEW_CORE}\n'.encode(), 1)
    expected = expected.replace(reference, f'      DGB_IMAGE: "{NEW_CORE}"\n'.encode(), 1)
    assert raw == expected and sha(raw) == row['afterComposeSHA256'], 'Only the exact DGB Core image may change'
    previous_model(yaml.safe_load(raw), root)
    return before


def previous_manifest_bytes(raw, root=ROOT):
    row = record(root)
    before = baseline_bytes(root, MANIFEST)
    assert sha(before) == row['beforeManifestSHA256']
    previous = yaml.safe_load(before)
    assert previous['version'] == PREVIOUS_VERSION
    expected = dict(previous, version=VERSION, releaseNotes=NOTE)
    assert yaml.safe_load(raw) == expected, 'Only the DGB version and release note may change'
    assert sha(raw) == row['afterManifestSHA256']
    return before


def current_bytes(root, name):
    """A DGB package file as the previous MAIN release shipped it."""
    raw = (root / name).read_bytes()
    if name == COMPOSE:
        return previous_compose_bytes(raw, root)
    if name == MANIFEST:
        return previous_manifest_bytes(raw, root)
    return raw


def validate(root=ROOT, *, check_baseline=False):
    row = record(root)
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINE, '--', APP).decode().splitlines()
    actual = {str(p.relative_to(root)) for p in (root / APP).rglob('*') if p.is_file() or p.is_symlink()}
    assert actual == set(names), 'DGB package inventory changed'
    for name in names:
        path = root / name
        assert stat.S_ISREG(path.lstat().st_mode), 'DGB package symlink forbidden'
        mode = git(root, 'ls-tree', BASELINE, '--', name).decode().split()[0]
        assert ('100755' if path.stat().st_mode & 0o111 else '100644') == mode, 'DGB package mode changed'
        assert current_bytes(root, name) == baseline_bytes(root, name), 'Unrelated DGB package content changed'
    for name, digest in row['historicalRecordsSHA256'].items():
        assert sha((root / name).read_bytes()) == digest == sha(baseline_bytes(root, name)), 'Historical DGB record changed'
    if check_baseline:
        protected = [name for name in git(root, 'ls-tree', '-r', '--name-only', BASELINE).decode().splitlines()
                     if name.startswith('willitmod-') and not name.startswith(APP + '/')]
        assert not git(root, 'diff', '--name-only', BASELINE, '--', *protected).strip(), 'Other app changed'
    return row


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-baseline', action='store_true')
    args = parser.parse_args()
    row = validate(check_baseline=args.check_baseline)
    print(json.dumps({'result': 'PASS', 'channel': CHANNEL, 'version': VERSION, 'core': NEW_CORE,
                      'digibyte': row['digibyteVersion']}))
