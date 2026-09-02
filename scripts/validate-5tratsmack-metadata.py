#!/usr/bin/env python3
from pathlib import Path
import re


REPO_ROOT = Path(__file__).resolve().parents[1]
APP_DIR = REPO_ROOT / "willitmod-dev-5tratsmack"

EXPECTED_VERSION = "0.11.11"
EXPECTED_PHASE = "STABLE"
EXPECTED_SOURCE_REVISION = "bd3aa4dbb0e915c7593e461ebf09546654d49134"
EXPECTED_APP_REF = (
    "ghcr.io/willitmod/5tratsmack-app:0.11.11@"
    "sha256:329b820a39beed7be4441d3c10ce694d7dedc579b62d494084bfcfe8c7755909"
)
EXPECTED_CKPOOL_REF = (
    "ghcr.io/willitmod/5tratsmack-ckpool:0.11.3@"
    "sha256:95a1a5f343d579206a0f8bb3c961cafa7500b5d487211a0cfb7b989cf34b895e"
)
EXPECTED_NON_APP_IMAGE_LINES = (
    "    image: alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1",
    "    image: ghcr.io/willitmod/5tratsmack-upnp:0.11.1@sha256:c85d527b8a12007be2565b200b99dfe46781ddaa773831852414d2cc5ad041d0",
    "    image: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070",
    "    image: ghcr.io/willitmod/5tratsmack-kdf:0.11.1@sha256:9eff0bfdc330bb997eacbce2b98500a52a084d682aec3644b73e663d54e6606a",
    "      BCH2_NODE_IMAGE: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070",
)

primary = APP_DIR / "5tratstore-app.yml"
compatibility = APP_DIR / "umbrel-app.yml"
compose = APP_DIR / "docker-compose.yml"
readme = REPO_ROOT / "README.md"

for path in (primary, compatibility, compose, readme):
    if not path.is_file() or not path.stat().st_size:
        raise SystemExit(f"missing required store file: {path}")

primary_bytes = primary.read_bytes()
compatibility_bytes = compatibility.read_bytes()
if primary_bytes != compatibility_bytes:
    raise SystemExit("5tratstore-app.yml and umbrel-app.yml must remain byte-identical")

manifest_text = primary_bytes.decode("utf-8")
compose_text = compose.read_text(encoding="utf-8")
readme_text = readme.read_text(encoding="utf-8")


def one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise SystemExit(f"expected one {label}, found {len(matches)}")
    return matches[0]


manifest_version = one(
    r'^version:\s*["\']?([^"\'\s]+)', manifest_text, "manifest version"
)
manifest_id = one(r"^id:\s*([^\s]+)", manifest_text, "manifest id")
source_revision = one(
    r"^# Release source revision:\s*([0-9a-f]{40})$",
    compose_text,
    "release source revision",
)
app_version = one(
    r'^\s{6}APP_VERSION:\s*["\']?([^"\'\s]+)', compose_text, "APP_VERSION"
)
release_phase = one(
    r'^\s{6}APP_RELEASE_PHASE:\s*["\']?([^"\'\s]+)',
    compose_text,
    "APP_RELEASE_PHASE",
)
release_tag = one(
    r'^\s{6}FIVETRAT_RELEASE_TAG:\s*["\']?([^"\'\s]+)',
    compose_text,
    "FIVETRAT_RELEASE_TAG",
)
app_revision = one(
    r"^\s{6}APP_REVISION:\s*([0-9a-f]{40})$", compose_text, "APP_REVISION"
)

if manifest_id != "willitmod-dev-5tratsmack":
    raise SystemExit(f"unexpected manifest id: {manifest_id}")
if {manifest_version, app_version, release_tag} != {EXPECTED_VERSION}:
    raise SystemExit(
        "store version mismatch: "
        f"manifest={manifest_version}, APP_VERSION={app_version}, "
        f"FIVETRAT_RELEASE_TAG={release_tag}, expected={EXPECTED_VERSION}"
    )
if release_phase != EXPECTED_PHASE:
    raise SystemExit(
        f"unexpected APP_RELEASE_PHASE: {release_phase}, expected {EXPECTED_PHASE}"
    )
if source_revision != EXPECTED_SOURCE_REVISION or app_revision != EXPECTED_SOURCE_REVISION:
    raise SystemExit(
        "source revision mismatch: "
        f"comment={source_revision}, APP_REVISION={app_revision}, "
        f"expected={EXPECTED_SOURCE_REVISION}"
    )

app_refs = re.findall(
    r"^\s+(?:image|APP_IMAGE):\s*(ghcr\.io/willitmod/5tratsmack-app:\S+)$",
    compose_text,
    flags=re.MULTILINE,
)
if app_refs != [EXPECTED_APP_REF, EXPECTED_APP_REF]:
    raise SystemExit(f"app image references are not the promoted stable image: {app_refs}")

ckpool_refs = re.findall(
    r"^\s+(?:image|CKPOOL_IMAGE):\s*(ghcr\.io/willitmod/5tratsmack-ckpool:\S+)$",
    compose_text,
    flags=re.MULTILINE,
)
if ckpool_refs != [EXPECTED_CKPOOL_REF, EXPECTED_CKPOOL_REF]:
    raise SystemExit(f"CKPool references changed during the app-only release: {ckpool_refs}")

for line in EXPECTED_NON_APP_IMAGE_LINES:
    if compose_text.count(line) != 1:
        raise SystemExit(f"non-app image reference changed or duplicated: {line}")

required_compose_lines = (
    "      APP_CHANNEL: MAIN",
    "      FIVETRAT_STORE_UPDATE_CHANNEL: main",
    '      FIVETRAT_UPDATER_ENABLED: "0"',
)
for line in required_compose_lines:
    if compose_text.count(line) != 1:
        raise SystemExit(f"expected one exact compose line: {line}")

expected_readme_line = (
    "- **5tratSmack** (`willitmod-dev-5tratsmack`) - `0.11.11`"
)
if readme_text.count(expected_readme_line) != 1:
    raise SystemExit("README current-version entry is not exactly 0.11.11")

for release_note_fragment in (
    "authenticated DEV catalogue",
    "never offers a downgrade",
    "private local/global trade separation",
    "default-on 5% development contribution",
):
    if release_note_fragment not in manifest_text:
        raise SystemExit(f"release notes missing: {release_note_fragment}")

print(
    "5tratSmack MAIN metadata verified: "
    f"version={EXPECTED_VERSION} source={EXPECTED_SOURCE_REVISION} "
    "promoted stable app pinned; CKPool and non-app images unchanged"
)
