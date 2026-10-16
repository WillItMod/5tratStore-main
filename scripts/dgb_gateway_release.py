"""Closed one-hostname successor for the observed Umbrel 2 LAN ingress resolver."""
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
BASELINE = '00252d0788468716274b3733885e6a3dac36c208'
CHANNEL = 'MAIN'
VERSION = '0.9.182'
RECORD = 'release-records/dgb-gateway-hostname-delivery-2026-10-16.json'
RECORD_SHA256 = 'adb6f7c873169ec12e368ed09ea26e01ebc3ee84d05c5a1ade795b75c1c26acb'
HOSTNAME = 'axedgb-app'
COMPOSE = APP + '/docker-compose.yml'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def baseline_bytes(root, name=COMPOSE):
    return git(root, 'show', BASELINE + ':' + name)


def record(root=ROOT):
    raw = (root / RECORD).read_bytes()
    assert sha(raw) == RECORD_SHA256, 'Unreviewed DGB gateway record'
    row = json.loads(raw)
    assert (row['schemaVersion'], row['status']) == (1, 'qualified-package-and-observed-resolver-model')
    assert (row['appId'], row['channel'], row['version'], row['baselineCommit']) == (APP, CHANNEL, VERSION, BASELINE)
    assert (row['appProxyHost'], row['appService'], row['addedHostname']) == (HOSTNAME, 'app', HOSTNAME)
    assert row['runtimeBuildChanged'] is False and row['nativeGatewayRetryQualified'] is False
    assert row['physicalMiningQualified'] is False
    assert row['observedNative2Resolver']['sourceObservationSHA256'] == '7d2c02e675c9611699e1d54bf046be2d344d7e60025dabf2cced7485c46ccea3'
    assert row['priorBackendAcceptance']['receiptSHA256'] == '5b52d746d03a334166d113c800adbab9f1ff89aaca86d8802b899c8d0091a574'
    assert row['priorBackendAcceptance']['qualifiesNewGatewaySuccessor'] is False
    return row


def previous_compose_bytes(raw, root=ROOT):
    row = record(root)
    before = baseline_bytes(root)
    assert sha(before) == row['beforeComposeSHA256']
    assert before.count(b'  app:\n') == 1
    if row['hostnameAlreadyPresent']:
        assert yaml.safe_load(before)['services']['app']['hostname'] == HOSTNAME
        expected = before
    else:
        assert b'    hostname: axedgb-app\n' not in before
        expected = before.replace(b'  app:\n', b'  app:\n    hostname: axedgb-app\n', 1)
    assert raw == expected and sha(raw) == row['afterComposeSHA256'], 'Only the exact declared DGB gateway hostname may change'
    previous_gateway_model(yaml.safe_load(raw), root)
    return before


def previous_gateway_model(current, root=ROOT):
    row = record(root)
    before = yaml.safe_load(baseline_bytes(root))
    assert ('hostname' in before['services']['app']) is row['hostnameAlreadyPresent']
    expected = copy.deepcopy(before)
    if not row['hostnameAlreadyPresent']:
        expected['services']['app']['hostname'] = HOSTNAME
    assert current == expected, 'Only the exact declared DGB gateway hostname may change'
    assert current['services']['app_proxy']['environment']['APP_HOST'] == HOSTNAME
    # The new declared name is unique among all declared service/host names.
    for name, service in current['services'].items():
        if name != 'app':
            assert HOSTNAME not in (name, service.get('container_name'), service.get('hostname'))
    return before


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
        if name == COMPOSE:
            assert previous_compose_bytes(path.read_bytes(), root) == baseline_bytes(root)
        else:
            assert path.read_bytes() == baseline_bytes(root, name), 'Unrelated DGB package content changed'
    assert yaml.safe_load((root / APP / 'umbrel-app.yml').read_text())['version'] == VERSION
    for name, digest in row['historicalRecordsSHA256'].items():
        assert sha((root / name).read_bytes()) == digest == sha(baseline_bytes(root, name)), 'Historical release record changed'
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
    print(json.dumps({'result': 'PASS', 'channel': CHANNEL, 'version': VERSION, 'hostname': HOSTNAME,
                      'scope': 'Exact package and observed native resolver model; new gateway retry not qualified'}))
