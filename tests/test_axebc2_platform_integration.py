import ast
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "willitmod-dev-bc2/data/init/init.sh"
TEMPLATES = ROOT / "willitmod-dev-bc2/data/templates"


def platform_root() -> Path:
    configured = os.environ.get("FIVETRATUMOS_ROOT")
    if configured:
        return Path(configured)
    return ROOT.parent / "5tratumos-v0711-release"


def load_fixture_module():
    source = ROOT / "tests/fixtures/5tratumos_contract_4f979cb.py"
    spec = importlib.util.spec_from_file_location("pinned_5tratumos_contract", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_platform_store_mapper(platform: Path):
    source_path = platform / "daemon/5tratumosd.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    required_assignments = {"_STORE_ID_PREFIXES", "_CANONICAL_STORE_APP_IDS"}
    selected = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in required_assignments
            for target in node.targets
        ):
            selected.append(node)
        if isinstance(node, ast.FunctionDef) and node.name == "map_store_id_to_app_id":
            selected.append(node)
    namespace = {"re": re}
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(source_path), "exec"), namespace)
    return namespace["map_store_id_to_app_id"]


def load_policy_module(platform: Path):
    source = platform / "daemon/app_rollback_policy.py"
    spec = importlib.util.spec_from_file_location("platform_app_rollback_policy", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class AxeBC2PlatformIntegrationTests(unittest.TestCase):
    def test_real_dev_store_id_maps_to_axebc2_and_policy_is_accepted(self):
        platform = platform_root()
        if platform.joinpath("daemon/5tratumosd.py").is_file():
            mapper = load_platform_store_mapper(platform)
            policy = load_policy_module(platform)
        else:
            policy = load_fixture_module()
            mapper = policy.map_store_id_to_app_id
        canonical_id = mapper("willitmod-dev-bc2", "dev")
        self.assertEqual(canonical_id, "axebc2")
        self.assertEqual(
            Path("/var/lib/5tratumos/apps") / canonical_id,
            Path("/var/lib/5tratumos/apps/axebc2"),
        )

        temp = Path(tempfile.mkdtemp(prefix="axebc2-platform-"))
        try:
            app_root = temp / "var/lib/5tratumos/apps" / canonical_id
            data = app_root / "data"
            data.mkdir(parents=True)
            build = temp / "etc/5tratumos/build.json"
            build.parent.mkdir(parents=True)
            build.write_text(json.dumps({"tag": "0.7.11"}), encoding="utf-8")
            env = os.environ.copy()
            env.update(
                {
                    "AXEBC2_DATA_DIR": str(data),
                    "AXEBC2_APPDATA_DIR": str(app_root),
                    "AXEBC2_BUILD_FILE": str(build),
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
            subprocess.run(["sh", str(INIT)], env=env, check=True, capture_output=True)
            policy_path = data / ".5tratumos-rollback-policy.json"
            accepted = policy.check_rollback_policy(policy_path, canonical_id, "0.1.10-dev")
            self.assertTrue(accepted["enforced"])
            with self.assertRaises(policy.RollbackPolicyError):
                policy.check_rollback_policy(policy_path, canonical_id, "0.1.9-dev")
        finally:
            shutil.rmtree(temp)


if __name__ == "__main__":
    unittest.main()
