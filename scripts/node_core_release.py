"""Exact node-only successors (2026-11-10): AxeBTC Core 30.4, AxeBCH BCHN 29.2.0, AxePPC 0.15.2.

Each app changes only its node image and the app's reference to that image,
plus the package version and one new release note. Older release contracts
read the package through the reverse functions here, so they still apply.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'NODE-CORE-2026-11-10.json'
MANIFESTS = ('umbrel-app.yml', 'global-app.yml', '5tratstore-app.yml')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def record(root=ROOT):
    path = root / RECORD
    if not path.is_file():
        return None
    row = json.loads(path.read_text())
    assert row['schemaVersion'] == 1 and row['status'] == 'qualified-node-only'
    for app_id, app in row['apps'].items():
        assert len(app['changes']) == 2, 'Exactly the node image and its app reference may change'
        services = {tuple(change['path'][:2]) for change in app['changes']}
        assert ('services', 'app') in services and len(services) == 2
        assert all(change['after'] == app['nodeImageRef'] and change['before'] == app['previousNodeImageRef']
                   for change in app['changes'])
    return row


def app_row(app_id, root=ROOT):
    row = record(root)
    return None if row is None else row['apps'].get(app_id)


def baseline_bytes(root, name):
    return git(root, 'show', record(root)['baselineCommit'] + ':' + name)


def previous_node_model(app_id, current, root=ROOT):
    """Reverse this node-only release; any other model passes through unchanged."""
    row = app_row(app_id, root)
    if row is None or digest(current) != row['afterModelSHA256']:
        return copy.deepcopy(current)
    restored = copy.deepcopy(current)
    for change in row['changes']:
        node = restored
        for key in change['path'][:-1]:
            node = node[key]
        assert node[change['path'][-1]] == change['after']
        node[change['path'][-1]] = change['before']
    assert digest(restored) == row['beforeModelSHA256'], 'Only the node image may change'
    return restored


def previous_node_manifest(app_id, current, filename='umbrel-app.yml', root=ROOT):
    row = app_row(app_id, root)
    if row is None or current.get('version') != row['version']:
        return copy.deepcopy(current)
    restored = copy.deepcopy(current)
    restored['version'] = row['previousVersion']
    prefix = row['note'] + '\n'
    assert restored['releaseNotes'].startswith(prefix), 'Only the node release note may be added'
    restored['releaseNotes'] = restored['releaseNotes'][len(prefix):]
    assert digest(restored) == row['beforeManifestSHA256'][filename], 'Only the version and node release note may change'
    return restored


def node_package_version(app_id, historical, root=ROOT):
    row = app_row(app_id, root)
    if row is None:
        return historical
    assert historical in (row['previousVersion'], row['version']), 'Unexpected preceding package version'
    return row['version']


def expected_bytes(root, app_id, name, before):
    """The exact bytes this release ships, derived from the baseline bytes."""
    row = record(root)['apps'][app_id]
    filename = Path(name).name
    if filename == 'docker-compose.yml':
        old, new = row['previousNodeImageRef'], row['nodeImageRef']
        after = before
        for change in row['changes']:
            key = change['path'][-1]
            if key == 'image':
                line = f'    image: {old}\n'.encode()
                assert after.count(line) == 1
                after = after.replace(line, f'    image: {new}\n'.encode(), 1)
            else:
                quoted = f'      {key}: "{old}"\n'.encode()
                plain = f'      {key}: {old}\n'.encode()
                if after.count(quoted) == 1:
                    after = after.replace(quoted, f'      {key}: "{new}"\n'.encode(), 1)
                else:
                    assert after.count(plain) == 1
                    after = after.replace(plain, f'      {key}: "{new}"\n'.encode(), 1)
        return after
    if filename in MANIFESTS:
        version = f'version: "{row["previousVersion"]}"\n'.encode()
        assert before.count(version) == 1 and before.count(b'releaseNotes: >-\n') == 1
        after = before.replace(version, f'version: "{row["version"]}"\n'.encode(), 1)
        return after.replace(b'releaseNotes: >-\n', b'releaseNotes: >-\n  ' + row['note'].encode() + b'\n\n', 1)
    return before


def changed_files(root=ROOT):
    row = record(root)
    names = set()
    for app_id in row['apps']:
        listed = git(root, 'ls-tree', '-r', '--name-only', row['baselineCommit'], '--', app_id).decode().splitlines()
        names.update(name for name in listed if Path(name).name in ('docker-compose.yml', *MANIFESTS)
                     and name.count('/') == 1)
    return names


def current_bytes(root, name):
    """A package file as the previous release shipped it."""
    raw = (root / name).read_bytes()
    row = record(root)
    if row is None or name not in changed_files(root):
        return raw
    before = baseline_bytes(root, name)
    assert raw == expected_bytes(root, name.split('/', 1)[0], name, before), 'Unreviewed node release bytes: ' + name
    return before


def validate(root=ROOT):
    row = record(root)
    assert row is not None, 'Node release record missing'
    for app_id, app in row['apps'].items():
        names = git(root, 'ls-tree', '-r', '--name-only', row['baselineCommit'], '--', app_id).decode().splitlines()
        actual = {str(p.relative_to(root)) for p in (root / app_id).rglob('*') if p.is_file() or p.is_symlink()}
        assert actual == set(names), 'Package inventory changed: ' + app_id
        for name in names:
            path = root / name
            assert stat.S_ISREG(path.lstat().st_mode), 'Package symlink forbidden'
            mode = git(root, 'ls-tree', row['baselineCommit'], '--', name).decode().split()[0]
            assert ('100755' if path.stat().st_mode & 0o111 else '100644') == mode, 'Package mode changed'
            assert current_bytes(root, name) == baseline_bytes(root, name), 'Unrelated package content changed: ' + name
        compose = yaml.safe_load((root / app_id / 'docker-compose.yml').read_text())
        assert digest(compose) == app['afterModelSHA256']
        assert digest(previous_node_model(app_id, compose, root)) == app['beforeModelSHA256']
        for filename in app['beforeManifestSHA256']:
            manifest = yaml.safe_load((root / app_id / filename).read_text())
            assert manifest['version'] == app['version']
            assert digest(previous_node_manifest(app_id, manifest, filename, root)) == app['beforeManifestSHA256'][filename]
    return row


def historical_protected_paths(root, previous_commit, protected):
    """Admit only this exact successor before an older other-app comparison."""
    validate(root)
    reviewed = changed_files(root)
    assert reviewed <= set(protected), 'Historical node package inventory differs'
    row = record(root)
    for name in reviewed:
        assert baseline_bytes(root, name) == git(root, 'show', previous_commit + ':' + name), 'Historical predecessor bytes differ: ' + name
        mode = git(root, 'ls-tree', row['baselineCommit'], '--', name).decode().split()[0]
        assert mode == git(root, 'ls-tree', previous_commit, '--', name).decode().split()[0], 'Historical predecessor mode differs'
    return [name for name in protected if name not in reviewed]


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    row = validate()
    print(json.dumps({'result': 'PASS', 'channel': row['channel'],
                      'apps': {app_id: app['version'] for app_id, app in row['apps'].items()}}))
