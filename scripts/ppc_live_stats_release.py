"""Exact AxePPC live-statistics app successor, before frozen historical contracts."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-ppc'
RECORD = 'PPC-LIVE-STATS-2026-11-16.json'
RECORD_SHA256 = '7a9d1d4f64e45597ff7891b389bccba137e0578cf3e5b5cbfc48b98db665e061'
VERSION = '0.2.40'
PRIOR_IMAGE = 'ghcr.io/willitmod/axeppc-app-umbrel-dev:0.2.38-mux.0264b623c305@sha256:959012f43b4ef82a73cd33bbf25f894072e66fbfe00733fbddde0b4da8651533'
NODE_IMAGE = 'ghcr.io/willitmod/axeppc-peercoind:0.15.2ppc-node.7b8e9374247e@sha256:20b5d3c9908fbb8e6a1444304d2a34be8e014667acff130bdb2dfe42768658cc'
NOTE = 'Shows active workers from recent accepted shares and the current Peercoin mining target. Historical worker records remain available, and unavailable mining targets are shown explicitly. The Peercoin 0.15.2 node, pool, payout settings and stored data are retained.'
MANIFESTS = ('umbrel-app.yml', 'global-app.yml', '5tratstore-app.yml')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return sha(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def record(root=ROOT):
    raw = (root / RECORD).read_bytes()
    assert sha(raw) == RECORD_SHA256, 'Unreviewed PPC live-statistics release record'
    row = json.loads(raw)
    assert row['schemaVersion'] == 1 and row['status'] == 'qualified-app-only'
    assert row['appId'] == APP and row['channel'] in ('DEV', 'MAIN')
    assert row['applicationVersion'] == VERSION and row['releaseNotePrefix'] == NOTE
    assert row['packageVersion'] == VERSION + ('-dev' if row['channel'] == 'DEV' else '')
    assert row['previousPackageVersion'] == '0.2.39' + ('-dev' if row['channel'] == 'DEV' else '')
    assert row['priorImageRef'] == PRIOR_IMAGE and row['nodeImageRef'] == NODE_IMAGE
    assert re.fullmatch(r'[0-9a-f]{40}', row['baselineCommit'])
    assert re.fullmatch(r'[0-9a-f]{40}', row['sourceRevision'])
    assert re.fullmatch(r'[0-9a-f]{40}', row['sourceTree'])
    assert row['sourceRepository'] == 'https://github.com/WillItMod/AxePPC_Build'
    tag = f"ghcr.io/willitmod/axeppc-app-umbrel-dev:{VERSION}-mux.{row['sourceRevision'][:12]}"
    assert re.fullmatch(re.escape(tag) + r'@sha256:[0-9a-f]{64}', row['imageRef'])
    assert isinstance(row['publicationRun'], int) and row['publicationRun'] > 0
    assert set(row['platforms']) == {'amd64', 'arm64'}
    for platform in row['platforms'].values():
        assert set(platform) == {'manifestDigest', 'configDigest'}
        assert all(re.fullmatch(r'sha256:[0-9a-f]{64}', value) for value in platform.values())
    expected_changes = [['services', 'app', 'image']]
    if row['channel'] == 'DEV':
        expected_changes.append(['services', 'app', 'environment', 'APP_VERSION_SUFFIX'])
    assert row['runtimeChanges'] == expected_changes
    assert row['qualification']['nativeRuntimeArchitectures'] == ['amd64', 'arm64']
    assert row['qualification']['provenanceVerified'] is True
    assert row['qualification']['sbomVerified'] is True
    assert row['qualification']['automaticChainRecovery'] is False
    return row


def baseline_bytes(root, name):
    return git(root, 'show', record(root)['baselineCommit'] + ':' + name)


def package_files(root=ROOT):
    row = record(root)
    return git(root, 'ls-tree', '-r', '--name-only', row['baselineCommit'], '--', APP).decode().splitlines()


def expected_bytes(root, name):
    row = record(root)
    before = baseline_bytes(root, name)
    filename = Path(name).name
    if name == APP + '/docker-compose.yml':
        old = f'    image: {PRIOR_IMAGE}\n'.encode()
        assert before.count(old) == 1
        after = before.replace(old, f"    image: {row['imageRef']}\n".encode(), 1)
        if row['channel'] == 'DEV':
            suffix = b'      APP_VERSION_SUFFIX: "-dev.1"\n'
            assert after.count(suffix) == 1
            after = after.replace(suffix, b'      APP_VERSION_SUFFIX: "-dev"\n', 1)
        return after
    if name.startswith(APP + '/') and name.count('/') == 1 and filename in MANIFESTS:
        old = f'version: "{row["previousPackageVersion"]}"\n'.encode()
        assert before.count(old) == 1 and before.count(b'releaseNotes: >-\n') == 1
        after = before.replace(old, f'version: "{row["packageVersion"]}"\n'.encode(), 1)
        return after.replace(b'releaseNotes: >-\n', b'releaseNotes: >-\n  ' + NOTE.encode() + b'\n\n', 1)
    return before


def previous_bytes(root, name, raw=None):
    """Reverse only exact successor bytes; unrelated packages pass through."""
    raw = (root / name).read_bytes() if raw is None else raw
    if not name.startswith(APP + '/'):
        return raw
    before = baseline_bytes(root, name)
    if raw == before:
        return raw
    assert raw == expected_bytes(root, name), 'Unreviewed PPC live-statistics bytes: ' + name
    return before


def previous_model(app_id, current, root=ROOT):
    if app_id != APP:
        return copy.deepcopy(current)
    name = APP + '/docker-compose.yml'
    before = yaml.safe_load(baseline_bytes(root, name))
    if current == before:
        return copy.deepcopy(current)
    assert current == yaml.safe_load(expected_bytes(root, name)), 'Unreviewed PPC live-statistics runtime'
    return before


def previous_manifest(app_id, current, filename='umbrel-app.yml', root=ROOT):
    if app_id != APP:
        return copy.deepcopy(current)
    name = APP + '/' + filename
    before = yaml.safe_load(baseline_bytes(root, name))
    if current == before:
        return copy.deepcopy(current)
    assert current == yaml.safe_load(expected_bytes(root, name)), 'Unreviewed PPC live-statistics manifest'
    return before


def package_version(app_id, historical, root=ROOT):
    if app_id != APP:
        return historical
    row = record(root)
    assert historical in (row['previousPackageVersion'], row['packageVersion'])
    return row['packageVersion']


def validate(root=ROOT):
    row = record(root)
    names = package_files(root)
    actual = {str(path.relative_to(root)) for path in (root / APP).rglob('*')
              if path.is_file() or path.is_symlink()}
    assert actual == set(names), 'PPC package inventory changed'
    for name in names:
        path = root / name
        assert stat.S_ISREG(path.lstat().st_mode), 'PPC package symlink forbidden'
        mode = git(root, 'ls-tree', row['baselineCommit'], '--', name).decode().split()[0]
        assert mode == ('100755' if path.stat().st_mode & 0o111 else '100644'), 'PPC package mode changed'
        assert path.read_bytes() == expected_bytes(root, name), 'PPC package content differs: ' + name
    compose = yaml.safe_load((root / APP / 'docker-compose.yml').read_text())
    before = previous_model(APP, compose, root)
    assert compose['services']['ppcd']['image'] == NODE_IMAGE
    assert compose['services']['app']['environment']['PPCD_IMAGE'] == NODE_IMAGE
    assert digest(compose) == row['afterModelSHA256'] and digest(before) == row['beforeModelSHA256']
    for filename in row['beforeManifestSHA256']:
        manifest = yaml.safe_load((root / APP / filename).read_text())
        before_manifest = previous_manifest(APP, manifest, filename, root)
        assert digest(manifest) == row['afterManifestSHA256'][filename]
        assert digest(before_manifest) == row['beforeManifestSHA256'][filename]
    return row


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    row = validate()
    print(json.dumps({'result': 'PASS', 'channel': row['channel'], 'version': row['packageVersion'], 'image': row['imageRef']}))
