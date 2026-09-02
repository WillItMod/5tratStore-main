#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 APP_INDEX_DIGEST CORE_INDEX_DIGEST DEV_ACCEPTANCE_JSON" >&2
  exit 64
fi

app_digest="$1"
core_digest="$2"
evidence="$3"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
compose="$repo_root/willitmod-dev-bc2/docker-compose.yml"
docker_bin="${DOCKER_BIN:-docker}"
app_tag="ghcr.io/willitmod/axebc2-app:0.1.10"
core_tag="ghcr.io/willitmod/bitcoinii-core:31.1.0"

fail() { echo "ERROR: $*" >&2; exit 1; }
[[ "$app_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "app digest is not an exact sha256 digest"
[[ "$core_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "Core digest is not an exact sha256 digest"
[[ -f "$evidence" ]] || fail "DEV acceptance evidence does not exist: $evidence"
command -v "$docker_bin" >/dev/null 2>&1 || fail "Docker is required for registry verification"

# Promotion is allowed only from a recorded, successful DEV run of the exact
# two multi-architecture indexes that MAIN will reference.
python3 - "$evidence" "$app_digest" "$core_digest" <<'PY'
import datetime, json, re, sys
path, app_digest, core_digest = sys.argv[1:]
try:
    with open(path, encoding="utf-8") as handle:
        evidence = json.load(handle)
except (OSError, ValueError) as exc:
    raise SystemExit(f"invalid DEV acceptance evidence: {exc}")
expected = {
    "schema": 1,
    "result": "passed",
    "app_image": "ghcr.io/willitmod/axebc2-app:0.1.10-dev",
    "app_digest": app_digest,
    "core_image": "ghcr.io/willitmod/bitcoinii-core:31.1.0-dev",
    "core_digest": core_digest,
    "app_version": "0.1.10-dev",
}
for key, value in expected.items():
    if evidence.get(key) != value:
        raise SystemExit(f"DEV acceptance evidence {key!r} must equal {value!r}")
if not re.fullmatch(r"[0-9a-f]{40}", str(evidence.get("source_revision", ""))):
    raise SystemExit("DEV acceptance evidence requires an exact source revision")
if not str(evidence.get("tested_on", "")).strip():
    raise SystemExit("DEV acceptance evidence requires the tested node identity")
try:
    datetime.datetime.fromisoformat(str(evidence["tested_at"]).replace("Z", "+00:00"))
except (KeyError, ValueError):
    raise SystemExit("DEV acceptance evidence requires an ISO-8601 tested_at value")
checks = evidence.get("checks")
if not isinstance(checks, list) or not checks or not all(isinstance(v, str) and v.strip() for v in checks):
    raise SystemExit("DEV acceptance evidence requires a non-empty checks list")
PY

anon_config="$(mktemp -d "${TMPDIR:-/tmp}/axebc2-anonymous-docker.XXXXXX")"
cleanup() { rm -rf -- "$anon_config"; }
trap cleanup EXIT
printf '{"auths":{}}\n' >"$anon_config/config.json"

resolve_tag() {
  local ref="$1" expected="$2" output resolved
  [[ "$ref" != *-dev* && "$ref" =~ :[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || fail "MAIN registry reference is not a stable release tag: $ref"
  output="$("$docker_bin" --config "$anon_config" buildx imagetools inspect "$ref")" \
    || fail "anonymous registry resolution failed for $ref"
  resolved="$(printf '%s\n' "$output" | awk '$1 == "Digest:" {print $2; exit}')"
  [[ "$resolved" == "$expected" ]] \
    || fail "$ref resolves to ${resolved:-nothing}, expected $expected"
}

verify_index() {
  local ref="$1" digest="$2" manifest
  manifest="$("$docker_bin" --config "$anon_config" manifest inspect "$ref@$digest")" \
    || fail "anonymous manifest inspection failed for $ref@$digest"
  python3 -c '
import json, sys
doc=json.load(sys.stdin)
platforms={(m.get("platform",{}).get("os"),m.get("platform",{}).get("architecture")) for m in doc.get("manifests",[])}
missing={("linux","amd64"),("linux","arm64")}-platforms
if missing: raise SystemExit("missing required platforms: "+", ".join("/".join(x) for x in sorted(missing)))
' <<<"$manifest" || fail "$ref@$digest is not the required amd64+arm64 index"
  "$docker_bin" --config "$anon_config" pull --platform linux/amd64 "$ref@$digest" >/dev/null \
    || fail "anonymous amd64 pull failed for $ref@$digest"
  "$docker_bin" --config "$anon_config" pull --platform linux/arm64 "$ref@$digest" >/dev/null \
    || fail "anonymous arm64 pull failed for $ref@$digest"
}

resolve_tag "$app_tag" "$app_digest"
resolve_tag "$core_tag" "$core_digest"
verify_index "$app_tag" "$app_digest"
verify_index "$core_tag" "$core_digest"

[[ "$(grep -oF 'APP_PROMOTED_DIGEST_REQUIRED' "$compose" | wc -l | tr -d ' ')" == 1 ]] \
  || fail "expected exactly one app digest sentinel"
[[ "$(grep -oF 'CORE31_PROMOTED_DIGEST_REQUIRED' "$compose" | wc -l | tr -d ' ')" == 2 ]] \
  || fail "expected exactly two Core digest sentinels"

tmp="$(mktemp "${compose}.finalize.XXXXXX")"
sed -e "s/APP_PROMOTED_DIGEST_REQUIRED/${app_digest#sha256:}/g" \
    -e "s/CORE31_PROMOTED_DIGEST_REQUIRED/${core_digest#sha256:}/g" \
    "$compose" >"$tmp"
chmod 0644 "$tmp"
grep -F '_DIGEST_REQUIRED' "$tmp" >/dev/null && fail "unresolved digest sentinel remains"
[[ "$(grep -oF "$core_tag@$core_digest" "$tmp" | wc -l | tr -d ' ')" == 2 ]] \
  || fail "Core service and BTC2D_IMAGE do not carry the same digest"
grep -Fx "    image: $app_tag@$app_digest" "$tmp" >/dev/null \
  || fail "final app image reference is incorrect"
grep -Fx "    image: $core_tag@$core_digest" "$tmp" >/dev/null \
  || fail "final Core service image reference is incorrect"
grep -Fx "      BTC2D_IMAGE: \"$core_tag@$core_digest\"" "$tmp" >/dev/null \
  || fail "final BTC2D_IMAGE reference is incorrect"
mv -f "$tmp" "$compose"

printf 'Prepared AxeBC2 0.1.10 MAIN\napp=%s\ncore=%s\nDEV evidence=%s\n' \
  "$app_digest" "$core_digest" "$evidence"
