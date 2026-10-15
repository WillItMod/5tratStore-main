#!/bin/sh
set -eu

echo "[fracattack] fractald entrypoint starting"

if ! command -v bitcoind >/dev/null 2>&1; then
  echo "[fracattack] ERROR: bitcoind not found in PATH"
  exit 127
fi

extra=""
if [ -f /data/btc_wipe_request ]; then
  echo "[fracattack] Full Fractal chain wipe requested."
  rm -rf /data/blocks /data/chainstate /data/indexes
  rm -f /data/.lock /data/bitcoind.pid /data/mempool.dat /data/fee_estimates.dat /data/peers.dat
  rm -f /data/.reindex-chainstate /data/btc_wipe_request
  echo "[fracattack] Fractal chain data removed; starting fresh sync."
fi

if [ -f /data/.reindex-chainstate ]; then
  echo "[fracattack] Reindex requested (chainstate)."
  rm -f /data/.reindex-chainstate || true
  extra="-reindex-chainstate"
fi

dbcache="${BTC_DBCACHE_MB:-}"
if [ -z "${dbcache}" ]; then
  mem_kb="$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  avail_kb="$(awk '/MemAvailable/ {print $2}' /proc/meminfo 2>/dev/null || echo 0)"
  mem_mb="$((mem_kb / 1024))"
  avail_mb="$((avail_kb / 1024))"
  # Keep the default conservative because 5tratumOS nodes often run
  # several full nodes at once. BTC_DBCACHE_MB can still override this.
  if [ "$mem_mb" -ge 12000 ]; then
    dbcache=1536
  elif [ "$mem_mb" -ge 7000 ]; then
    dbcache=1024
  else
    dbcache=512
  fi

  if [ "$avail_mb" -gt 0 ] && [ "$avail_mb" -lt 4096 ] && [ "$dbcache" -gt 1024 ]; then
    dbcache=1024
  fi
  if [ "$avail_mb" -gt 0 ] && [ "$avail_mb" -lt 2048 ] && [ "$dbcache" -gt 512 ]; then
    dbcache=512
  fi

  if [ "$dbcache" -lt 256 ]; then dbcache=256; fi
fi

echo "[fracattack] Using dbcache=${dbcache}MB"
echo "[fracattack] Exec: bitcoind -datadir=/data -printtoconsole -dbcache=${dbcache} $extra"
exec bitcoind -datadir=/data -printtoconsole -dbcache="${dbcache}" $extra
