#!/bin/sh
set -eu

echo "[axebtc] bitcoind entrypoint starting"

if ! command -v bitcoind >/dev/null 2>&1; then
  echo "[axebtc] ERROR: bitcoind not found in PATH"
  exit 127
fi

extra=""
if [ -f /data/.reindex-chainstate ]; then
  echo "[axebtc] Reindex requested (chainstate)."
  rm -f /data/.reindex-chainstate || true
  extra="-reindex-chainstate"
fi

dbcache="${BTC_DBCACHE_MB:-}"
if [ -z "${dbcache}" ]; then
  mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  mem_mb="$((mem_kb / 1024))"
  # Conservative: ~1/8 of RAM, clamped.
  dbcache="$((mem_mb / 8))"
  if [ "$dbcache" -lt 256 ]; then dbcache=256; fi
  if [ "$dbcache" -gt 2048 ]; then dbcache=2048; fi
fi

echo "[axebtc] Using dbcache=${dbcache}MB"
echo "[axebtc] Exec: bitcoind -datadir=/data -printtoconsole -dbcache=${dbcache} $extra"
exec bitcoind -datadir=/data -printtoconsole -dbcache="${dbcache}" $extra
