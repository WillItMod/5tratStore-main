"""Execute the recipe initializer in its actual Alpine image on private tmpfs.

The runtime tests deliberately use no app volumes, network or host ports.
Native rendering is optional and executes only the two extracted generators.
"""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bch2_retention_release_tests', ROOT / 'scripts/bch2_retention_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
APP = ROOT / release.APP
MODEL = yaml.safe_load((APP / 'docker-compose.yml').read_text())
INIT = MODEL['services']['init_permissions']
COMMAND = INIT['command'][-1].replace('$$', '$')
CAP = '/data/ui/state/ckpool-retention-capability.json'
SETUP = '''
set -eu
mkdir -p /data/outside
ln -s /data/outside /outside
mkdir -p /data/ui/state /data/pool/config /data/pool/www /data/node /outside/dir
printf 'checkpoint bytes\\n' > /data/ui/state/ckpool_accounting_checkpoint.json
printf 'lock bytes\\n' > /data/ui/state/ckpool_accounting_checkpoint.json.lock
printf 'pool configuration\\n' > /data/pool/config/ckpool.conf
printf 'raw pool evidence\\n' > /data/pool/www/ckpool.log
printf 'core data\\n' > /data/node/chain-sentinel
printf 'outside bytes\\n' > /outside/sentinel
printf 'outside directory bytes\\n' > /outside/dir/sentinel
printf 'multiply-linked bytes\\n' > /outside/hardlink-sentinel
chmod 400 /data/ui/state/* /data/pool/config/* /data/pool/www/* /data/node/* /outside/sentinel /outside/dir/sentinel /outside/hardlink-sentinel
ln -s /outside/sentinel /data/ui/symlink-file
ln -s /outside/dir /data/pool/symlink-directory
ln /outside/hardlink-sentinel /data/ui/hardlink-file
snapshot() { stat -c '%u:%g:%a:%i:%h' "$1"; sha256sum "$1"; }
snapshot /outside/sentinel > /outside/sentinel.before
snapshot /outside/dir/sentinel > /outside/dir.before
snapshot /outside/hardlink-sentinel > /outside/hardlink.before
snapshot /data/node/chain-sentinel > /outside/node.before
'''
ASSERTIONS = '''
test "$(stat -c '%u:%g:%a' /data/ui/state/ckpool_accounting_checkpoint.json)" = 1000:1000:660
test "$(stat -c '%u:%g:%a' /data/ui/state/ckpool_accounting_checkpoint.json.lock)" = 1000:1000:660
test "$(stat -c '%u:%g:%a' /data/pool/config/ckpool.conf)" = 1000:1000:660
test "$(stat -c '%u:%g:%a' /data/pool/www/ckpool.log)" = 1000:1000:660
test "$(cat /data/ui/state/ckpool_accounting_checkpoint.json)" = 'checkpoint bytes'
test "$(cat /data/ui/state/ckpool_accounting_checkpoint.json.lock)" = 'lock bytes'
test "$(cat /data/pool/www/ckpool.log)" = 'raw pool evidence'
test -d /data/pool/www/pool && test -d /data/pool/www/users
snapshot /outside/sentinel | cmp - /outside/sentinel.before
snapshot /outside/dir/sentinel | cmp - /outside/dir.before
snapshot /outside/hardlink-sentinel | cmp - /outside/hardlink.before
snapshot /data/node/chain-sentinel | cmp - /outside/node.before
'''
WRITABLE = '''
addgroup -g 1000 app
adduser -D -u 1000 -G app app
su app -s /bin/sh -c 'printf app-write >> /data/ui/state/ckpool_accounting_checkpoint.json; printf app-write >> /data/ui/state/ckpool_accounting_checkpoint.json.lock; printf app-write >> /data/pool/www/ckpool.log'
test "$(tail -c 9 /data/ui/state/ckpool_accounting_checkpoint.json)" = app-write
test "$(tail -c 9 /data/ui/state/ckpool_accounting_checkpoint.json.lock)" = app-write
test "$(tail -c 9 /data/pool/www/ckpool.log)" = app-write
'''


class RecipeReleaseTests(unittest.TestCase):
    def test_exact_recipe_only_package_keeps_images_source_and_retention_binding(self):
        row = release.validate(check_baseline=True)
        self.assertEqual(row['runtimeImages'], {name: service['image'] for name, service in MODEL['services'].items() if 'image' in service})
        self.assertEqual(MODEL['services']['app']['environment']['APP_VERSION'], row['version'])

    def test_image_mount_policy_and_initializer_changes_are_rejected(self):
        for service, field, value in (('app', 'image', 'moving:latest'), ('app', 'volumes', []),
                                      ('ckpool', 'command', []), ('bch2', 'stop_grace_period', '1s'),
                                      ('init_permissions', 'command', ['/bin/sh', '-c', 'true'])):
            changed = copy.deepcopy(MODEL)
            changed['services'][service][field] = value
            with self.subTest(service=service, field=field), self.assertRaises(AssertionError):
                release.previous_model(changed)
        changed = copy.deepcopy(MODEL)
        changed['x-5tratumos-stop-policy']['requiresRetention']['appSourceRevision'] = '0' * 40
        with self.assertRaises(AssertionError):
            release.previous_model(changed)

    def test_arbitrary_metadata_version_and_note_changes_are_rejected(self):
        current = yaml.safe_load((APP / 'umbrel-app.yml').read_text())
        for field, value in (('version', '99.0.0'), ('releaseNotes', 'replacement'), ('port', 9999)):
            changed = copy.deepcopy(current)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                release.previous_manifest(changed, 'umbrel-app.yml')


@unittest.skipUnless(os.environ.get('BCH2_RETENTION_DOCKER_RUNTIME') == '1', 'opt-in actual Alpine runtime not requested')
class AlpinePermissionTests(unittest.TestCase):
    def run_script(self, script):
        result = subprocess.run(['docker', 'run', '--rm', '--network', 'none', '--tmpfs', '/data',
                                 '-i', INIT['image'], *INIT['command'][:2], script], text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_protected_and_invalid_leases_keep_exact_bytes_owner_mode_inode(self):
        for owner, mode, content in (('0:0', '644', '{"expiresAt":9999999999}'), ('1000:1000', '666', 'untrusted malformed bytes')):
            with self.subTest(owner=owner, mode=mode):
                prepare = f'''printf '%s' '{content}' > {CAP}
chown {owner} {CAP}
chmod {mode} {CAP}
snapshot {CAP} > /outside/capability.before
'''
                preserved = f'snapshot {CAP} | cmp - /outside/capability.before\n'
                self.run_script(SETUP + prepare + COMMAND + '\n' + preserved + ASSERTIONS + COMMAND + '\n' + preserved + ASSERTIONS + WRITABLE)

    def test_absent_lease_is_not_created_and_normal_app_state_is_writable(self):
        self.run_script(SETUP + COMMAND + '\n' + f'test ! -e {CAP}\n' + ASSERTIONS + WRITABLE)

    def test_capability_symlink_and_hardlink_are_not_followed_or_promoted(self):
        for create in (f'ln -s /outside/sentinel {CAP}', f'ln /outside/sentinel {CAP}'):
            with self.subTest(create=create):
                self.run_script(SETUP + create + '\nsnapshot /outside/sentinel > /outside/sentinel.before\n' + COMMAND + '\n' +
                                'snapshot /outside/sentinel | cmp - /outside/sentinel.before\n' + ASSERTIONS)

    def test_directory_named_capability_is_pruned(self):
        self.run_script(SETUP + f'mkdir {CAP}\nprintf bad > {CAP}/sentinel\nchmod 400 {CAP}/sentinel\n' +
                        COMMAND + '\n' + f'test "$(stat -c \'%u:%g:%a\' {CAP}/sentinel)" = 0:0:400\n' + ASSERTIONS)

    def test_old_recipe_reproduces_permission_corruption(self):
        before = yaml.safe_load(release.baseline_bytes(ROOT, release.APP + '/docker-compose.yml'))
        command = before['services']['init_permissions']['command'][-1].replace('$$', '$')
        self.run_script(SETUP + f'printf lease > {CAP}\nchmod 644 {CAP}\n' + command + '\n' +
                        f'test "$(stat -c \'%u:%g:%a\' {CAP})" = 1000:1000:664\n')


@unittest.skipUnless(os.environ.get('BCH2_RETENTION_NATIVE_SOURCE'), 'opt-in exact native OS source not provided')
class NativeRenderTests(unittest.TestCase):
    def test_actual_native_install_and_update_generators_preserve_init_command(self):
        platform = Path(os.environ['BCH2_RETENTION_NATIVE_SOURCE'])
        cli = (platform / 'bin/5tratumos').read_text()
        blocks = [s for s in re.findall(r"python3 - <<'PY'[^\n]*\n(.*?)\nPY\n", cli, re.S)
                  if 'compose_path = root / store_dir / "docker-compose.yml"' in s]
        self.assertEqual(len(blocks), 2)
        with tempfile.TemporaryDirectory(prefix='bch2-native-render-') as temp:
            socket_path = Path(temp) / 'docker.sock'
            with socket.socket(socket.AF_UNIX) as fixture_socket:
                fixture_socket.bind(str(socket_path))
            socket_path.chmod(0o660)
            for index, block in enumerate(blocks):
                dest = Path(temp) / str(index)
                dest.mkdir()
                env = dict(os.environ, STORE_CHANNEL=release.channel().lower(), STORE_ROOT=str(ROOT), STORE_DIR=release.APP,
                           DEST=str(dest), APP_ID='axebch2', STORE_PORT='21223', OUT_FILE='docker-compose.yml',
                           STOP_POLICY_CHECKER=str(platform / 'daemon/app_stop_policy.py'),
                           SOCKET_ACCESS_CHECKER=str(platform / 'daemon/docker_socket_access.py'),
                           BCH2_TEST_SOCKET_PATH=str(socket_path), BCH2_TEST_NATIVE_SOURCE=str(platform))
                # The generator is unchanged. Substitute only Docker socket
                # metadata with a real isolated Unix socket on non-Linux hosts.
                driver = '''import os
original_stat = os.stat
def fixture_stat(path, *args, **kwargs):
    if path in ('/var/run/docker.sock', '/run/docker.sock'):
        path = os.environ['BCH2_TEST_SOCKET_PATH']
    return original_stat(path, *args, **kwargs)
os.stat = fixture_stat
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(os.environ['BCH2_TEST_NATIVE_SOURCE']) / 'daemon'))
import pool_retention_capability
# A source checkout is not a root-owned installed OS. Parse its exact real
# contract bytes as a fixture; protected-file admission is tested by the OS.
contracts = pool_retention_capability.parse_contracts(json.loads(pool_retention_capability.CONTRACT_FILE.read_text()))
pool_retention_capability.load_contracts = lambda: contracts
'''
                result = subprocess.run([sys.executable, '-c', driver + block], env=env, capture_output=True, text=True, timeout=20)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                rendered = yaml.safe_load((dest / 'docker-compose.yml').read_text())
                self.assertEqual(rendered['services']['init_permissions']['command'], INIT['command'])
                self.assertEqual(rendered['services']['app']['environment']['APP_VERSION'], release.VERSIONS[release.channel()])
                for name in ('app', 'bch2', 'ckpool'):
                    self.assertEqual(rendered['services'][name]['image'], MODEL['services'][name]['image'])


if __name__ == '__main__':
    unittest.main()
