#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
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

subprocess.run(["sh", "-n", str(APP / "data/init/init.sh")], check=True)
suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), pattern="test_axebc2_*.py")
result = unittest.TextTestRunner(verbosity=2).run(suite)
sys.exit(0 if result.wasSuccessful() else 1)
