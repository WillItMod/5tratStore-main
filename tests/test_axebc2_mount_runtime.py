"""Run on the Docker host; temporary files must be visible to its daemon.

AXEBC2_TEST_DOCKER_RUNTIME=1 python3 -m unittest discover -s tests -p 'test_axebc2_mount_runtime.py' -v
The pinned Alpine image must already be present; this test never pulls images.
"""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "willitmod-dev-bc2"


@unittest.skipUnless(os.environ.get("AXEBC2_TEST_DOCKER_RUNTIME") == "1",
                     "set AXEBC2_TEST_DOCKER_RUNTIME=1 on a disposable Docker test host")
class StrictMountRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axebc2-mount-contract-")
        self.root = Path(self.temp.name)
        self.project = "axebc2-mount-" + uuid.uuid4().hex[:12]
        self.file = self.root / "build.json"
        self.file.write_text('{"tag":"0.7.12"}\n')
        self.directory = self.root / "pool-config"
        self.directory.mkdir()
        (self.directory / "sentinel").write_text("original pool data\n")
        recipe = yaml.safe_load((APP / "docker-compose.yml").read_text())
        # Older Compose versions do not accept `run --pull never`. Requiring
        # the exact image locally before run gives the same no-pull guarantee.
        subprocess.run(["docker", "image", "inspect", recipe["services"]["init"]["image"]],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, check=True)
        # Use the recipe's actual config grant and read-only local-volume mount.
        grant = next(c for c in recipe["services"]["init"]["configs"]
                     if c["target"] == "/etc/5tratumos/build.json")
        volume = next(v for v in recipe["services"]["ckpool"]["volumes"] if ":/config:" in v)
        volume_name = volume.split(":", 1)[0]
        volume_definition = copy.deepcopy(recipe["volumes"][volume_name])
        volume_definition["driver_opts"]["device"] = str(self.directory)
        config_definition = copy.deepcopy(recipe["configs"][grant["source"]])
        config_definition["file"] = str(self.file)
        self.compose = {
            "services": {"probe": {
                "image": recipe["services"]["init"]["image"],
                "network_mode": "none",
                "volumes": [volume], "configs": [grant],
                "command": ["/bin/sh", "-ec", "cat /etc/5tratumos/build.json /config/sentinel"],
            }},
            "volumes": {volume_name: volume_definition},
            "configs": {grant["source"]: config_definition},
        }
        self.path = self.root / "compose.yml"
        self.path.write_text(yaml.safe_dump(self.compose))

    def tearDown(self):
        try:
            subprocess.run(self.command("down", "--volumes", "--remove-orphans"),
                           capture_output=True, timeout=30, check=False)
        finally:
            self.temp.cleanup()

    def command(self, *arguments):
        return ["docker", "compose", "-p", self.project, "-f", str(self.path), *arguments]

    def run_probe(self):
        self.path.write_text(yaml.safe_dump(self.compose))
        return subprocess.run(self.command("run", "--rm", "--no-deps", "probe"),
                              text=True, capture_output=True, timeout=60)

    def test_readonly_file_and_directory_reject_writes_and_preserve_contents(self):
        self.compose["services"]["probe"]["command"] = ["/bin/sh", "-ec", """
            cat /etc/5tratumos/build.json /config/sentinel
            if (printf changed > /etc/5tratumos/build.json) 2>/dev/null; then exit 91; fi
            if (printf changed > /config/sentinel) 2>/dev/null; then exit 92; fi
            if (printf created > /config/new-file) 2>/dev/null; then exit 93; fi
        """]
        result = self.run_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("original pool data", result.stdout)
        self.assertEqual(json.loads(self.file.read_text()), {"tag": "0.7.12"})
        self.assertEqual((self.directory / "sentinel").read_text(), "original pool data\n")
        self.assertFalse((self.directory / "new-file").exists())

    def test_missing_config_file_fails_without_creating_host_path(self):
        self.file.unlink()
        result = self.run_probe()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.file), result.stderr)
        self.assertRegex(result.stderr.lower(), "does not exist|no such file|not found")
        self.assertFalse(self.file.exists())
        self.assertEqual((self.directory / "sentinel").read_text(), "original pool data\n")

    def test_missing_directory_fails_without_creating_host_path(self):
        (self.directory / "sentinel").unlink()
        self.directory.rmdir()
        result = self.run_probe()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(str(self.directory), result.stderr)
        self.assertRegex(result.stderr.lower(), "does not exist|no such file|not found")
        self.assertFalse(self.directory.exists())
        self.assertEqual(json.loads(self.file.read_text()), {"tag": "0.7.12"})


if __name__ == "__main__":
    unittest.main()
