"""Packaging contracts for the memory supervisor and offline startup."""
import subprocess
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "willitmod-dev-dgb"


class AxeDgbPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
        cls.services = cls.compose["services"]
        cls.init = cls.services["init"]["command"][-1]

    def test_persistent_launcher_is_refreshed_with_exact_shipped_content(self):
        start = self.init.index("<<'DGB_ENTRYPOINT'\n") + len("<<'DGB_ENTRYPOINT'\n")
        end = self.init.index("\nDGB_ENTRYPOINT", start)
        embedded = self.init[start:end].replace("$$", "$") + "\n"
        self.assertEqual(embedded, (ROOT / "data/templates/dgb-entrypoint.sh").read_text())
        subprocess.run(["sh", "-n"], input=embedded, text=True, check=True)
        self.assertIn("exec python3 /usr/local/lib/axedgb/core_supervisor.py", embedded)
        self.assertNotIn("rm -f /data/.reindex-chainstate", embedded)

    def test_install_needs_no_package_mirror_and_reports_failures(self):
        self.assertNotIn("apk add", self.init)
        self.assertIn("trap init_failed EXIT", self.init)
        self.assertIn("init_status ready", self.init)
        self.assertIn("--single-transaction", self.init)
        self.assertIn("axedgb-init:", self.services["init"]["image"])

    def test_all_changed_images_match_release_version(self):
        version = yaml.safe_load((ROOT / "umbrel-app.yml").read_text())["version"]
        for service in ["app", "init", "dgbd"]:
            self.assertTrue(self.services[service]["image"].endswith(":" + version), service)
        self.assertEqual(self.services["app"]["environment"]["DGB_IMAGE"], self.services["dgbd"]["image"])
        self.assertEqual(self.services["dgbd"]["stop_grace_period"], "15m30s")
        self.assertNotIn("dgbd", self.services["app"]["depends_on"])


if __name__ == "__main__":
    unittest.main()
