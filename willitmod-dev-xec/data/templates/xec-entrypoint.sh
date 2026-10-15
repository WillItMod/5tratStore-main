#!/bin/sh
set -eu

echo "[axexec] XEC node entrypoint starting"

if ! command -v bitcoind >/dev/null 2>&1; then
  echo "[axexec] ERROR: bitcoind not found in PATH"
  exit 127
fi

extra=""
if [ -f /data/.reindex-chainstate ]; then
  echo "[axexec] Reindex requested (chainstate)."
  rm -f /data/.reindex-chainstate || true
  extra="-reindex-chainstate"
fi

echo "[axexec] Exec: bitcoind -datadir=/data -printtoconsole $extra"
exec bitcoind -datadir=/data -printtoconsole $extra

