"""Exact XEC node-only successor: Bitcoin ABC 0.34.3 image, nothing else."""
import argparse
import json
from pathlib import Path
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-xec'
RECORD = 'XEC-NODE-2026-11-10.json'
BASELINE = '9c0fc81f22ea3e81060e098f7e5272480816b99f'
COMPOSE = APP + '/docker-compose.yml'
MANIFEST = APP + '/umbrel-app.yml'
CHANGED = {COMPOSE, MANIFEST}
NOTE = ('Updates the eCash node to Bitcoin ABC 0.34.3, required to stay on the network after the 15 November 2026 '
        'upgrade at 12:00 UTC. Only the node image changes. The app, pool, settings, ports and chain data are unchanged, '
        'and no reindex is needed.')


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def baseline_bytes(root, name):
    return git(root, 'show', BASELINE + ':' + name)


def record(root=ROOT):
    row = json.loads((root / RECORD).read_text())
    assert (row['appId'], row['channel'], row['baselineCommit']) == (APP, 'MAIN', BASELINE)
    assert (row['coreVersion'], row['upstreamRevision']) == ('0.34.3', '5621f13e073c007bed66a35fdfda3bc67772bab6')
    return row


def validate(root=ROOT):
    row = record(root)
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINE, '--', APP).decode().splitlines()
    actual = {str(p.relative_to(root)) for p in (root / APP).rglob('*') if p.is_file() or p.is_symlink()}
    assert actual == set(names), 'XEC package inventory changed'
    old, new = row['previousNodeImageRef'], row['nodeImageRef']
    for name in names:
        path = root / name
        assert stat.S_ISREG(path.lstat().st_mode), 'XEC package symlink forbidden'
        mode = git(root, 'ls-tree', BASELINE, '--', name).decode().split()[0]
        assert ('100755' if path.stat().st_mode & 0o111 else '100644') == mode, 'XEC package mode changed'
        before = baseline_bytes(root, name)
        if name == COMPOSE:
            lines = (f'    image: {old}\n'.encode(), f'      XECD_IMAGE: "{old}"\n'.encode())
            assert all(before.count(line) == 1 for line in lines)
            expected = before.replace(lines[0], f'    image: {new}\n'.encode(), 1)
            expected = expected.replace(lines[1], f'      XECD_IMAGE: "{new}"\n'.encode(), 1)
            assert path.read_bytes() == expected, 'Only the XEC node image may change'
        elif name == MANIFEST:
            previous = yaml.safe_load(before)
            current = yaml.safe_load(path.read_text())
            assert previous['version'] == row['previousPackageVersion']
            expected = dict(previous, version=row['version'], releaseNotes=NOTE + '\n' + previous['releaseNotes'])
            assert current == expected, 'Only the XEC version and new release note may change'
        else:
            assert path.read_bytes() == before, 'Unrelated XEC package content changed'
    return row


def historical_protected_paths(root, previous_commit, protected):
    """Admit only this exact successor before an older other-app comparison."""
    validate(root)
    assert CHANGED <= set(protected), 'Historical XEC package inventory differs'
    for name in CHANGED:
        assert baseline_bytes(root, name) == git(root, 'show', previous_commit + ':' + name), 'Historical XEC predecessor bytes differ'
        mode = git(root, 'ls-tree', BASELINE, '--', name).decode().split()[0]
        historical = git(root, 'ls-tree', previous_commit, '--', name).decode().split()[0]
        assert mode == historical, 'Historical XEC predecessor mode differs'
    return [name for name in protected if name not in CHANGED]


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    row = validate()
    print(json.dumps({'result': 'PASS', 'channel': row['channel'], 'version': row['version'], 'node': row['nodeImageRef']}))
