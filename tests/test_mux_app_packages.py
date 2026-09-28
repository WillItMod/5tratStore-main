"""Bind independently verified MUX app releases to every install surface."""
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class InitShellTests(unittest.TestCase):
    """Execute the shipped literal command with real grep/sed/jq/envsubst.

    Only apk installation and ownership changes are stubbed on the test host;
    all files, chmod, regeneration, backups and JSON transformations are real.
    The chown stub also makes any attempted ownership change auditable.
    """
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name).resolve()
        self.data, self.appdata, self.bin = [self.root / n for n in ('data', 'appdata', 'bin')]
        for path in (self.data, self.appdata, self.bin):
            path.mkdir()
        self.chown_log = self.root / 'chown.log'
        for name, script in {
            'apk': '#!/bin/sh\nexit 0\n',
            'chown': '#!/bin/sh\nprintf "%s\\n" "$@" >> "$TEST_CHOWN_LOG"\n',
        }.items():
            path = self.bin / name
            path.write_text(script)
            path.chmod(0o755)
        for executable in ('jq', 'envsubst'):
            self.assertIsNotNone(shutil.which(executable), executable + ' is a required integration-test dependency')

    def tearDown(self):
        self.tmp.cleanup()

    def run_init(self, app, service):
        recipe = ROOT / app / 'docker-compose.yml'
        command = yaml.safe_load(recipe.read_text())['services'][service]['command']
        self.assertEqual(command[:2], ['/bin/sh', '-ec'])
        # Compose resolves $$ to $; remap only the test bind-mount roots.
        script = command[2].replace('$$', '$').replace('/appdata', str(self.appdata)).replace('/data', str(self.data))
        env = dict(os.environ, PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                   TEST_CHOWN_LOG=str(self.chown_log), JWT_SECRET='',
                   RPC_USER='fixture-user', RPC_PASSWORD='fixture-password', APPS_SUBNET='10.0.0.0/16',
                   PPC_RPC_PORT='9902', PPC_P2P_PORT='9901', PPC_ZMQ_HASHBLOCK_PORT='28336',
                   CPS_WEBSITE_PORT='8080', CPS_STRATUM_PORT='3333', PAYOUT_ADDRESS='fixture-default-payout')
        result = subprocess.run(['/bin/sh', '-ec', script], env=env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('brackets', result.stderr)
        return result

    def ppc_setup(self, raw=None, saved_payout=None):
        shutil.copytree(ROOT / 'willitmod-dev-ppc/data/templates', self.data / 'templates')
        config = self.data / 'pool/config/ckpool.conf'
        config.parent.mkdir(parents=True)
        if raw is not None:
            config.write_bytes(raw)
        if saved_payout is not None:
            state = self.data / 'ui/state'
            state.mkdir(parents=True)
            (state / 'pool_settings.json').write_text(json.dumps({'payoutAddress': saved_payout}))
        return config

    def test_ppc_valid_live_config_is_unchanged_without_spurious_backup(self):
        raw = b'{ "btcd": [{"url":"existing-node","pass":"fixture"}], "btcaddress":"existing-payout", "zmqblock":"existing-zmq", "startdiff":42 }\n'
        config = self.ppc_setup(raw)
        self.run_init('willitmod-dev-ppc', 'init')
        self.run_init('willitmod-dev-ppc', 'init')
        self.assertEqual(config.read_bytes(), raw)
        self.assertEqual(list(config.parent.glob('ckpool.conf.bak.invalid.*')), [])

    def test_ppc_legacy_config_backup_keeps_exact_bytes_and_existing_payout(self):
        raw = b'{"btcd": [], "btcaddress": "existing-payout", "startdiff":42}\n'
        config = self.ppc_setup(raw)
        self.run_init('willitmod-dev-ppc', 'init')
        backups = list(config.parent.glob('ckpool.conf.bak.invalid.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), raw)
        result = json.loads(config.read_text())
        self.assertIsInstance(result['btcd'], list)
        self.assertIn('zmqblock', result)
        self.assertEqual(result['btcaddress'], 'existing-payout')
        self.run_init('willitmod-dev-ppc', 'init')
        self.assertEqual(list(config.parent.glob('ckpool.conf.bak.invalid.*')), backups)

    def test_ppc_invalid_config_retains_backup_and_saved_payout_wins(self):
        raw = b'broken { "btcaddress": "legacy-payout"\n'
        config = self.ppc_setup(raw, saved_payout='saved-payout')
        self.run_init('willitmod-dev-ppc', 'init')
        backups = list(config.parent.glob('ckpool.conf.bak.invalid.*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), raw)
        self.assertEqual(json.loads(config.read_text())['btcaddress'], 'saved-payout')
        self.assertEqual(json.loads((self.data / 'ui/state/pool_settings.json').read_text()), {'payoutAddress': 'saved-payout'})

    def test_ppc_missing_config_is_created_without_backup(self):
        config = self.ppc_setup()
        self.run_init('willitmod-dev-ppc', 'init')
        self.assertEqual(json.loads(config.read_text())['btcaddress'], 'fixture-default-payout')
        self.assertEqual(list(config.parent.glob('ckpool.conf.bak.invalid.*')), [])

    def test_bch2_init_never_changes_existing_core_tree_permissions_or_bytes(self):
        node = self.data / 'node'
        (node / 'blocks/index').mkdir(parents=True)
        (node / 'bitcoinII.conf').write_bytes(b'fixture-core-config\n')
        (node / 'bitcoin.conf').symlink_to('bitcoinII.conf')
        (node / 'blocks/index/000069.log').write_bytes(b'fixture-leveldb-file\n')
        for path in (node, node / 'blocks', node / 'blocks/index'):
            path.chmod(0o700)
        (node / 'bitcoinII.conf').chmod(0o600)
        (node / 'blocks/index/000069.log').chmod(0o600)
        def snapshot():
            result = {}
            for path in [node, *sorted(node.rglob('*'))]:
                st = path.lstat()
                result[str(path.relative_to(node))] = (stat.S_IMODE(st.st_mode), st.st_uid, st.st_gid,
                    os.readlink(path) if path.is_symlink() else path.read_bytes() if path.is_file() else None)
            return result
        before = snapshot()
        self.run_init('willitmod-dev-axebch2', 'init_permissions')
        self.run_init('willitmod-dev-axebch2', 'init_permissions')
        self.assertEqual(snapshot(), before)
        for argument in self.chown_log.read_text().splitlines():
            self.assertFalse(argument == str(node) or argument.startswith(str(node) + '/'), 'Core ownership must remain with its own image')
        self.assertTrue((self.data / 'ui/state').is_dir())
        self.assertTrue((self.data / 'pool/config').is_dir())


class MuxPackageTests(unittest.TestCase):
    def test_verified_images_and_versions_reach_every_install_surface(self):
        release = json.loads((ROOT / "MAIN-NODE-ROLLUP-2026-09-28.json").read_text())
        self.assertEqual(release["schemaVersion"], 1)
        expected = {"willitmod-dev-" + name for name in
                    ("btc", "bch", "bc2", "axebch2", "dgb", "xec", "ppc", "powpow", "fracattack")}
        expected.remove("willitmod-dev-btc"); expected.add("willitmod-btc")
        self.assertEqual(set(release["apps"]), expected)
        for name, record in release["apps"].items():
            with self.subTest(app=name):
                app = ROOT / name
                self.assertRegex(record["sourceRevision"], r"^[0-9a-f]{40}$")
                self.assertEqual(record["platforms"], ["linux/amd64", "linux/arm64"])
                version = record["version"].removesuffix("-dev")
                self.assertRegex(record["imageRef"], r":" + re.escape(version) + r"-mux\." +
                                 record["sourceRevision"][:12] + r"@sha256:[0-9a-f]{64}$")
                for filename in ("umbrel-app.yml", "global-app.yml"):
                    path = app / filename
                    if path.exists():
                        manifest = yaml.safe_load(path.read_text())
                        self.assertEqual(manifest["id"], name)
                        self.assertEqual(manifest["version"], record["version"])
                        self.assertIn("Block alerts in this browser", manifest["releaseNotes"])
                        self.assertIn("browser-only Close", manifest["releaseNotes"])
                        self.assertIn("OS and MUX", manifest["releaseNotes"])
                for filename in ("docker-compose.yml", "docker-compose.yml.template"):
                    path = app / filename
                    if not path.exists():
                        continue
                    service = yaml.safe_load(path.read_text())["services"]["app"]
                    self.assertEqual(service["image"], record["imageRef"])
                    environment = service["environment"]
                    self.assertEqual(environment["MUX_IDENTITY_URL"],
                                     "http://172.17.0.1:21222/api/integrations/workers")
                    if "APP_VERSION" in environment:
                        self.assertEqual(environment["APP_VERSION"], record["version"])

    def test_powpow_app_and_pool_bind_to_the_same_verified_source(self):
        release = json.loads((ROOT / "MAIN-NODE-ROLLUP-2026-09-28.json").read_text())
        record = release["apps"]["willitmod-dev-powpow"]
        compose = yaml.safe_load((ROOT / "willitmod-dev-powpow/docker-compose.yml").read_text())
        self.assertEqual(compose["services"]["pool"]["image"], record["poolImageRef"])
        self.assertEqual(record["poolSourceRevision"], record["sourceRevision"])
        version = record["version"].removesuffix("-dev")
        self.assertRegex(record["poolImageRef"], r":" + re.escape(version) + r"-mux\." +
                         record["sourceRevision"][:12] + r"@sha256:[0-9a-f]{64}$")

    def test_fractal_update_retains_the_consensus_fixed_core(self):
        compose = yaml.safe_load((ROOT / "willitmod-dev-fracattack/docker-compose.yml").read_text())
        self.assertEqual(compose["services"]["fractald"]["image"],
                         "ghcr.io/willitmod/fracattack-fractald:0.4.0")
        self.assertEqual(compose["services"]["app"]["environment"]["FRACTAL_IMAGE"],
                         "ghcr.io/willitmod/fracattack-fractald:0.4.0")


if __name__ == "__main__":
    unittest.main()
