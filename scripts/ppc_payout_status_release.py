#!/usr/bin/env python3
"""Exact application-only payout-status successor, before historical PPC gates.

The published image and record hashes are reviewed source bindings. Editable
JSON never authorizes another image, setting, node, pool, or release claim.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-ppc'
RECORD_NAME = 'PPC-PAYOUT-STATUS-2026-10-21.json'
BASELINES = {'DEV': '80068694f882d44401d92ed04e9ae029e59ae5b8', 'MAIN': '3e05eb57cbe1688c7660f690ac4afa0dce902611'}
VERSIONS = {'DEV': '0.2.38-dev.1', 'MAIN': '0.2.38'}
BEFORE_VERSIONS = {'DEV': '0.2.37-dev.1', 'MAIN': '0.2.37'}
PREDECESSOR_IMAGE = 'ghcr.io/willitmod/axeppc-app-umbrel-dev:0.2.37-mux.5b0aac96a475@sha256:df22d1f1ba4f607d7422945cbdb0ec4ad348b9ce7ddd578d8179849db45d536d'
IMAGE = 'ghcr.io/willitmod/axeppc-app-umbrel-dev:0.2.38-mux.a3764b817397@sha256:822ecd4f43f22a469720cb30ce2f4f8c7b7c24d1be8d1fde94e0b1fc87aa25f9'
SOURCE_REVISION = 'a3764b8173971e3b155073e5794bfcd1b602f706'
SOURCE_TREE = '82518e630ee7dae3cddcdde45a6fc2a2026806a9'
PUBLICATION_RUN = 39585921897
PLATFORMS = {'amd64': {'manifestDigest': 'sha256:bfedde8c410fca2c8bd0903207e93db111450765ae0aefb90483f2f1bef4d2d5', 'configDigest': 'sha256:4db57951172bba378d79a2f42d38325acd1b2105836395a18371670522288c99'}, 'arm64': {'manifestDigest': 'sha256:2afab10904e0ce5f9fee621d5374777bd50dc837fca6857f8adfc31f7b600c55', 'configDigest': 'sha256:464758f9e41a4ff89546a5f3c5e586810b5d8c974f078ee1cb910009d98aac5a'}}
LOCKS = {'DEV': '22d22c804eb2459462ad9fd3d7748a66e5963e746a0fdaa9ef25668557138b13', 'MAIN': '9ae1ba215d9e3a842e5b03bec039761ae9ea7fddbd9fc57f6be75a2877a63f1c'}
MIGRATION_NAME = 'release-records/ppc-0.2.38-native-arm64-migration.json'
MIGRATION_SHA256 = '6d2ece398f6b2d03cf85f47511d57c0548ab5f13ba89a0d17ed31f1d85836e9c'
NOTE = 'Payout status now distinguishes node-validated, invalid, missing and not-yet-validated addresses. The channel label is informational. Node-rejected addresses are never saved, and an unavailable node is shown explicitly. Use a bare native Peercoin receiving address without a peercoin: prefix. Existing payout settings, pool configuration and stored data are retained.'
OLD_ADDRESS_HELP = 'Payout address must be a Base58 Peercoin address.'
ADDRESS_HELP = 'Use a bare native Peercoin receiving address without a peercoin: prefix. Legacy Base58 P... addresses are recommended; the node validates the address.'


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(model):
    return sha256(json.dumps(model, sort_keys=True, separators=(',', ':')).encode())


def git(root, *arguments):
    return subprocess.check_output(['git', *arguments], cwd=root)


def record(root=ROOT):
    raw = (root / RECORD_NAME).read_bytes()
    result = json.loads(raw)
    channel = result.get('channel')
    assert channel in BASELINES, 'Unexpected payout-status channel'
    assert sha256(raw) == LOCKS[channel], 'Unreviewed payout-status release record'
    assert result['schemaVersion'] == 1 and result['appId'] == APP
    assert result['baselineCommit'] == BASELINES[channel]
    assert result['sourceRepository'] == 'https://github.com/WillItMod/AxePPC_Build'
    assert (result['sourceRevision'], result['sourceTree']) == (SOURCE_REVISION, SOURCE_TREE)
    assert result['imageRef'] == IMAGE and result['priorImageRef'] == PREDECESSOR_IMAGE
    assert result['publicationRun'] == PUBLICATION_RUN and result['platforms'] == PLATFORMS
    assert result['applicationVersion'] == '0.2.38'
    assert result['packageVersion'] == VERSIONS[channel]
    assert result['previousPackageVersion'] == BEFORE_VERSIONS[channel]
    assert result['releaseNotePrefix'] == NOTE
    assert result['runtimeChanges'] == [['services', 'app', 'image']]
    assert result['qualificationScope']['isolatedNativeArm64ExactImageMigration'] == {
        'path': MIGRATION_NAME, 'sha256': MIGRATION_SHA256, 'platform': 'linux/arm64',
        'stages': 9, 'assertions': 218, 'httpRequests': 57,
        'scope': 'Isolated exact-image fixture volumes, real application HTTP and native Peercoin node validation; OS app-manager update and real mining payouts are not claimed.'}
    migration_raw = (root / MIGRATION_NAME).read_bytes()
    assert sha256(migration_raw) == MIGRATION_SHA256, 'Unreviewed isolated migration receipt'
    migration = json.loads(migration_raw)
    assert (migration['revision'], migration['newImage'], migration['oldImage']) == (SOURCE_REVISION, IMAGE, PREDECESSOR_IMAGE)
    assert migration['outcome'] == 'passed' and len(migration['stages']) == 9
    assert all(row['outcome'] == 'passed' for row in migration['stages'])
    assert sum(row['assertions'] for row in migration['stages']) == 218
    assert sum(row['httpRequests'] for row in migration['stages']) == 57
    return result


def predecessor(filename, root=ROOT):
    channel = record(root)['channel']
    return yaml.safe_load(git(root, 'show', f'{BASELINES[channel]}:{APP}/{filename}'))


def expected_model(root=ROOT):
    model = predecessor('docker-compose.yml', root)
    assert model['services']['app']['image'] == PREDECESSOR_IMAGE
    model['services']['app']['image'] = IMAGE
    return model


def previous_model(app_id, current, root=ROOT):
    if app_id != APP:
        return copy.deepcopy(current)
    before = predecessor('docker-compose.yml', root)
    if current == before:
        return copy.deepcopy(current)
    assert current == expected_model(root), 'Unreviewed complete PPC runtime model'
    return before


def expected_manifest(root=ROOT):
    channel = record(root)['channel']
    manifest = predecessor('umbrel-app.yml', root)
    assert manifest['version'] == BEFORE_VERSIONS[channel]
    assert manifest['description'].count(OLD_ADDRESS_HELP) == 1
    manifest['version'] = VERSIONS[channel]
    manifest['description'] = manifest['description'].replace(OLD_ADDRESS_HELP, ADDRESS_HELP)
    manifest['releaseNotes'] = NOTE + '\n' + manifest['releaseNotes']
    return manifest


def previous_manifest(app_id, current, root=ROOT):
    if app_id != APP:
        return copy.deepcopy(current)
    before = predecessor('umbrel-app.yml', root)
    if current == before:
        return copy.deepcopy(current)
    assert current == expected_manifest(root), 'Unreviewed complete PPC manifest'
    return before


def package_version(app_id, historical, root=ROOT):
    if app_id != APP:
        return historical
    channel = record(root)['channel']
    assert historical in (BEFORE_VERSIONS[channel], VERSIONS[channel]), 'Unexpected preceding PPC version'
    return VERSIONS[channel]


def validate(root=ROOT, *, check_catalogue=False):
    release = record(root)
    current = yaml.safe_load((root / APP / 'docker-compose.yml').read_text())
    assert current == expected_model(root), 'Current PPC image or runtime configuration differs'
    assert digest(current) == release['afterModelSHA256']
    assert digest(previous_model(APP, current, root)) == release['beforeModelSHA256']
    manifest = yaml.safe_load((root / APP / 'umbrel-app.yml').read_text())
    assert manifest == expected_manifest(root), 'Current PPC manifest differs'
    assert digest(manifest) == release['afterManifestSHA256']
    assert digest(previous_manifest(APP, manifest, root)) == release['beforeManifestSHA256']
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINES[release['channel']]).decode().splitlines()
    for name in names:
        if name.startswith(APP + '/') and name not in {APP + '/docker-compose.yml', APP + '/umbrel-app.yml'}:
            assert (root / name).read_bytes() == git(root, 'show', f"{release['baselineCommit']}:{name}"), 'Unrelated PPC package file changed'
    if check_catalogue:
        for name in names:
            if (name.startswith('willitmod-') and not name.startswith(APP + '/')) or name.endswith('.json'):
                assert (root / name).read_bytes() == git(root, 'show', f"{release['baselineCommit']}:{name}"), 'Preexisting app or release record changed'
    return release


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-catalogue', action='store_true', help='Initial delivery only: retain every other package and historical record')
    args = parser.parse_args()
    release = validate(check_catalogue=args.check_catalogue)
    print(json.dumps({'status': 'PASS', 'channel': release['channel'], 'version': release['packageVersion'],
                      'image': release['imageRef'], 'initialCatalogueChecked': args.check_catalogue}))
