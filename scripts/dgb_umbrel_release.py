"""Exact app-only MAIN 0.9.182 successor; no DEV/Core/init/pool promotion."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-dgb'
BASELINE = 'e2609aa61aa4c854de1453c2a23b0b3fedbc40d2'
VERSION = '0.9.182'
RECORD = 'DGB-UMBREL-AUTH-RELEASE-2026-10-16.json'
PUBLICATION = 'release-records/dgb-0.9.182-umbrel-authfix-delivery.json'
SOURCE = 'd42a2e9b3314c7f8b1859837ae319104395759fb'
TREE = '61825b8384e8b76847803295a06c862325ace28c'
IMAGE_REF = 'ghcr.io/willitmod/axedgb-app:0.9.182-umbrel-authfix.1@sha256:514e426281259905ba7d3dd0258e11a9fdf8393b2a7a4307b03db11e68dcc0ef'
RECORD_SHA256 = 'df5b4f4fac4288082dfce7d7121bb3d18b20b81b00770c9ff80ea7ab89be0071'
EXPORTS_SHA256 = '6d21c61f8c413ce7921b0b6ba0d76987ae8c27b9ed25a8fd957b77fffff50809'
NOTE = ('Fixes Umbrel 2 updates when the legacy authentication container is absent. '
        'Installations already blocked by the old authentication hook need that '
        'installed hook repaired once before retrying Update. '
        'Uses guarded optional authentication lookups and a compiled application with '
        'minified browser assets. Existing ports, node/pool/init images, settings and '
        'stored chain data are preserved.')
SHA256 = re.compile(r'[0-9a-f]{64}\Z')
DIGEST = re.compile(r'sha256:[0-9a-f]{64}\Z')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def predecessor(root, filename):
    return yaml.safe_load(git(root, 'show', f'{BASELINE}:{APP}/{filename}'))


def record(root=ROOT):
    raw = (root / RECORD).read_bytes()
    value = json.loads(raw)
    assert RECORD_SHA256 is not None, 'Protected DGB app publication and native image checks are pending'
    assert sha(raw) == RECORD_SHA256, 'Unreviewed DGB release record'
    assert value['schemaVersion'] == 1 and value['status'] == 'qualified'
    assert (value['appId'], value['channel'], value['version'], value['baselineCommit']) == (APP, 'MAIN', VERSION, BASELINE)
    assert (value['sourceRevision'], value['sourceTree']) == (SOURCE, TREE)
    assert value['imageRef'] == IMAGE_REF and IMAGE_REF is not None
    assert re.fullmatch(r'ghcr\.io/willitmod/axedgb-app:0\.9\.182-umbrel-authfix\.1@sha256:[0-9a-f]{64}', IMAGE_REF)
    return value


def backend_adapter(root):
    spec = importlib.util.spec_from_file_location('dgb_backend_successor', root / 'scripts/dgb_backend_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def model(before, release):
    after = copy.deepcopy(before)
    after['services']['app']['image'] = release['imageRef']
    return after


def admit_model(current, release, root=ROOT):
    before = predecessor(root, 'docker-compose.yml')
    expected = model(before, release)
    if current != expected:
        adapter = backend_adapter(root)
        adapter.admit_model(current, expected, adapter.record(root))
    assert current['services']['init']['image'] == 'ghcr.io/willitmod/axedgb-init:0.9.181'
    assert current['services']['dgbd']['image'] == 'ghcr.io/willitmod/axedgb-core:0.9.181'
    return before


def package_files(root):
    return {str(p.relative_to(root)): {'sha256': sha(p.read_bytes()), 'mode': oct(stat.S_IMODE(p.lstat().st_mode))}
            for p in (root / APP).rglob('*') if p.is_file() or p.is_symlink()}


def validate_package(root, release):
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINE, '--', APP).decode().splitlines()
    actual = package_files(root)
    assert set(actual) == set(names), 'Unreviewed DGB package inventory'
    if actual != release['packageFiles']:
        backend_adapter(root).validate_package(root)
        return
    for name in names:
        path = root / name
        assert stat.S_ISREG(path.lstat().st_mode), 'DGB package symlink forbidden'
        mode = git(root, 'ls-tree', BASELINE, '--', name).decode().split()[0]
        assert ('100755' if path.stat().st_mode & 0o111 else '100644') == mode
        if name == APP + '/docker-compose.yml':
            admit_model(yaml.safe_load(path.read_text()), release, root)
        elif name == APP + '/umbrel-app.yml':
            expected = predecessor(root, 'umbrel-app.yml')
            expected.update(version=VERSION, releaseNotes=NOTE)
            assert yaml.safe_load(path.read_text()) == expected, 'Only DGB version/release note may change'
        else:
            assert path.read_bytes() == git(root, 'show', f'{BASELINE}:{name}'), 'Unrelated DGB package content changed'
    assert sha((root / APP / 'exports.sh').read_bytes()) == EXPORTS_SHA256


def validate_publication(root, release):
    row = release['publication']
    assert row['path'] == PUBLICATION and SHA256.fullmatch(row['sha256'])
    raw = (root / row['path']).read_bytes()
    assert sha(raw) == row['sha256'], 'DGB delivery receipt changed'
    proof = json.loads(raw)
    assert proof['schemaVersion'] == 1 and proof['result'] == 'PASS'
    for key in ('version', 'sourceRevision', 'sourceTree', 'imageRef'):
        assert proof[key] == release[key]
    assert proof['anonymousIndexAndBothPlatformsVerified'] is True
    assert set(proof['platforms']) == {'amd64', 'arm64'}
    for architecture, p in proof['platforms'].items():
        assert {key: p[key] for key in ('manifestDigest', 'configDigest')} == release['platforms'][architecture]
        assert all(DIGEST.fullmatch(p[key]) for key in ('manifestDigest', 'configDigest'))
        assert SHA256.fullmatch(p['protectedExecutableSHA256'])
        for key in ('nativeStartupVerified', 'noApplicationPythonSources', 'noSourceMaps', 'allDistributedLayersAudited'):
            assert p[key] is True
        assert p['httpVersion'] == VERSION
    assert proof['strictBashAuthRegressionVerified'] is True
    assert proof['nativeUmbrelAppManagerInstallQualified'] is False
    assert proof['physicalMiningQualified'] is False
    assert proof['scope'] == ('Native AMD64/ARM64 compiled app runtime and public immutable images verified. '
        'The guarded auth exports are exercised under strict Bash, including the exact legacy MAIN failure. '
        'Native Umbrel app-manager installation follows catalogue publication; full chain sync and physical mining are not qualified.')
    return proof


def validate_baseline(root):
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINE).decode().splitlines()
    protected = [name for name in names if (name.startswith('willitmod-') and not name.startswith(APP + '/'))
        or (name.endswith('.json') and ('/' not in name or name.startswith('release-records/')))]
    assert protected and not git(root, 'diff', '--name-only', BASELINE, '--', *protected).decode().splitlines(), 'Other app or historical release record changed'
    before = {name for name in names if name.startswith('willitmod-')}
    current = {str(p.relative_to(root)) for folder in root.glob('willitmod-*') if folder.is_dir() for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
    assert current == before, 'App package inventory changed'


def validate(root=ROOT, *, check_baseline=False):
    release = record(root)
    validate_package(root, release)
    validate_publication(root, release)
    if check_baseline:
        validate_baseline(root)
    return release


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-baseline', action='store_true')
    args = parser.parse_args()
    value = validate(check_baseline=args.check_baseline)
    print(json.dumps({'result': 'PASS', 'version': value['version'], 'imageRef': value['imageRef'], 'initialBaselineChecked': args.check_baseline}))
