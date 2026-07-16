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
if [ -f /data/.reindex-chainstate ]; then
  echo "[axedgb] Reindex requested (chainstate)."
  rm -f /data/.reindex-chainstate || true
  extra="-reindex-chainstate"
fi

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

dbcache="${DGB_DBCACHE_MB:-}"
if [ -z "$dbcache" ] && [ -f /data/.dbcache_mb ]; then
  raw="$(cat /data/.dbcache_mb 2>/dev/null | tr -d ' \t\r\n' || true)"
  case "$raw" in
    ""|auto|AUTO)
      dbcache=""
      ;;
    *[!0-9]*)
      echo "[axedgb] WARNING: invalid /data/.dbcache_mb value, ignoring"
      dbcache=""
      ;;
    *)
      dbcache="$raw"
      ;;
  esac
fi

if [ -z "$dbcache" ] && [ -r /proc/meminfo ]; then
  mem_kb="$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
  avail_kb="$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null || true)"
  if [ -n "$mem_kb" ]; then
    mem_mb="$((mem_kb / 1024))"
    if [ "$mem_mb" -ge 15360 ]; then
      dbcache="2048"
    elif [ "$mem_mb" -ge 7680 ]; then
      dbcache="1024"
    else
      dbcache="512"
    fi
  fi
  if [ -n "$avail_kb" ]; then
    avail_mb="$((avail_kb / 1024))"
    if [ "$avail_mb" -lt 2048 ]; then
      dbcache="512"
    elif [ "$avail_mb" -lt 4096 ] && [ "${dbcache:-0}" -gt 1024 ]; then
      dbcache="1024"
    fi
  fi
fi

if [ -n "$dbcache" ] && echo "$dbcache" | grep -Eq '^[0-9]+$'; then
  if [ "$dbcache" -lt 512 ]; then
    echo "[axedgb] WARNING: dbcache=$dbcache too low; clamping to 512MB minimum"
    dbcache="512"
  fi
fi

if [ -n "$dbcache" ]; then
  extra="$extra -dbcache=$dbcache"
fi

echo "[axedgb] Exec: digibyted -datadir=/data -printtoconsole $extra"
exec digibyted -datadir=/data -printtoconsole $extra
