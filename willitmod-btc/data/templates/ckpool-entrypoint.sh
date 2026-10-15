#!/bin/sh
set -eu

CFG="/config/ckpool.conf"
ARGS_FILE="/config/ckpool.args"

rm -f /tmp/ckpool/*.pid 2>/dev/null || true

ckpool_bin=""
if command -v ckpool >/dev/null 2>&1; then
  ckpool_bin="ckpool"
elif [ -x /bin/ckpool ]; then
  ckpool_bin="/bin/ckpool"
elif [ -x /usr/bin/ckpool ]; then
  ckpool_bin="/usr/bin/ckpool"
else
  echo "[axebtc] ERROR: ckpool binary not found in image" >&2
  exit 1
fi

checksum() {
  if [ ! -f "$CFG" ]; then
    echo ""
    return 0
  fi
  cksum "$CFG" 2>/dev/null | awk '{print $1 ":" $2}'
}

start_ckpool() {
  if [ ! -f "$CFG" ]; then
    return 0
  fi
  ARGS="$(cat "$ARGS_FILE" 2>/dev/null || true)"
  # shellcheck disable=SC2086
  "$ckpool_bin" -k -L -c "$CFG" $ARGS &
  pid="$!"
}

last=""
pid=""
poll_pid=""

stop_ckpool() {
  if [ -n "$pid" ]; then
    kill -TERM "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    pid=""
  fi
}

terminate_pool() {
  trap '' TERM INT
  if [ -n "$poll_pid" ]; then
    kill -TERM "$poll_pid" 2>/dev/null || true
    wait "$poll_pid" 2>/dev/null || true
    poll_pid=""
  fi
  stop_ckpool
  exit 0
}

trap terminate_pool TERM INT

while true; do
  sum="$(checksum)"

  if [ "$sum" != "$last" ]; then
    last="$sum"
    stop_ckpool
    start_ckpool
    if [ -n "${pid:-}" ]; then
      echo "[axebtc] ckpool started (pid ${pid})"
    else
      echo "[axebtc] waiting for ckpool.conf..."
    fi
  fi

  if [ -n "${pid:-}" ] && ! kill -0 "$pid" 2>/dev/null; then
    wait "$pid" 2>/dev/null || true
    pid=""
  fi

  sleep 2 &
  poll_pid="$!"
  wait "$poll_pid" 2>/dev/null || true
  poll_pid=""
done
