#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import argparse
from axebc2_release_state import validate as validate_release_state


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "willitmod-dev-bc2"


def require(condition, message):
    if not condition:
        raise SystemExit(message)


compose = (APP / "docker-compose.yml").read_text(encoding="utf-8")
parser=argparse.ArgumentParser(); parser.add_argument("--phase",required=True,choices=("prefinalization","finalized")); phase=parser.parse_args().phase
try: validate_release_state(compose,phase)
except ValueError as exc: raise SystemExit(str(exc))
manifest = (APP / "umbrel-app.yml").read_text(encoding="utf-8")
node_config = (APP / "data/templates/bitcoinII.conf.template").read_text(encoding="utf-8")

require('version: "0.1.11"' in manifest, "manifest must be stable 0.1.11")
require('id: willitmod-dev-bc2' in manifest, "stable store identity must remain unchanged")
require('APP_CHANNEL: "MAIN"' in compose, "stable app channel must be MAIN")
require('APP_VERSION_SUFFIX: ""' in compose, "stable app must have no DEV suffix")
require("beginning with 1, 3, or bc1" in manifest, "release notes must describe valid payout families")
require("misleading payout warning from MAIN builds" in manifest, "release notes must describe the MAIN banner fix")
require(
    "keeps CKPool /config writable on" in manifest
    and "conditionally repairs /www ownership" in manifest,
    "release notes must accurately describe the config and sharelog repairs",
)
require("does not trigger another blockchain reindex" in manifest, "release notes must rule out a repeated reindex")
require("Requires 5tratumOS 0.7.12" in manifest, "OS prerequisite must be disclosed")
require('"2345:3333/tcp"' in compose, "Stratum host port 2345 must be retained")
require("SUPPORT_CHECKIN_ENABLED: \"false\"" in compose, "telemetry must default off")
require("create_host_path: false" in compose, "build metadata bind must fail closed")
require("/etc/5tratumos/build.json" in compose, "build metadata must be mounted")
require('JWT_SECRET: "${JWT_SECRET}"' in compose, "init must receive the platform JWT secret")
require(
    "chown -R 1000:1000 /data/pool/config" in compose
    and compose.index("chown -R 1000:1000 /data/pool/config")
    < compose.index("exec /bin/sh /opt/axebc2/init.sh"),
    "versioned Compose init must keep fresh and preserved CKPool config writable",
)
require(
    "chown -R 1000:1000 /data/pool/www" in compose
    and compose.count("$$(stat -c '%u:%g' /data/pool/www") == 3
    and '"$(stat -c' not in compose,
    "versioned Compose init must repair CKPool sharelogs with escaped interpolation",
)
require(
    "previously seeded init script" in compose,
    "ownership repair must document why it cannot live only in seeded app data",
)
require(
    ".5tratumos-rollback-policy.json" in (APP / "data/init/init.sh").read_text(encoding="utf-8"),
    "init must use the policy filename consumed by AxeBC2 and 5tratumOS",
)
require(
    'minimum_app="0.1.10"' in (APP / "data/init/init.sh").read_text(encoding="utf-8"),
    "Core 31 rollback floor must remain 0.1.10",
)
require(
    'chown -R 1000:1000 "${data_dir}/pool/config"'
    in (APP / "data/init/init.sh").read_text(encoding="utf-8"),
    "seeded init must retain targeted CKPool config ownership repair",
)
require(
    "repair_sharelog_ownership" in (APP / "data/init/init.sh").read_text(encoding="utf-8"),
    "init must retain the conditional CKPool sharelog ownership repair",
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
            compose.replace("APP_PROMOTED_DIGEST_REQUIRED", "b" * 64),
            encoding="utf-8",
        )
        parsed = temp / "parsed-compose.json"
        merged = temp / "platform-merged-compose.json"
        transform = """
import json, sys, yaml
with open(sys.argv[1], encoding='utf-8') as handle:
    config = yaml.safe_load(handle)
with open(sys.argv[2], 'w', encoding='utf-8') as handle:
    json.dump(config, handle)
"""
        subprocess.run([yaml_python(), "-c", transform, source, parsed], check=True)
        contract_path = ROOT / "tests/fixtures/5tratumos_contract_4f979cb.py"
        spec = importlib.util.spec_from_file_location("pinned_5tratumos_contract", contract_path)
        contract = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(contract)
        rendered_contract = contract.materialize_compose(
            json.loads(parsed.read_text(encoding="utf-8")), 21219
        )
        declared_bind_targets = []
        for service_name, service in rendered_contract["services"].items():
            for volume in service.get("volumes", []):
                if volume.get("type") == "bind":
                    require(
                        volume.get("bind", {}).get("create_host_path") is False,
                        "platform-merged Compose contains an implicit host-path bind",
                    )
                    declared_bind_targets.append((service_name, volume.get("target")))
        merged.write_text(json.dumps(rendered_contract), encoding="utf-8")
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
            services["init"]["environment"]["JWT_SECRET"] == "validation-only",
            "platform-merged init service must receive JWT_SECRET",
        )
        require(
            services["app"]["ports"] == [{"mode": "ingress", "target": 3000, "published": "21219", "protocol": "tcp"}],
            "platform merge must materialize the app-proxy host port on the app service",
        )
        require(
            "umbrel_main_network" not in rendered.get("networks", {}),
            "platform merge must remove the legacy shared network",
        )
        require(
            services["app"]["restart"] == "unless-stopped"
            and services["ckpool"]["restart"] == "unless-stopped",
            "platform merge must normalize service restart policies",
        )
        require(
            services["btc2d"]["depends_on"]["init"]["condition"]
            == "service_completed_successfully",
            "Core must wait for successful init completion",
        )
        # Compose releases differ in whether ``false`` boolean fields survive
        # JSON serialization. The materialized contract above must declare the
        # fail-closed value; the CLI output may omit it, but must never turn it
        # on or change the declared bind set.
        rendered_bind_targets = []
        for service_name, service in services.items():
            for volume in service.get("volumes", []):
                if volume.get("type") == "bind":
                    rendered_bind_targets.append((service_name, volume.get("target")))
                    create_host_path = volume.get("bind", {}).get("create_host_path")
                    require(
                        create_host_path is None or create_host_path is False,
                        "Docker Compose enabled or malformed implicit host-path creation",
                    )
        require(
            sorted(rendered_bind_targets) == sorted(declared_bind_targets),
            "Docker Compose changed the platform-declared host binds",
        )


validate_platform_merged_compose()

subprocess.run(["sh", "-n", str(APP / "data/init/init.sh")], check=True)
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_axebc2_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
