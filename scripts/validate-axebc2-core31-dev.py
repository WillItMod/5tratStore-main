#!/usr/bin/env python3
from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "willitmod-dev-bc2"


def require(condition, message):
    if not condition:
        raise SystemExit(message)


compose = (APP / "docker-compose.yml").read_text(encoding="utf-8")
manifest = (APP / "umbrel-app.yml").read_text(encoding="utf-8")
node_config = (APP / "data/templates/bitcoinII.conf.template").read_text(encoding="utf-8")

require('version: "0.1.10-dev"' in manifest, "manifest must be 0.1.10-dev")
require("Requires 5tratumOS 0.7.11" in manifest, "OS prerequisite must be disclosed")
require('"2345:3333/tcp"' in compose, "Stratum host port 2345 must be retained")
require("SUPPORT_CHECKIN_ENABLED: \"false\"" in compose, "telemetry must default off")
require("create_host_path: false" in compose, "build metadata bind must fail closed")
require("/etc/5tratumos/build.json" in compose, "build metadata must be mounted")
require(
    ".5tratumos-rollback-policy.json" in (APP / "data/init/init.sh").read_text(encoding="utf-8"),
    "init must use the policy filename consumed by AxeBC2 and 5tratumOS",
)
require(
    "alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1"
    in compose,
    "init image must be pinned",
)
require(
    "ghcr.io/willitmod/docker-ckpool-solo:590fb2a@sha256:8a9a7f10c8138d0f55533132ee7710a06715a42a49f75efb39be3350ada4fa6e"
    in compose,
    "CKPool image must retain its exact pin",
)
require("natpmp=0" in node_config and "upnp=1" not in node_config, "NAT-PMP must be off")
require(not re.search(r'^\s+-\s+"?8338:', compose, re.MULTILINE), "P2P must not be published")

for placeholder in ("CORE31_CANDIDATE_DIGEST_REQUIRED", "APP_CANDIDATE_DIGEST_REQUIRED"):
    require(placeholder in compose, f"pending digest sentinel is missing: {placeholder}")

require(
    compose.count("create_host_path: false") == 9,
    "every AxeBC2 host bind must disable implicit source-path creation",
)


def yaml_python():
    candidates = [os.environ.get("YAML_PYTHON"), "/usr/bin/python3", sys.executable]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            check = subprocess.run(
                [candidate, "-c", "import yaml"], capture_output=True, check=False
            )
            if check.returncode == 0:
                return candidate
    raise SystemExit("PyYAML-capable Python is required for merged Compose validation")


def validate_platform_merged_compose():
    docker = shutil.which("docker")
    require(docker is not None, "Docker Compose is required for merged Compose validation")
    with tempfile.TemporaryDirectory(prefix="axebc2-compose-") as raw_temp:
        temp = Path(raw_temp)
        app_data = temp / "state/apps/axebc2"
        for relative in (
            "data/templates",
            "data/init",
            "data/node",
            "data/pool/config",
            "data/pool/www",
        ):
            (app_data / relative).mkdir(parents=True, exist_ok=True)
        (app_data / "data/init/init.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        source = temp / "docker-compose.yml"
        source.write_text(
            compose.replace("CORE31_CANDIDATE_DIGEST_REQUIRED", "a" * 64).replace(
                "APP_CANDIDATE_DIGEST_REQUIRED", "b" * 64
            ),
            encoding="utf-8",
        )
        merged = temp / "platform-merged-compose.json"
        transform = """
import json, sys, yaml
with open(sys.argv[1], encoding='utf-8') as handle:
    config = yaml.safe_load(handle)
config['services'].pop('app_proxy', None)
with open(sys.argv[2], 'w', encoding='utf-8') as handle:
    json.dump(config, handle)
"""
        subprocess.run([yaml_python(), "-c", transform, source, merged], check=True)
        env = os.environ.copy()
        env.update(
            {
                "APP_DATA_DIR": str(app_data),
                "APP_PASSWORD": "validation-only",
                "JWT_SECRET": "validation-only",
                "NETWORK_IP": "10.21.0.0",
            }
        )
        result = subprocess.run(
            [docker, "compose", "-f", str(merged), "config", "--format", "json"],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        require(result.returncode == 0, f"merged Compose is invalid: {result.stderr}")
        rendered = json.loads(result.stdout)
        services = rendered["services"]
        require("app_proxy" not in services, "platform merge must remove legacy app_proxy")
        require(
            services["btc2d"]["depends_on"]["init"]["condition"]
            == "service_completed_successfully",
            "Core must wait for successful init completion",
        )
        for service in services.values():
            for volume in service.get("volumes", []):
                if volume.get("type") == "bind":
                    require(
                        volume.get("bind", {}).get("create_host_path") is False,
                        "rendered Compose contains an implicit host-path bind",
                    )


validate_platform_merged_compose()

subprocess.run(["sh", "-n", str(APP / "data/init/init.sh")], check=True)
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_axebc2_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
