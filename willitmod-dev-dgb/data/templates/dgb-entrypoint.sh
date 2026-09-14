#!/bin/sh
set -eu

echo "[axedgb] DGB entrypoint starting"

if ! command -v digibyted >/dev/null 2>&1; then
  echo "[axedgb] ERROR: digibyted not found in PATH"
  exit 127
fi

heal_node_json() {
  file="$1"
  name="$2"
  [ -e "$file" ] || return 0

  if [ ! -s "$file" ]; then
    ts="$(date +%Y%m%dT%H%M%SZ 2>/dev/null || date +%s)"
    echo "[axedgb] Removing empty $name: $file"
    mv "$file" "$file.bad.$ts" 2>/dev/null || rm -f "$file" || true
    return 0
  fi

  if command -v jq >/dev/null 2>&1; then
    if ! jq -e 'type == "object"' < "$file" >/dev/null 2>&1; then
      ts="$(date +%Y%m%dT%H%M%SZ 2>/dev/null || date +%s)"
      echo "[axedgb] Quarantining malformed $name: $file"
      mv "$file" "$file.bad.$ts" 2>/dev/null || rm -f "$file" || true
    fi
  fi
}

global_conf_value() {
  key="$1"
  [ -f /data/digibyte.conf ] || return 0
  awk -F= -v wanted="$key" '
    /^[[:space:]]*\[/ { exit }
    /^[[:space:]]*#/ { next }
    {
      k=$1
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", k)
      if (k == wanted) {
        sub(/^[^=]*=/, "")
        gsub(/^[[:space:]]+|[[:space:]]+$/, "")
        print
        exit
      }
    }
  ' /data/digibyte.conf
}

if [ "$(id -u)" = "0" ]; then
  mkdir -p /data || true
  chown 1000:1000 /data 2>/dev/null || true
  chmod 755 /data 2>/dev/null || true
  [ -f /data/digibyte.conf ] && chown 1000:1000 /data/digibyte.conf 2>/dev/null || true
  [ -f /data/.dbcache_mb ] && chown 1000:1000 /data/.dbcache_mb 2>/dev/null || true
  [ -f /data/settings.json ] && chown 1000:1000 /data/settings.json 2>/dev/null || true
fi

heal_node_json /data/settings.json "DigiByte settings file"

extra=""

prune="$(global_conf_value prune)"
case "$prune" in
  ""|*[!0-9]*) prune="0" ;;
esac
if [ "$prune" -gt 0 ]; then
  txindex="0"
  echo "[axedgb] Managed transaction index: disabled for pruned mode"
else
  txindex="1"
  echo "[axedgb] Managed transaction index: enabled for DigiDollar archival mode"
fi
extra="$extra -txindex=$txindex"

# The supervisor selects the cache against the node's cgroup/host capacity,
# measures the actual Core process and preserves memory pauses across restarts.
exec python3 /usr/local/lib/axedgb/core_supervisor.py digibyted -datadir=/data -printtoconsole $extra
