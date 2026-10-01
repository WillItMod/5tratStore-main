#!/usr/bin/env python3
"""Validate the exact protected app and preserved broker/store contract."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'willitmod-dev-5tratsmack'
VERSION = '0.11.18'
REVISION = 'fa08d11623b51159f78c47ac2e2a93cab639cb71'
KDF_REF = 'ghcr.io/willitmod/5tratsmack-kdf:0.11.17-rc.99a34a0ef5f5@sha256:c3ce7e638bdf55710fbfb607145d76c7d6e00b81a35e4c843645d9815f862087'
CHANNEL = 'main'
CKPOOL_REF = 'ghcr.io/willitmod/5tratsmack-ckpool:0.11.3@sha256:95a1a5f343d579206a0f8bb3c961cafa7500b5d487211a0cfb7b989cf34b895e'
RECORD = json.loads((ROOT / 'SMACK-RELEASE-2026-10-01.json').read_text())
EVIDENCE_BYTES = (ROOT / 'SMACK-PUBLISHED-IMAGES-2026-10-01.json').read_bytes()
EVIDENCE = json.loads(EVIDENCE_BYTES)
APP_REF = RECORD['appImageRef']
assert RECORD['registryEvidenceSha256'] == hashlib.sha256(EVIDENCE_BYTES).hexdigest()
assert RECORD['version'] == EVIDENCE['version'] == VERSION
assert RECORD['sourceRevision'] == EVIDENCE['sourceRevision'] == REVISION
assert RECORD['channel'] == CHANNEL
assert RECORD['kdfImageRef'] == KDF_REF
assert APP_REF == EVIDENCE['appImageRef']
assert re.fullmatch(r'ghcr.io/willitmod/5tratsmack-app:0\.11\.18@sha256:[0-9a-f]{64}', APP_REF)
assert EVIDENCE['anonymousPullVerified'] is True
assert EVIDENCE['platforms'] == ['linux/amd64', 'linux/arm64']
assert EVIDENCE['validation']['nativeRuntimeAndLayerChecks'] is True
assert EVIDENCE['validation']['liveProofAcrossTwoCacheExpiries'] is True
assert EVIDENCE['validation']['retainedHistoryPreserved'] is True
assert EVIDENCE['validation']['walletAndTradeMutationPerformed'] is False

def one(pattern, text):
    matches = re.findall(pattern, text, re.M)
    assert len(matches) == 1, (pattern, len(matches))
    return matches[0]

primary = (APP / '5tratstore-app.yml').read_bytes()
assert primary == (APP / 'umbrel-app.yml').read_bytes(), 'compatibility manifests differ'
manifest = primary.decode()
compose = (APP / 'docker-compose.yml').read_text()
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
for line in (
    '    image: alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1',
    '    image: ghcr.io/willitmod/5tratsmack-upnp:0.11.1@sha256:c85d527b8a12007be2565b200b99dfe46781ddaa773831852414d2cc5ad041d0',
    '    image: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070',
    '      BCH2_NODE_IMAGE: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070',
):
    assert compose.splitlines().count(line) == 1, 'protected Core/helper image changed'
assert compose.count('    stop_signal: SIGINT') == 1
assert compose.count('    hostname: 5tratsmack-app') == 1
assert compose.count('      test: ["CMD", "curl", "--fail", "--silent", "--max-time", "3", "http://127.0.0.1:3000/api/about"]') == 1
assert compose.count('      FIVETRAT_UPDATER_ENABLED: "0"') == 1
assert '${APP_DATA_DIR}' in compose and '${APP_PASSWORD}' in compose
assert f'- **5tratSmack** (`willitmod-dev-5tratsmack`) - `{VERSION}`' in (ROOT / 'README.md').read_text()
for phrase in ('bounded recent feed', 'coinbase output zero', 'Trade Pulse', 'Gleec', 'final transaction approval', 'Block alerts in this browser', 'local to that browser', 'OS and MUX notification acknowledgements remain separate'):
    assert phrase in manifest, phrase
assert 'has completed public-chain' not in manifest
print(f'5tratSmack {CHANNEL.upper()} {VERSION}: native app pinned, tested broker reused, metadata aligned')
