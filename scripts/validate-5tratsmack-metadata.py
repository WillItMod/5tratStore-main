#!/usr/bin/env python3
"""Ensure the exact candidate app/backend pair and store versions agree."""
from pathlib import Path
import re
ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "willitmod-dev-5tratsmack"
VERSION = '0.11.16'
REVISION = 'fe2559223ed0fbd4fcd8bd5180713dd6b9686a29'
APP_REF = 'ghcr.io/willitmod/5tratsmack-app:0.11.16-rc.fe2559223ed0@sha256:857a73d220ce36204afb5b4d1dc11afe13511e00fa30878ea6339dd8d64d0668'
KDF_REF = 'ghcr.io/willitmod/5tratsmack-kdf:0.11.16-rc.fe2559223ed0@sha256:34392d2c5bb5371d82d4ecea3def9dc79c2d02427b0cb3926a6cc0066b88fdbf'
CKPOOL_REF = 'ghcr.io/willitmod/5tratsmack-ckpool:0.11.3@sha256:95a1a5f343d579206a0f8bb3c961cafa7500b5d487211a0cfb7b989cf34b895e'
CHANNEL = 'main'

PROTECTED_IMAGE_LINES = (
    "    image: alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1",
    "    image: ghcr.io/willitmod/5tratsmack-upnp:0.11.1@sha256:c85d527b8a12007be2565b200b99dfe46781ddaa773831852414d2cc5ad041d0",
    "    image: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070",
    "      BCH2_NODE_IMAGE: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070",
)

primary = (APP / "5tratstore-app.yml").read_bytes()
assert primary == (APP / "umbrel-app.yml").read_bytes(), "compatibility manifests differ"
manifest = primary.decode()
compose = (APP / "docker-compose.yml").read_text()
for line in PROTECTED_IMAGE_LINES:
    assert compose.splitlines().count(line) == 1, "protected core/helper image changed or duplicated"
def one(pattern, text):
    result = re.findall(pattern, text, re.M)
    assert len(result) == 1, (pattern, len(result))
    return result[0]
assert one(r'^id: (\S+)$', manifest) == 'willitmod-dev-5tratsmack'
assert one(r'^version: "([^"\n]+)"$', manifest) == VERSION
for key in ('APP_VERSION', 'FIVETRAT_RELEASE_TAG'):
    assert one(r'^      ' + key + r': (\S+)$', compose) == VERSION
assert one(r'^# Release source revision: (\S+)$', compose) == REVISION
assert one(r'^      APP_REVISION: (\S+)$', compose) == REVISION
assert one(r'^      APP_CHANNEL: (\S+)$', compose) == CHANNEL.upper()
assert one(r'^      FIVETRAT_STORE_UPDATE_CHANNEL: (\S+)$', compose) == CHANNEL
assert one(r'^      APP_RELEASE_PHASE: (\S+)$', compose) == ('RC1' if CHANNEL == 'dev' else 'STABLE')
for component, expected, count in [('app', APP_REF, 2), ('kdf', KDF_REF, 1), ('ckpool', CKPOOL_REF, 2)]:
    refs = re.findall(r'^\s+(?:image|APP_IMAGE|CKPOOL_IMAGE): (ghcr\.io/willitmod/5tratsmack-' + component + r':\S+)$', compose, re.M)
    assert refs == [expected] * count, (component, 'unexpected image reference')
    assert re.search(r'@sha256:[0-9a-f]{64}$', expected), 'unpinned image'
assert compose.count('    stop_signal: SIGINT') == 1
assert compose.count('    hostname: 5tratsmack-app') == 1
assert 'has completed public-chain' not in manifest
assert '${APP_DATA_DIR}' in compose and '${APP_PASSWORD}' in compose
assert compose.count('      FIVETRAT_UPDATER_ENABLED: "0"') == 1
assert f'- **5tratSmack** (`willitmod-dev-5tratsmack`) - `{VERSION}`' in (ROOT/'README.md').read_text()
for phrase in ('Trade Pulse', 'Gleec', 'final transaction approval', 'application and trading backend', 'Block alerts in this browser', 'coinbase output zero'):
    assert phrase in manifest, phrase
print(f'5tratSmack {CHANNEL.upper()} {VERSION}: app/KDF pair pinned; versions aligned; core, CKPool and helpers unchanged')
