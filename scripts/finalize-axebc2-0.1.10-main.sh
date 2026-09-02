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
    "app_image": "ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.10-candidate.6e4ef58218e8",
    "app_digest": app_digest,
    "source_revision": "6e4ef58218e8cd5a4d1113196f9872a7f501f52e",
    "core_image": "ghcr.io/willitmod/bitcoinii-core:31.1.0-rc.3c2cafcab19e",
    "core_digest": core_digest,
    "core_source_revision": "3c2cafcab19efde33c1e476a982c3389957dacb2",
    "core_candidate_run": 33674007419,
    "app_version": "0.1.10-dev",
}
for key, value in expected.items():
    if evidence.get(key) != value:
        raise SystemExit(f"DEV acceptance evidence {key!r} must equal {value!r}")
if not str(evidence.get("tested_on", "")).strip():
    raise SystemExit("DEV acceptance evidence requires the tested node identity")
try:
    datetime.datetime.fromisoformat(str(evidence["tested_at"]).replace("Z", "+00:00"))
except (KeyError, ValueError):
    raise SystemExit("DEV acceptance evidence requires an ISO-8601 tested_at value")
a=evidence.get("acceptance")
if not isinstance(a, dict): raise SystemExit("DEV acceptance evidence requires structured acceptance observations")
try: datetime.datetime.fromisoformat(str(a["observed_at"]).replace("Z", "+00:00"))
except (KeyError, ValueError): raise SystemExit("acceptance observed_at must be ISO-8601")
truth=("migration_required_marker_absent","migration_complete_marker_valid","verifychain_passed","payout_configured","payout_preserved","app_ui_privacy_passed","telemetry_disabled","app_rollback_rejected","os_rollback_rejected")
if any(a.get(k) is not True for k in truth): raise SystemExit("all required acceptance gates must be true")
if a.get("core_version",0) < 310000: raise SystemExit("Core 31 version was not observed")
if a.get("checkpoint_height") != 57752 or a.get("checkpoint_hash") != "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576": raise SystemExit("official checkpoint observation is invalid")
hex64=lambda v: isinstance(v,str) and bool(re.fullmatch(r"[0-9a-f]{64}",v))
minimum="0000000000000000000000000000000000000000000000959028194ff1139272"
if not hex64(a.get("chainwork")) or a["chainwork"] < minimum: raise SystemExit("observed chainwork is below minimum")
if a.get("ibd") is not False or not isinstance(a.get("verification_progress"),(int,float)) or a["verification_progress"] < 0.999: raise SystemExit("node synchronization evidence is incomplete")
if not isinstance(a.get("blocks"),int) or a["blocks"] != a.get("headers") or a["blocks"] != a.get("explorer_common_height"): raise SystemExit("node/explorer heights do not match")
if not hex64(a.get("best_block_hash")) or a["best_block_hash"] != a.get("explorer_common_hash"): raise SystemExit("node/explorer hashes do not match")
if not isinstance(a.get("outbound_core31_peers"),int) or a["outbound_core31_peers"] < 3: raise SystemExit("fewer than three outbound Core 31 peers observed")
if a.get("verifychain_level") != 4: raise SystemExit("verifychain level 4 was not recorded")
if a.get("pool_stratum_result") != "passed": raise SystemExit("pool/Stratum acceptance did not pass")
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
