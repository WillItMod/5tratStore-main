import json
import os
from pathlib import Path
import shutil
import stat
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

    def run_init(self, tag="0.7.12", expect=0, jwt_secret=None, extra_env=None):
        self.build.write_text(json.dumps({"tag": tag}), encoding="utf-8")
        env = os.environ.copy()
        env.pop("JWT_SECRET", None)
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
        if jwt_secret is not None:
            env["JWT_SECRET"] = jwt_secret
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            ["sh", str(INIT)], env=env, text=True, capture_output=True, check=False
        )
        self.assertEqual(result.returncode, expect, result.stderr)
        return result

    def test_fresh_env_persists_jwt_secret_with_private_mode(self):
        self.run_init(jwt_secret="fresh-secret")
        envfile = self.appdata / ".env"
        self.assertEqual(envfile.read_text(encoding="utf-8"), "JWT_SECRET=fresh-secret\n")
        self.assertEqual(stat.S_IMODE(envfile.stat().st_mode), 0o600)

    def test_existing_env_replaces_all_jwts_and_preserves_unrelated_entries(self):
        envfile = self.appdata / ".env"
        envfile.write_text(
            "KEEP_FIRST=alpha\nJWT_SECRET=old-one\nKEEP_SECOND=beta=value\nJWT_SECRET=old-two\n",
            encoding="utf-8",
        )
        envfile.chmod(0o644)
        self.run_init(jwt_secret="replacement-secret")
        lines = envfile.read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines.count("JWT_SECRET=replacement-secret"), 1)
        self.assertFalse(any(line in {"JWT_SECRET=old-one", "JWT_SECRET=old-two"} for line in lines))
        self.assertIn("KEEP_FIRST=alpha", lines)
        self.assertIn("KEEP_SECOND=beta=value", lines)
        self.assertEqual(stat.S_IMODE(envfile.stat().st_mode), 0o600)

    def test_policy_and_reindex_requirement_exist_without_rpc(self):
        (self.data / "node/blocks").mkdir(parents=True)
        self.run_init()
        policy = json.loads(
            (self.data / ".5tratumos-rollback-policy.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["minimum_base_version"], "0.1.10")
        self.assertEqual(policy["minimum_5tratumos_version"], "0.7.12")
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

    def test_current_ckpool_config_still_repairs_sharelog_ownership(self):
        pool = self.data / "pool"
        sharelogs = pool / "www"
        sharelogs.mkdir(parents=True)
        config_dir = pool / "config"
        config_dir.mkdir()
        config = config_dir / "ckpool.conf"
        original = json.dumps(
            {
                "btcaddress": "1BoatSLRHtKNngkdXEeobR76b53LETtpyT",
                "btcd": [{"url": "btc2d:8337"}],
                "zmqblock": "tcp://btc2d:28336",
            },
            sort_keys=True,
        ) + "\n"
        config.write_text(original, encoding="utf-8")

        fake_bin = self.tmp / "fake-bin"
        fake_bin.mkdir()
        chown_log = self.tmp / "chown.log"
        chown_state = self.tmp / "sharelog-ownership-repaired"
        fake_chown = fake_bin / "chown"
        fake_chown.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$AXEBC2_TEST_CHOWN_LOG"\n'
            'case "$*" in *"$AXEBC2_TEST_SHARELOG_ROOT"*) '
            ': > "$AXEBC2_TEST_CHOWN_STATE" ;; esac\n',
            encoding="utf-8",
        )
        fake_chown.chmod(0o755)
        fake_stat = fake_bin / "stat"
        fake_stat.write_text(
            "#!/bin/sh\n"
            'if [ -e "$AXEBC2_TEST_CHOWN_STATE" ]; then '
            "printf '1000:1000\\n'; else printf '0:0\\n'; fi\n",
            encoding="utf-8",
        )
        fake_stat.chmod(0o755)
        extra_env = {
            "AXEBC2_TEST_SKIP_CHOWN": "false",
            "AXEBC2_TEST_CHOWN_LOG": str(chown_log),
            "AXEBC2_TEST_CHOWN_STATE": str(chown_state),
            "AXEBC2_TEST_SHARELOG_ROOT": str(sharelogs),
            "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
        }

        self.run_init(extra_env=extra_env)
        self.run_init(extra_env=extra_env)

        repair = f"-R 1000:1000 {sharelogs}"
        self.assertEqual(chown_log.read_text(encoding="utf-8").splitlines().count(repair), 1)
        self.assertEqual(config.read_text(encoding="utf-8"), original)

    def test_fresh_install_repairs_mutable_pool_config_ownership(self):
        fake_bin = self.tmp / "fake-bin"
        fake_bin.mkdir()
        chown_log = self.tmp / "chown.log"
        fake_chown = fake_bin / "chown"
        fake_chown.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$*" >> "$AXEBC2_TEST_CHOWN_LOG"\n',
            encoding="utf-8",
        )
        fake_chown.chmod(0o755)
        fake_stat = fake_bin / "stat"
        fake_stat.write_text("#!/bin/sh\nprintf '1000:1000\\n'\n", encoding="utf-8")
        fake_stat.chmod(0o755)

        self.run_init(
            extra_env={
                "AXEBC2_TEST_SKIP_CHOWN": "false",
                "AXEBC2_TEST_CHOWN_LOG": str(chown_log),
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
            }
        )

        config_dir = self.data / "pool/config"
        self.assertTrue((config_dir / "ckpool.conf").is_file())
        self.assertIn(
            f"-R 1000:1000 {config_dir}",
            chown_log.read_text(encoding="utf-8").splitlines(),
        )
        # Atomic payout saves need directory-level create and replace access.
        replacement = config_dir / ".ckpool.conf.atomic-test"
        replacement.write_text("replacement\n", encoding="utf-8")
        replacement.replace(config_dir / "ckpool.conf")
        self.assertEqual(
            (config_dir / "ckpool.conf").read_text(encoding="utf-8"),
            "replacement\n",
        )

    def test_saved_payout_and_persistent_settings_survive_main_upgrade(self):
        pool_config = self.data / "pool/config"
        pool_config.mkdir(parents=True)
        (pool_config / "ckpool.conf").write_text(
            json.dumps({"btcaddress": "LegacySavedPayout"}), encoding="utf-8"
        )
        settings_dir = self.data / "ui/state"
        settings_dir.mkdir(parents=True)
        settings = settings_dir / "pool_settings.json"
        original_settings = json.dumps(
            {"payoutAddress": "CurrentSavedPayout", "unrelated": "preserve-me"},
            sort_keys=True,
        )
        settings.write_text(original_settings, encoding="utf-8")

        self.run_init()

        regenerated = json.loads((pool_config / "ckpool.conf").read_text(encoding="utf-8"))
        self.assertEqual(regenerated["btcaddress"], "CurrentSavedPayout")
        self.assertEqual(settings.read_text(encoding="utf-8"), original_settings)
        backups = list(pool_config.glob("ckpool.conf.bak.*"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text())["btcaddress"], "LegacySavedPayout")

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
        self.build.write_text(json.dumps({"tag": "0.7.12"}), encoding="utf-8")
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
