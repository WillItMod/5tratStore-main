#!/usr/bin/env bash
set -euo pipefail

# The platform auth-server signs tokens with JWT_SECRET (not UMBREL_AUTH_SECRET).
# In legacy-compat flows, JWT_SECRET is not consistently passed through to apps.
# If it's missing, read it from the running `auth` container so app_proxy can
# validate auth JWTs reliably.

if [[ -z "${JWT_SECRET:-}" ]] && command -v docker >/dev/null 2>&1; then
  jwt_secret_from_auth="$(
    docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' auth 2>/dev/null \
      | sed -n 's/^JWT_SECRET=//p' \
      | tail -n 1
  )"

  if [[ -n "${jwt_secret_from_auth:-}" ]]; then
    export JWT_SECRET="${jwt_secret_from_auth}"
  fi
fi

# Last-resort fallback (keeps proxy from crashing, but won't match auth tokens).
export JWT_SECRET="${JWT_SECRET:-DEADBEEF}"
