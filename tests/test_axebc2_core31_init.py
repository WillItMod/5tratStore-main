import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "willitmod-dev-bc2/data/init/init.sh"
TEMPLATES = ROOT / "willitmod-dev-bc2/data/templates"


class AxeBC2InitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="axebc2-init-"))
        self.data = self.tmp / "data"
        self.appdata = self.tmp / "appdata"
        self.data.mkdir()
        self.appdata.mkdir()
        self.build = self.tmp / "build.json"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_init(self, tag="0.7.11", expect=0):
        self.build.write_text(json.dumps({"tag": tag}), encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "AXEBC2_DATA_DIR": str(self.data),
                "AXEBC2_APPDATA_DIR": str(self.appdata),
                "AXEBC2_BUILD_FILE": str(self.build),
                "AXEBC2_TEMPLATES_DIR": str(TEMPLATES),
                "AXEBC2_TEST_SKIP_CHOWN": "true",
                "APPS_SUBNET": "10.0.0.0/16",
                "RPC_USER": "btc2",
                "RPC_PASSWORD": "test-only",
                "BTC2_RPC_PORT": "8337",
                "BTC2_P2P_PORT": "8338",
                "BTC2_ZMQ_HASHBLOCK_PORT": "28336",
                "PAYOUT_ADDRESS": "CHANGEME_BTC2_PAYOUT_ADDRESS",
            }
        )
        result = subprocess.run(
            ["sh", str(INIT)], env=env, text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def test_policy_and_reindex_requirement_exist_without_rpc(self):
        (self.data / "node/blocks").mkdir(parents=True)
        self.run_init()
        policy = json.loads(
            (self.data / ".5tratumos-rollback-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["minimum_base_version"], "0.1.10")
        self.assertEqual(policy["minimum_5tratumos_version"], "0.7.11")
        marker = json.loads(
            (self.data / "node/.core31-full-reindex-required.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(marker["migration"], "bitcoinii-shockwave-core31-full-reindex")
        self.assertEqual(marker["minimum_core_major"], 31)
        self.assertEqual(marker["activation_height"], 57750)

    def test_old_os_fails_before_data_mutation(self):
        sentinel = self.data / "unchanged"
        sentinel.write_text("original", encoding="utf-8")
        self.run_init(tag="0.7.10", expect=78)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "original")
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["unchanged"])
        self.assertEqual(list(self.appdata.iterdir()), [])

    def test_malformed_policy_fails_closed(self):
        policy = self.data / ".5tratumos-rollback-policy.json"
        policy.write_text('{"schema":1,"app_id":"wrong"}', encoding="utf-8")
        self.run_init(expect=78)
        self.assertEqual(policy.read_text(encoding="utf-8"), '{"schema":1,"app_id":"wrong"}')
        self.assertFalse((self.data / "node").exists())

    def test_stricter_floors_are_preserved(self):
        policy = self.data / ".5tratumos-rollback-policy.json"
        policy.write_text(
            json.dumps(
                {
                    "schema": 1,
                    "app_id": "axebc2",
                    "minimum_base_version": "0.2.3",
                    "minimum_5tratumos_version": "0.8.1",
                    "reason": "future stricter policy",
                    "recorded_at_height": 60000,
                }
            ),
            encoding="utf-8",
        )
        self.run_init()
        updated = json.loads(policy.read_text(encoding="utf-8"))
        self.assertEqual(updated["minimum_base_version"], "0.2.3")
        self.assertEqual(updated["minimum_5tratumos_version"], "0.8.1")
        self.assertEqual(updated["recorded_at_height"], 60000)

    def test_valid_completion_prevents_required_marker(self):
        node = self.data / "node"
        (node / "chainstate").mkdir(parents=True)
        (node / ".core31-full-reindex-complete.json").write_text(
            json.dumps(
                {
                    "schema": 1,
                    "migration": "bitcoinii-shockwave-core31-full-reindex",
                    "minimum_core_major": 31,
                    "activation_height": 57750,
                    "completed_at": "2026-09-02T00:00:00Z",
                    "validated_height": 57752,
                    "best_block_hash": "0" * 64,
                    "core_version": 310100,
                    "checkpoint_height": 57752,
                    "checkpoint_hash": "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576",
                    "validated_chainwork": "0000000000000000000000000000000000000000000000959028194ff1139272",
                }
            ),
            encoding="utf-8",
        )
        self.run_init()
        self.assertFalse((node / ".core31-full-reindex-required.json").exists())

    def test_existing_upnp_configuration_is_disabled(self):
        node = self.data / "node"
        node.mkdir()
        config = node / "bitcoinII.conf"
        config.write_text("server=1\nupnp=1\nnatpmp=1\n", encoding="utf-8")
        self.run_init()
        updated = config.read_text(encoding="utf-8")
        self.assertNotIn("upnp=", updated)
        self.assertEqual(updated.count("natpmp=0"), 1)

    def test_missing_or_malformed_build_metadata_fails_closed(self):
        self.build.write_text("not-json", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "AXEBC2_DATA_DIR": str(self.data),
                "AXEBC2_APPDATA_DIR": str(self.appdata),
                "AXEBC2_BUILD_FILE": str(self.build),
                "AXEBC2_TEST_SKIP_CHOWN": "true",
            }
        )
        result = subprocess.run(["sh", str(INIT)], env=env, capture_output=True)
        self.assertEqual(result.returncode, 78)
        self.assertEqual(list(self.data.iterdir()), [])

    def test_dependency_install_failure_precedes_persistent_mutation(self):
        tool_dir = self.tmp / "broken-tools"
        tool_dir.mkdir()
        apk = tool_dir / "apk"
        apk.write_text("#!/bin/sh\nexit 42\n", encoding="utf-8")
        apk.chmod(0o755)
        self.build.write_text(json.dumps({"tag": "0.7.11"}), encoding="utf-8")
        sentinel = self.data / "unchanged"
        sentinel.write_text("original", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "PATH": str(tool_dir),
                "AXEBC2_DATA_DIR": str(self.data),
                "AXEBC2_APPDATA_DIR": str(self.appdata),
                "AXEBC2_BUILD_FILE": str(self.build),
            }
        )
        result = subprocess.run(["/bin/sh", str(INIT)], env=env, capture_output=True)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(sentinel.read_text(encoding="utf-8"), "original")
        self.assertEqual(sorted(p.name for p in self.data.iterdir()), ["unchanged"])
        self.assertEqual(list(self.appdata.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
