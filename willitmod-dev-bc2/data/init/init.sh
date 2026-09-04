#!/bin/sh
set -eu

data_dir="${AXEBC2_DATA_DIR:-/data}"
appdata_dir="${AXEBC2_APPDATA_DIR:-/appdata}"
build_file="${AXEBC2_BUILD_FILE:-/etc/5tratumos/build.json}"
templates_dir="${AXEBC2_TEMPLATES_DIR:-${data_dir}/templates}"
policy_file="${data_dir}/.5tratumos-rollback-policy.json"
node_dir="${data_dir}/node"
required_marker="${node_dir}/.core31-full-reindex-required.json"
complete_marker="${node_dir}/.core31-full-reindex-complete.json"
minimum_os="0.7.12"
minimum_app="0.1.10"
migration="bitcoinii-shockwave-core31-full-reindex"

fail() {
  echo "[axebc2-init] $*" >&2
  exit 78
}

if ! command -v jq >/dev/null 2>&1 || ! command -v envsubst >/dev/null 2>&1; then
  # The digest-pinned Alpine image is intentionally kept generic. These tools
  # come from its configured 3.22 repositories; a repository/network failure
  # exits here, before the OS check and before any persistent-data write.
  apk add --no-cache gettext-envsubst jq >/dev/null
fi

version_normalize() {
  printf '%s' "$1" | sed -nE 's/^v?([0-9]+(\.[0-9]+){1,3})([-+][0-9A-Za-z][0-9A-Za-z.-]*)?$/\1/p'
}

version_ge() {
  lhs="$(version_normalize "$1")"
  rhs="$(version_normalize "$2")"
  [ -n "$lhs" ] && [ -n "$rhs" ] || return 1
  component=1
  while [ "$component" -le 4 ]; do
    left="$(printf '%s' "$lhs" | cut -d. -f"$component")"
    right="$(printf '%s' "$rhs" | cut -d. -f"$component")"
    [ "$left" != "$lhs" ] || [ "$component" -eq 1 ] || left=0
    [ "$right" != "$rhs" ] || [ "$component" -eq 1 ] || right=0
    left="$(printf '%s' "${left:-0}" | sed 's/^0*//')"; left="${left:-0}"
    right="$(printf '%s' "${right:-0}" | sed 's/^0*//')"; right="${right:-0}"
    if [ "${#left}" -gt "${#right}" ]; then return 0; fi
    if [ "${#left}" -lt "${#right}" ]; then return 1; fi
    if [ "$left" != "$right" ]; then
      highest="$(printf '%s\n%s\n' "$left" "$right" | LC_ALL=C sort | tail -n 1)"
      [ "$highest" = "$left" ]
      return
    fi
    component=$((component + 1))
  done
  return 0
}

# This check deliberately precedes every write under /data or /appdata.
[ -r "$build_file" ] || fail "5tratumOS build metadata is missing or unreadable"
installed_os="$(jq -er '.tag | select(type == "string" and length > 0)' "$build_file" 2>/dev/null)" ||
  fail "5tratumOS build metadata has no valid tag"
version_ge "$installed_os" "$minimum_os" ||
  fail "5tratumOS ${installed_os} is unsupported; upgrade to ${minimum_os} or newer first"

atomic_json_write() {
  destination="$1"
  payload="$2"
  parent="$(dirname "$destination")"
  [ -d "$parent" ] || mkdir -p "$parent"
  temporary="${destination}.tmp.$$"
  trap 'rm -f "$temporary"' EXIT HUP INT TERM
  umask 077
  printf '%s\n' "$payload" >"$temporary" || fail "cannot write ${destination}"
  chmod 600 "$temporary" || fail "cannot protect ${destination}"
  if [ "${AXEBC2_TEST_SKIP_CHOWN:-false}" != "true" ]; then
    chown 1000:1000 "$temporary" || fail "cannot assign ${destination} to the app user"
  fi
  mv "$temporary" "$destination" || fail "cannot install ${destination}"
  trap - EXIT HUP INT TERM
}

policy_app="$minimum_app"
policy_os="$minimum_os"
policy_height=57750
if [ -e "$policy_file" ]; then
  [ -r "$policy_file" ] || fail "existing release policy is unreadable"
  jq -e '
    type == "object" and .schema == 1 and .app_id == "axebc2" and
    (.minimum_base_version | type == "string" and test("^v?[0-9]+(\\.[0-9]+){1,3}([-+][0-9A-Za-z][0-9A-Za-z.-]*)?$")) and
    (.minimum_5tratumos_version | type == "string" and test("^v?[0-9]+(\\.[0-9]+){1,3}([-+][0-9A-Za-z][0-9A-Za-z.-]*)?$")) and
    (.reason | type == "string" and length > 0) and
    (.recorded_at_height | type == "number" and floor == . and . >= 0)
  ' "$policy_file" >/dev/null 2>&1 || fail "existing release policy is malformed"
  existing_app="$(jq -r '.minimum_base_version' "$policy_file")"
  existing_os="$(jq -r '.minimum_5tratumos_version' "$policy_file")"
  existing_height="$(jq -r '.recorded_at_height' "$policy_file")"
  if version_ge "$existing_app" "$policy_app"; then policy_app="$existing_app"; fi
  if version_ge "$existing_os" "$policy_os"; then policy_os="$existing_os"; fi
  if [ "$existing_height" -gt "$policy_height" ]; then policy_height="$existing_height"; fi
fi
policy_payload="$(jq -cn \
  --arg app "$policy_app" --arg os "$policy_os" --argjson height "$policy_height" \
  '{schema:1,app_id:"axebc2",minimum_base_version:$app,minimum_5tratumos_version:$os,reason:"ShockWave Core 31 consensus activation requires a non-downgradable app and OS floor",recorded_at_height:$height}')"
atomic_json_write "$policy_file" "$policy_payload"

validate_migration_marker() {
  marker="$1"
  jq -e --arg migration "$migration" '
    type == "object" and .schema == 1 and .migration == $migration and
    .minimum_core_major == 31 and .activation_height == 57750
  ' "$marker" >/dev/null 2>&1
}

validate_complete_marker() {
  marker="$1"
  validate_migration_marker "$marker" &&
    jq -e '
      (.completed_at | type == "string" and test("^[0-9]{4}-[0-9]{2}-[0-9]{2}T.*(Z|[+]00:00)$")) and
      (.validated_height | type == "number" and floor == . and . >= 57750) and
      (.best_block_hash | type == "string" and test("^[0-9a-f]{64}$")) and
      (.core_version | type == "number" and floor == . and . >= 310000) and
      .checkpoint_height == 57752 and
      .checkpoint_hash == "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576" and
      (.validated_chainwork | type == "string" and test("^[0-9a-f]{64}$") and
        . >= "0000000000000000000000000000000000000000000000959028194ff1139272")
    ' "$marker" >/dev/null 2>&1
}

if [ -e "$complete_marker" ]; then
  [ -r "$complete_marker" ] && validate_complete_marker "$complete_marker" ||
    fail "existing Core 31 completion marker is invalid"
fi
if [ -e "$required_marker" ]; then
  [ -r "$required_marker" ] && validate_migration_marker "$required_marker" ||
    fail "existing Core 31 required marker is invalid"
fi

if { [ -e "${node_dir}/blocks" ] || [ -e "${node_dir}/chainstate" ]; } && [ ! -e "$complete_marker" ]; then
  required_payload='{"schema":1,"migration":"bitcoinii-shockwave-core31-full-reindex","minimum_core_major":31,"activation_height":57750}'
  atomic_json_write "$required_marker" "$required_payload"
fi

# Normal initialization starts only after the OS floor and migration policy exist.
if [ -n "${JWT_SECRET:-}" ]; then
  envfile="${appdata_dir}/.env"
  tmp="${envfile}.tmp.$$"
  if [ -f "$envfile" ]; then grep -v '^JWT_SECRET=' "$envfile" >"$tmp" || true; else : >"$tmp"; fi
  printf 'JWT_SECRET=%s\n' "$JWT_SECRET" >>"$tmp"
  chmod 600 "$tmp"
  chown 1000:1000 "$tmp" 2>/dev/null || true
  mv "$tmp" "$envfile"
fi

mkdir -p "$node_dir" "${data_dir}/pool/config" "${data_dir}/pool/www/pool" "${data_dir}/pool/www/users"
touch "${appdata_dir}/settings.yml"
chown 1000:1000 "${appdata_dir}/settings.yml" 2>/dev/null || true

if [ ! -f "${node_dir}/bitcoinII.conf" ]; then
  envsubst <"${templates_dir}/bitcoinII.conf.template" >"${node_dir}/bitcoinII.conf"
  chown -R 1000:1000 "$node_dir" 2>/dev/null || true
fi

# Existing installs may retain the old upnp=1 setting. Core 31 uses NAT-PMP;
# explicitly disable both forms rather than relying only on the new template.
node_conf="${node_dir}/bitcoinII.conf"
[ -r "$node_conf" ] || fail "BitcoinII configuration is unreadable"
node_conf_tmp="${node_conf}.tmp.$$"
awk '
  !/^[[:space:]]*(upnp|natpmp)[[:space:]]*=/ { print }
  END { print "natpmp=0" }
' "$node_conf" >"$node_conf_tmp" || fail "cannot disable automatic P2P port mapping"
chmod 600 "$node_conf_tmp" || fail "cannot protect BitcoinII configuration"
chown 1000:1000 "$node_conf_tmp" 2>/dev/null || true
mv "$node_conf_tmp" "$node_conf" || fail "cannot install BitcoinII configuration"

ckpool_conf="${data_dir}/pool/config/ckpool.conf"
needs_ckpool_regen=0
if [ -f "$ckpool_conf" ]; then
  grep -qE '"btcd"[[:space:]]*:[[:space:]]*\[' "$ckpool_conf" || needs_ckpool_regen=1
  grep -q '"zmqblock"' "$ckpool_conf" || needs_ckpool_regen=1
else
  needs_ckpool_regen=1
fi
if [ "$needs_ckpool_regen" -eq 1 ]; then
  existing_addr="$(grep -oE '\"btcaddress\"[[:space:]]*:[[:space:]]*\"[^\"]*\"' "$ckpool_conf" 2>/dev/null | head -n 1 | sed -E 's/.*\"btcaddress\"[[:space:]]*:[[:space:]]*\"([^\"]*)\".*/\1/' || true)"
  if [ -f "$ckpool_conf" ]; then mv "$ckpool_conf" "${ckpool_conf}.bak.$(date +%s 2>/dev/null || echo 0)"; fi
  envsubst <"${templates_dir}/ckpool.conf.template" >"$ckpool_conf"
  if [ -n "$existing_addr" ] && [ "$existing_addr" != "CHANGEME_BTC2_PAYOUT_ADDRESS" ]; then
    tmp="$(mktemp)"
    jq --arg a "$existing_addr" '.btcaddress=$a' "$ckpool_conf" >"$tmp" || fail "cannot preserve payout address"
    mv "$tmp" "$ckpool_conf"
  fi
  chown -R 1000:1000 "${data_dir}/pool" 2>/dev/null || true
fi

if [ ! -f "${data_dir}/pool/config/ckpool.args" ]; then
  printf '%s\n' '-B' >"${data_dir}/pool/config/ckpool.args"
  chown 1000:1000 "${data_dir}/pool/config/ckpool.args" 2>/dev/null || true
fi

settings="${data_dir}/ui/state/pool_settings.json"
if [ -f "$settings" ]; then
  addr="$(jq -r '.payoutAddress // empty' "$settings" 2>/dev/null || true)"
  if [ -n "$addr" ] && [ -f "$ckpool_conf" ]; then
    tmp="$(mktemp)"
    jq --arg a "$addr" '.btcaddress=$a' "$ckpool_conf" >"$tmp" || fail "cannot apply saved payout address"
    mv "$tmp" "$ckpool_conf"
    chown 1000:1000 "$ckpool_conf" 2>/dev/null || true
  fi
fi
