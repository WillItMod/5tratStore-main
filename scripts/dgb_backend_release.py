"""Closed admission for the exact DGB DNS/SQL safety repair; no runtime promotion."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import stat
import subprocess
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = 'willitmod-dev-dgb'
BASELINE = '2807a919bbd677b3f2a7f64c7521fdaa58419736'
CHANNEL = 'MAIN'
VERSION = '0.9.182'
RECORD = 'DGB-BACKEND-SAFETY-2026-10-16.json'
RECORD_SHA256 = '368de09334748aa6678e5a41c0c2ca23d647fca05ede92b7e3386fe48bab34b1'
ALIASES = {'postgres': 'axedgb-postgres', 'dgbd': 'axedgb-core', 'miningcore': 'axedgb-miningcore'}
CHANGED = {APP + '/docker-compose.yml', APP + '/data/templates/miningcore.json.template'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def baseline_bytes(root, name):
    return git(root, 'show', BASELINE + ':' + name)


def section(command, name):
    start = command.index('# ' + name + '_BEGIN')
    end = command.index('# ' + name + '_END') + len('# ' + name + '_END')
    return command[start:end]


def record(root=ROOT):
    raw = (root / RECORD).read_bytes()
    assert sha(raw) == RECORD_SHA256, 'Unreviewed DGB backend repair record'
    value = json.loads(raw)
    assert value['schemaVersion'] == 1 and value['status'] == 'qualified-package-and-fixtures'
    assert (value['appId'], value['baselineCommit'], value['channel'], value['version']) == (APP, BASELINE, CHANNEL, VERSION)
    assert set(value['changedPackageFiles']) == CHANGED
    assert value['backendAliases'] == ALIASES
    assert value['runtimeBuildChanged'] is False
    assert value['nativeUmbrelRetryQualified'] is False and value['physicalMiningQualified'] is False
    return value


def gateway_adapter(root):
    spec = importlib.util.spec_from_file_location('dgb_gateway_successor', root / 'scripts/dgb_gateway_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def admit_model(current, before, release, root=ROOT):
    if 'hostname' in current.get('services', {}).get('app', {}):
        current = gateway_adapter(root).previous_gateway_model(current, root)
    expected = copy.deepcopy(before)
    for service, alias in ALIASES.items():
        expected['services'][service]['networks'] = {'default': {'aliases': [alias]}}
    init = expected['services']['init']
    init['environment'].update(DB_HOST=ALIASES['postgres'], DGB_RPC_HOST=ALIASES['dgbd'])
    app = expected['services']['app']['environment']
    app.update(PGHOST=ALIASES['postgres'], DGB_RPC_HOST=ALIASES['dgbd'], MININGCORE_API_URL='http://' + ALIASES['miningcore'] + ':4000')
    command = current['services']['init']['command']
    assert len(command) == 3 and command[:2] == init['command'][:2], 'DGB init launcher changed'
    assert sha(command[-1].encode()) == release['initCommandSHA256'], 'Unreviewed DGB init logic'
    for name, digest in release['initSectionsSHA256'].items():
        assert sha(section(command[-1].replace('$$', '$'), name).encode()) == digest, 'DGB safety section changed'
    init['command'] = command
    assert current == expected, 'Only exact backend names and reviewed init safety logic may change'
    return before


def validate_package(root=ROOT, release=None):
    release = release or record(root)
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINE, '--', APP).decode().splitlines()
    actual = {str(p.relative_to(root)) for p in (root / APP).rglob('*') if p.is_file() or p.is_symlink()}
    assert actual == set(names), 'DGB package inventory changed'
    for name in names:
        path = root / name
        assert stat.S_ISREG(path.lstat().st_mode), 'DGB package symlink forbidden'
        baseline_mode = git(root, 'ls-tree', BASELINE, '--', name).decode().split()[0]
        assert ('100755' if path.stat().st_mode & 0o111 else '100644') == baseline_mode, 'DGB package mode changed'
        if name in CHANGED:
            raw = path.read_bytes()
            if name == APP + '/docker-compose.yml' and sha(raw) != release['changedPackageFiles'][name]:
                raw = gateway_adapter(root).previous_compose_bytes(raw, root)
            assert sha(raw) == release['changedPackageFiles'][name], 'Unreviewed DGB repair bytes'
        else:
            assert path.read_bytes() == baseline_bytes(root, name), 'Unrelated DGB file changed'
    before = yaml.safe_load(baseline_bytes(root, APP + '/docker-compose.yml'))
    current = yaml.safe_load((root / APP / 'docker-compose.yml').read_text())
    admit_model(current, before, release, root)
    template = APP + '/data/templates/miningcore.json.template'
    assert (root / template).read_bytes() == baseline_bytes(root, template).replace(b'"host": "dgbd"', b'"host": "${DGB_RPC_HOST}"'), 'Only generic template daemon hosts may change'
    assert yaml.safe_load((root / APP / 'umbrel-app.yml').read_text())['version'] == VERSION
    images = {name: value['image'] for name, value in current['services'].items() if 'image' in value}
    assert images == release['runtimeImages'] == {name: value['image'] for name, value in before['services'].items() if 'image' in value}, 'DGB image changed'
    for name, digest in release['historicalRecordsSHA256'].items():
        assert sha((root / name).read_bytes()) == digest == sha(baseline_bytes(root, name)), 'Historical DGB release record changed'
    assert 'DROP TABLE' not in section(current['services']['init']['command'][-1], 'DGB_DATABASE_SETUP')
    validate_native_fixtures(root, release)
    return release


def validate_native_fixtures(root, release):
    receipt = release['nativePostgresqlFixtures']
    assert receipt['path'] == 'release-records/dgb-backend-safety-fixtures-2026-10-16.json'
    raw = (root / receipt['path']).read_bytes()
    assert sha(raw) == receipt['sha256'], 'Unreviewed native PostgreSQL fixture proof'
    proof = json.loads(raw)
    assert proof['schemaVersion'] == 1 and proof['result'] == 'PASS'
    assert proof['sqlBlockSHA256'] == release['initSectionsSHA256']['DGB_DATABASE_SETUP']
    assert proof['composeSHA256'][CHANNEL] == release['changedPackageFiles'][APP + '/docker-compose.yml']
    expected = {'pristine': True, 'complete': True, 'partial': False, 'auth_failure': False, 'wrong_host': False, 'sql_import_error': False, 'unsupported_blocks_poolid': False}
    assert len(proof['cases']) == len(expected) and {row['case'] for row in proof['cases']} == set(expected)
    for row in proof['cases']:
        assert row['expectedSuccess'] is expected[row['case']]
        assert (row['exitCode'] == 0) is expected[row['case']]
        assert row['foreignDatabaseUnchanged'] is True
        if row['case'] != 'pristine':
            assert row['beforeSHA256'] == row['afterSHA256'] and row['existingSchemaRowsSequencesPreserved'] is True
    assert proof['foreignSourceWriteStatements'] == 0
    assert proof['foreignSchemaRowsSequencesUnchanged'] is True and proof['onlyExtractedMarkedDbSetupExecuted'] is True
    for key in ('wholeInitOrNodeOrMinerExecuted', 'liveDataAccessed', 'hostPortsPublished', 'nativeUmbrelRetryQualified', 'physicalMiningQualified'):
        assert proof[key] is False
    return proof


def previous_backend_model(app_id, current, root=ROOT):
    if app_id != APP:
        return copy.deepcopy(current)
    before = yaml.safe_load(baseline_bytes(root, APP + '/docker-compose.yml'))
    admit_model(current, before, record(root), root)
    return copy.deepcopy(before)


def validate_baseline(root=ROOT):
    names = git(root, 'ls-tree', '-r', '--name-only', BASELINE).decode().splitlines()
    protected = [name for name in names if (name.startswith('willitmod-') and not name.startswith(APP + '/')) or (name.endswith('.json') and ('/' not in name or name.startswith('release-records/')))]
    assert protected and not git(root, 'diff', '--name-only', BASELINE, '--', *protected).decode().splitlines(), 'Other app or historical record changed'
    before = {name for name in names if name.startswith('willitmod-')}
    current = {str(p.relative_to(root)) for folder in root.glob('willitmod-*') if folder.is_dir() for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
    assert current == before, 'App inventory changed'


def validate(root=ROOT, *, check_baseline=False):
    value = validate_package(root)
    if check_baseline:
        validate_baseline(root)
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-baseline', action='store_true')
    args = parser.parse_args()
    value = validate(check_baseline=args.check_baseline)
    print(json.dumps({'result': 'PASS', 'scope': 'Exact catalogue repair and isolated native PostgreSQL fixtures; native retry not qualified', 'channel': CHANNEL, 'version': VERSION, 'initialBaselineChecked': args.check_baseline}))
