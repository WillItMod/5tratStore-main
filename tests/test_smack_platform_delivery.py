"""Smack platform delivery; external source/Compose checks are explicit opt-ins.

SMACK_PLATFORM_NATIVE_SOURCE may name an exact OS source checkout. Set
SMACK_PLATFORM_COMPOSE_COMMAND to a real Compose command to check interpolation.
Neither optional check starts containers or executes an application backend.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "willitmod-dev-5tratsmack"
EXPRESSION = "${APP_5TRATSMACK_PLATFORM:-5TRATUMOS}"
EXPORTS = (b'#!/usr/bin/env bash\n'
           b'# Umbrel sources this hook before Compose; native 5tratumOS uses the default.\n'
           b'export APP_5TRATSMACK_PLATFORM="UMBREL"\n')
FRAGMENTS = ["9dc8fd762892a0a4d4492de4348646df87584469eb079a3d9a54d53a7d594578",
             "0cf6ed5c7955a343ae7c3028c0e5a5b2872f41e8e011f41eabcf3df76f4ccd68"]
CLI_HASHES = {"caa747717a3a5ba12dbc231ce79987179b3c37b8ca31d8f588baa1c30c715cfc",
              "aca43e31bfcc5b13b92088c74483410ed9ec530d0fd22df34ad147277327d37b"}


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def source_model():
    return yaml.safe_load((PACKAGE / "docker-compose.yml").read_text())


class SmackPlatformDeliveryTests(unittest.TestCase):
    def test_platform_is_deferred_to_one_app_specific_compose_variable(self):
        text = (PACKAGE / "docker-compose.yml").read_text()
        self.assertEqual(source_model()["services"]["app"]["environment"]["APP_PLATFORM"], EXPRESSION)
        self.assertEqual(text.count("APP_5TRATSMACK_PLATFORM"), 1)
        self.assertFalse((PACKAGE / "docker-compose.yml.template").exists())

    def test_export_hook_is_exact_and_contains_no_discovery_or_lifecycle(self):
        path = PACKAGE / "exports.sh"
        self.assertEqual(path.read_bytes(), EXPORTS)
        self.assertEqual(path.stat().st_mode & 0o777, 0o755)

    def check_shell_export(self, strict):
        prefix = "set -euo pipefail" if strict else "set +e; set +u; set +o pipefail"
        script = prefix + '''
before_flags=$-
before_pipefail=$(set -o | awk '$1 == "pipefail" {print $2}')
. "$1"
[[ "$before_flags" == "$-" ]] || exit 91
[[ "$before_pipefail" == "$(set -o | awk '$1 == "pipefail" {print $2}')" ]] || exit 92
printf '%s\\n' "$APP_5TRATSMACK_PLATFORM"
bash -c 'printf "%s\\n" "$APP_5TRATSMACK_PLATFORM"'
'''
        for value in (None, "", "5TRATUMOS", "stale-parent-value"):
            env = os.environ.copy()
            env.pop("APP_5TRATSMACK_PLATFORM", None)
            if value is not None:
                env["APP_5TRATSMACK_PLATFORM"] = value
            p = subprocess.run(["bash", "-c", script, "smack-platform-export-test",
                                str(PACKAGE / "exports.sh")], env=env, text=True,
                               capture_output=True, timeout=10)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.splitlines(), ["UMBREL", "UMBREL"])

    def test_umbrel_export_overrides_stale_inheritance_under_strict_caller(self):
        self.check_shell_export(True)

    def test_umbrel_export_preserves_non_strict_caller_options(self):
        self.check_shell_export(False)

    def test_shell_healthcheck_expansions_are_still_escaped_for_compose(self):
        command = source_model()["services"]["node-a"]["healthcheck"]["test"][1]
        self.assertIn("$$(fivetrat-cli", command)
        self.assertIn('"$$FIVETRAT_RPC_PASSWORD"', command)
        self.assertIn('"$$FIVETRAT_CANONICAL_CHECKPOINT_HEIGHT"', command)
        self.assertIn('"$$FIVETRAT_CANONICAL_CHECKPOINT_HASH"', command)
        self.assertNotRegex(command, r"(?<!\$)\$\(")
        self.assertNotRegex(command, r"(?<!\$)\$FIVETRAT_")

    @unittest.skipUnless(os.environ.get("SMACK_PLATFORM_NATIVE_SOURCE"),
                         "opt-in exact native CLI source not provided")
    def test_actual_native_install_and_update_generators_keep_the_expression(self):
        root = Path(os.environ["SMACK_PLATFORM_NATIVE_SOURCE"])
        cli = (root / "bin/5tratumos").read_bytes()
        self.assertIn(digest(cli), CLI_HASHES)
        self.assertNotIn("exports.sh", cli.decode())
        self.assertNotIn("docker-compose.yml.template", cli.decode())
        blocks = [s for s in re.findall(r"python3 - <<'PY'[^\n]*\n(.*?)\nPY\n", cli.decode(), re.S)
                  if 'compose_path = root / store_dir / "docker-compose.yml"' in s]
        self.assertEqual([digest(s.encode()) for s in blocks], FRAGMENTS)
        helper = root / "daemon/docker_socket_access.py"
        self.assertEqual(digest(helper.read_bytes()),
                         "e08271cf0c535aa638d83415b69858bc14c6b583f8bbad5a0f68777658985c87")
        current = source_model()
        with tempfile.TemporaryDirectory(prefix="smack-native-platform-") as temp:
            t = Path(temp)
            for index, block in enumerate(blocks):
                outputs = []
                for label in ("before", "candidate"):
                    package = t / str(index) / label / "store" / PACKAGE.name
                    dest = package.parent.parent / "render"
                    package.mkdir(parents=True); dest.mkdir()
                    value = copy.deepcopy(current)
                    if label == "before":
                        value["services"]["app"]["environment"]["APP_PLATFORM"] = "5TRATUMOS"
                    (package / "docker-compose.yml").write_text(yaml.safe_dump(value, sort_keys=False))
                    (package / "5tratstore-app.yml").write_bytes((PACKAGE / "5tratstore-app.yml").read_bytes())
                    env = dict(os.environ, STORE_CHANNEL=str(current['services']['app']['environment']['APP_CHANNEL']).lower(),
                               STORE_ROOT=str(package.parent), STORE_DIR=PACKAGE.name, DEST=str(dest),
                               APP_ID="5tratsmack", STORE_PORT="57550", OUT_FILE="docker-compose.yml",
                               SOCKET_ACCESS_CHECKER=str(helper))
                    p = subprocess.run([sys.executable, "-c", block], env=env, capture_output=True,
                                       text=True, timeout=20)
                    self.assertEqual(p.returncode, 0, p.stderr)
                    outputs.append(yaml.safe_load((dest / "docker-compose.yml").read_text()))
                self.assertEqual(outputs[1]["services"]["app"]["environment"]["APP_PLATFORM"], EXPRESSION)
                outputs[1]["services"]["app"]["environment"]["APP_PLATFORM"] = "5TRATUMOS"
                self.assertEqual(outputs[0], outputs[1])

    @unittest.skipUnless(os.environ.get("SMACK_PLATFORM_COMPOSE_COMMAND"),
                         "opt-in real Compose config command not provided")
    def test_real_compose_defaults_native_and_honors_umbrel_export(self):
        command = shlex.split(os.environ["SMACK_PLATFORM_COMPOSE_COMMAND"])
        current = source_model()
        # Native and Umbrel2 remove this legacy gateway service before runtime
        # config. It has no standalone image without Umbrel's support fragment.
        current["services"].pop("app_proxy")
        with tempfile.TemporaryDirectory(prefix="smack-platform-compose-") as temp:
            path = Path(temp) / "docker-compose.yml"
            path.write_text(yaml.safe_dump(current, sort_keys=False))
            parsed = []
            for supplied, expected in ((None, "5TRATUMOS"), ("", "5TRATUMOS"), ("UMBREL", "UMBREL")):
                env = dict(os.environ, APP_DATA_DIR="/tmp/smack-platform-public-data",
                           APP_PASSWORD="public-test-password", JWT_SECRET="public-test-jwt", NETWORK_IP="10.21.0.0")
                env.pop("APP_5TRATSMACK_PLATFORM", None)
                if supplied is not None:
                    env["APP_5TRATSMACK_PLATFORM"] = supplied
                p = subprocess.run([*command, "--project-name", "smack-platform-proof", "--file", str(path),
                                    "config", "--format", "json"], env=env, capture_output=True,
                                   text=True, timeout=20)
                self.assertEqual(p.returncode, 0, p.stderr)
                output = json.loads(p.stdout)
                self.assertEqual(output["services"]["app"]["environment"]["APP_PLATFORM"], expected)
                output["services"]["app"]["environment"]["APP_PLATFORM"] = "5TRATUMOS"
                parsed.append(output)
            self.assertEqual(parsed[0], parsed[1])
            self.assertEqual(parsed[0], parsed[2])


if __name__ == "__main__":
    unittest.main()
