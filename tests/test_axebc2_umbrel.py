import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "willitmod-dev-bc2"


class UmbrelPackagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axebc2-umbrel-")
        self.root = Path(self.temp.name)
        self.data = self.root / "data"
        shutil.copytree(APP / "data", self.data)
        shutil.copytree(APP / "hooks", self.root / "hooks")
        self.env = os.environ.copy()
        self.env.update({
            "AXEBC2_PLATFORM": "umbrel", "AXEBC2_DATA_DIR": str(self.data),
            "AXEBC2_APPDATA_DIR": str(self.root),
            "AXEBC2_TEMPLATES_DIR": str(self.data / "templates"),
            "AXEBC2_TEST_SKIP_CHOWN": "true", "APP_DATA_DIR": str(self.root),
            "APP_PASSWORD": "test-only", "JWT_SECRET": "test-only",
            "NETWORK_IP": "10.21.0.0", "APPS_SUBNET": "10.21.0.0/16",
            "RPC_USER": "btc2", "RPC_PASSWORD": "test-only",
            "BTC2_RPC_PORT": "8337", "BTC2_P2P_PORT": "8338",
            "BTC2_ZMQ_HASHBLOCK_PORT": "28336",
            "PAYOUT_ADDRESS": "CHANGEME_BTC2_PAYOUT_ADDRESS",
            "AXEBC2_BUILD_FILE": str(self.root / "does-not-exist.json"),
        })

    def tearDown(self):
        self.temp.cleanup()

    def run_init(self, expected=0):
        result = subprocess.run(["sh", str(self.root / "hooks/umbrel-init")],
                                env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, result.stderr)
        return result

    def test_generated_artifacts_are_current(self):
        subprocess.run([sys.executable, str(ROOT / "scripts/build-axebc2-umbrel.py"), "--check"], check=True)

    def test_accepted_5tratumos_recipe_remains_byte_identical(self):
        self.assertEqual(hashlib.sha256((APP / "docker-compose.yml").read_bytes()).hexdigest(),
                         "367b7ff11bf3021b56feaa239c65aedd9e9cf4fbaeedcb3172d4cd6adbbdcd2e")

    def test_umbrel_envsubst_and_compose_keep_pins_and_auth_without_os_bind(self):
        rendered = subprocess.check_output(["envsubst"], input=(APP / "docker-compose.yml.template").read_text(),
                                           env=self.env, text=True)
        self.assertNotIn("/etc/5tratumos", rendered)
        config = yaml.safe_load(rendered)
        config["services"]["app_proxy"]["image"] = "getumbrel/app-proxy:1.7.0"
        path = self.root / "docker-compose.yml"
        path.write_text(yaml.safe_dump(config))
        result = subprocess.run(["docker", "compose", "-f", str(path), "config", "--format", "json"],
                                capture_output=True, text=True, env=self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        services = json.loads(result.stdout)["services"]
        accepted = yaml.safe_load((APP / "docker-compose.yml").read_text())["services"]
        for service in ("app", "btc2d", "ckpool", "init"):
            self.assertEqual(services[service]["image"], accepted[service]["image"])
        self.assertEqual(services["app_proxy"]["environment"]["JWT_SECRET"], "test-only")
        self.assertEqual(services["app_proxy"]["environment"]["APP_HOST"], "axebc2-app")
        self.assertEqual(services["btc2d"]["depends_on"]["init"]["condition"], "service_completed_successfully")
        self.assertEqual(services["init"]["environment"]["AXEBC2_PLATFORM"], "umbrel")
        for service in services.values():
            for volume in service.get("volumes", []):
                if volume["type"] == "bind":
                    self.assertFalse(volume.get("bind", {}).get("create_host_path", False))
                    self.assertTrue(Path(volume["source"]).exists(), volume)

    def test_fresh_umbrel_init_succeeds_without_5tratumos_metadata(self):
        self.run_init()
        policy = json.loads((self.data / ".5tratumos-rollback-policy.json").read_text())
        self.assertEqual(policy["minimum_base_version"], "0.1.10")
        self.assertEqual(policy["minimum_5tratumos_version"], "0.7.12")
        self.assertTrue((self.data / "node/bitcoinII.conf").is_file())

    def test_missing_umbrel_recipe_identity_fails_before_writes(self):
        self.env.pop("AXEBC2_PLATFORM")
        self.run_init(78)
        self.assertFalse((self.data / ".5tratumos-rollback-policy.json").exists())
        self.assertFalse((self.root / "settings.yml").exists())

    def test_existing_chain_requires_reindex_and_keeps_data(self):
        blocks = self.data / "node/blocks"
        blocks.mkdir()
        sentinel = blocks / "blk00000.dat"
        sentinel.write_bytes(b"preserved chain")
        self.run_init()
        marker = json.loads((self.data / "node/.core31-full-reindex-required.json").read_text())
        self.assertEqual(marker["minimum_core_major"], 31)
        self.assertEqual(marker["activation_height"], 57750)
        self.assertEqual(sentinel.read_bytes(), b"preserved chain")

    def test_malformed_migration_marker_still_rejects_startup(self):
        marker = self.data / "node/.core31-full-reindex-complete.json"
        marker.write_text('{"migration":"not-accepted"}')
        self.run_init(78)
        self.assertEqual(marker.read_text(), '{"migration":"not-accepted"}')
        self.assertFalse((self.data / "node/bitcoinII.conf").exists())

    def test_valid_completion_survives_restart_without_reindex(self):
        marker = self.data / "node/.core31-full-reindex-complete.json"
        complete = {
            "schema": 1, "migration": "bitcoinii-shockwave-core31-full-reindex",
            "minimum_core_major": 31, "activation_height": 57750,
            "completed_at": "2026-09-04T17:22:22Z", "validated_height": 58444,
            "best_block_hash": "0" * 64, "core_version": 310100,
            "checkpoint_height": 57752,
            "checkpoint_hash": "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576",
            "validated_chainwork": "0000000000000000000000000000000000000000000000959028194ff1139272",
        }
        marker.write_text(json.dumps(complete))
        (self.data / "node/chainstate").mkdir()
        self.run_init()
        self.run_init()
        self.assertEqual(json.loads(marker.read_text()), complete)
        self.assertFalse((self.data / "node/.core31-full-reindex-required.json").exists())

    def test_preserved_data_initializer_is_not_executed_on_upgrade(self):
        (self.data / "init/init.sh").write_text("#!/bin/sh\nexit 99\n")
        self.run_init()
        config = self.data / "pool/config/ckpool.conf"
        saved = json.loads(config.read_text())
        saved["btcaddress"] = "retained-test-payout"
        config.write_text(json.dumps(saved))
        self.run_init()
        self.assertEqual(json.loads(config.read_text())["btcaddress"], "retained-test-payout")


if __name__ == "__main__":
    unittest.main()
