#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: $0 APP_INDEX_DIGEST DEV_ACCEPTANCE_JSON" >&2
  exit 64
fi

app_digest="$1"
evidence="$2"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
compose="$repo_root/willitmod-dev-bc2/docker-compose.yml"
docker_bin="${DOCKER_BIN:-docker}"
curl_bin="${CURL_BIN:-curl}"
jq_bin="${JQ_BIN:-jq}"
app_tag="ghcr.io/willitmod/axebc2-app:0.1.11"
core_tag="ghcr.io/willitmod/bitcoinii-core:31.1.0"
expected_app_digest="sha256:23a7962e223da5549eba52697c6f4cfa16ab74cba935c68c48148a4c515302b4"
core_digest="sha256:8875917ece57668fe9925d40a256ce8d429a3071511bb555d4ace1fa4370afc6"

fail() { echo "ERROR: $*" >&2; exit 1; }
[[ "$app_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "app digest is not an exact sha256 digest"
[[ "$app_digest" == "$expected_app_digest" ]] || fail "app digest must equal the tested DEV candidate digest"
[[ "$core_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "Core digest is not an exact sha256 digest"
[[ -f "$evidence" ]] || fail "DEV acceptance evidence does not exist: $evidence"
command -v "$docker_bin" >/dev/null 2>&1 || fail "Docker is required for registry verification"
command -v "$curl_bin" >/dev/null 2>&1 || fail "curl is required for anonymous registry verification"
command -v "$jq_bin" >/dev/null 2>&1 || fail "jq is required for anonymous registry verification"
docker_host="${DOCKER_HOST:-}"
if [[ -z "$docker_host" ]]; then
  active_context="$("$docker_bin" context show)" || fail "cannot determine active Docker context"
  [[ -n "$active_context" ]] || fail "active Docker context is empty"
  docker_host="$("$docker_bin" context inspect "$active_context" --format '{{.Endpoints.docker.Host}}')" || fail "cannot resolve active Docker daemon endpoint"
fi
[[ "$docker_host" =~ ^(unix|tcp|ssh|npipe)://[^[:space:]]+$ ]] || fail "Docker daemon endpoint is missing or malformed"

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
    "app_image": "ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.11-candidate.ecf6e2c8cfd0",
    "app_digest": app_digest,
    "app_candidate_run": 33895447789,
    "source_revision": "ecf6e2c8cfd0e42ea53d3cc146b18cd6d4c4b563",
    "core_image": "ghcr.io/willitmod/bitcoinii-core:31.1.0-rc.cdf44542dde2",
    "core_digest": core_digest,
    "core_source_revision": "cdf44542dde255648008249d187fafc15f3a2f09",
    "core_candidate_run": 33675068951,
    "app_version": "0.1.11-dev",
    "tested_os_version": "v0.7.12-dev",
    "tested_os_bundle_sha256": "11a35e68ab169eb0446485992a57b33fae018a92020b7d86bbf9a005571377af",
    "dev_store_revision": "249ab61506dc09c2151d39e2b210f5f18d75ff21",
    "dev_compose_sha256": "93ceba92069947f47d650a5fb32205836fe070d83707f36912a2e0e83beb1244",
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
truth=("migration_required_marker_absent","migration_started_marker_valid","migration_complete_marker_valid","verifychain_passed","payout_configured","payout_preserved","app_ui_privacy_passed","payout_validation_passed","invalid_payout_rejected_without_mutation","rpc_unavailable_rejected_without_mutation","pending_payout_revalidation_passed","main_payout_banner_hidden","pool_config_directory_writable","ckpool_sharelog_ownership_repaired","telemetry_disabled","p2p_port_unpublished","natpmp_disabled","post_completion_restart_passed","reindex_not_repeated","app_rollback_rejected","os_rollback_rejected")
if any(a.get(k) is not True for k in truth): raise SystemExit("all required acceptance gates must be true")
if a.get("chain") != "main" or a.get("competing_valid_tips") != 0: raise SystemExit("main chain must have no competing valid tips")
if a.get("core_version") != 310100: raise SystemExit("exact Core 31.1.0 version was not observed")
if a.get("checkpoint_height") != 57752 or a.get("checkpoint_hash") != "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576": raise SystemExit("official checkpoint observation is invalid")
hex64=lambda v: isinstance(v,str) and bool(re.fullmatch(r"[0-9a-f]{64}",v))
minimum="0000000000000000000000000000000000000000000000959028194ff1139272"
if not hex64(a.get("chainwork")) or a["chainwork"] < minimum: raise SystemExit("observed chainwork is below minimum")
if a.get("ibd") is not False or not isinstance(a.get("verification_progress"),(int,float)) or a["verification_progress"] < 0.999999: raise SystemExit("node synchronization evidence is incomplete")
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
  local ref="$1" expected="$2" path repository tag token headers resolved
  [[ "$ref" != *-dev* && "$ref" =~ :[0-9]+\.[0-9]+\.[0-9]+$ ]] \
    || fail "MAIN registry reference is not a stable release tag: $ref"
  path="${ref#ghcr.io/}"; repository="${path%:*}"; tag="${path##*:}"
  token="$("$curl_bin" -fsSL "https://ghcr.io/token?service=ghcr.io&scope=repository:${repository}:pull" | "$jq_bin" -er '.token')" \
    || fail "anonymous token request failed for $ref"
  headers="$("$curl_bin" -fsSI -H "Authorization: Bearer $token" \
    -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' \
    "https://ghcr.io/v2/${repository}/manifests/${tag}")" \
    || fail "anonymous manifest HEAD failed for $ref"
  resolved="$(printf '%s\n' "$headers" | awk 'tolower($0) ~ /^docker-content-digest:/ {sub(/^[^:]*:[[:space:]]*/, ""); sub(/\r$/, ""); print}' | tail -n 1)"
  [[ "$resolved" =~ ^sha256:[0-9a-f]{64}$ ]] || fail "$ref returned a missing or malformed Docker-Content-Digest"
  [[ "$resolved" == "$expected" ]] \
    || fail "$ref resolves to ${resolved:-nothing}, expected $expected"
}

verify_index() {
  local ref="$1" digest="$2" manifest
  manifest="$("$docker_bin" --host "$docker_host" --config "$anon_config" manifest inspect "$ref@$digest")" \
    || fail "anonymous manifest inspection failed for $ref@$digest"
  python3 -c '
import json, sys
doc=json.load(sys.stdin)
platforms={(m.get("platform",{}).get("os"),m.get("platform",{}).get("architecture")) for m in doc.get("manifests",[])}
missing={("linux","amd64"),("linux","arm64")}-platforms
if missing: raise SystemExit("missing required platforms: "+", ".join("/".join(x) for x in sorted(missing)))
' <<<"$manifest" || fail "$ref@$digest is not the required amd64+arm64 index"
  "$docker_bin" --host "$docker_host" --config "$anon_config" pull --platform linux/amd64 "$ref@$digest" >/dev/null \
    || fail "anonymous amd64 pull failed for $ref@$digest"
  "$docker_bin" --host "$docker_host" --config "$anon_config" pull --platform linux/arm64 "$ref@$digest" >/dev/null \
    || fail "anonymous arm64 pull failed for $ref@$digest"
}

resolve_tag "$app_tag" "$app_digest"
resolve_tag "$core_tag" "$core_digest"
verify_index "$app_tag" "$app_digest"
verify_index "$core_tag" "$core_digest"

[[ "$(grep -oF 'APP_PROMOTED_DIGEST_REQUIRED' "$compose" | wc -l | tr -d ' ')" == 1 ]] \
  || fail "expected exactly one app digest sentinel"
[[ "$(grep -oF "$core_tag@$core_digest" "$compose" | wc -l | tr -d ' ')" == 2 ]] \
  || fail "expected exactly two retained Core pins"
[[ "$(grep -oF '_DIGEST_REQUIRED' "$compose" | wc -l | tr -d ' ')" == 1 ]] \
  || fail "unexpected digest sentinel"

tmp="$(mktemp "${compose}.finalize.XXXXXX")"
sed -e "s/APP_PROMOTED_DIGEST_REQUIRED/${app_digest#sha256:}/g" \
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

printf 'Finalized AxeBC2 0.1.11 MAIN\napp=%s\ncore=%s\nDEV evidence=%s\n' \
  "$app_digest" "$core_digest" "$evidence"
