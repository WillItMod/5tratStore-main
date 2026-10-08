#!/usr/bin/env bash
set -euo pipefail

# The platform auth server signs tokens with JWT_SECRET.
# In some update/restart flows (especially manual SSH updates), JWT_SECRET may not
# be exported into the app environment, which causes app_proxy to reject logins.
#
# If it's missing, read it from the running `auth` container so app_proxy can
# validate platform JWTs reliably.

if [[ -z "${JWT_SECRET:-}" ]] && command -v docker >/dev/null 2>&1; then
  jwt_secret_from_auth=""

  for auth_container in auth 5tratumos-auth 5tratumos_auth; do
    jwt_secret_from_auth="$(
      docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${auth_container}" 2>/dev/null \
        | sed -n 's/^JWT_SECRET=//p' \
        | tail -n 1
    )"
    if [[ -n "${jwt_secret_from_auth:-}" ]]; then
      break
    fi
  done

  if [[ -n "${jwt_secret_from_auth:-}" ]]; then
    export JWT_SECRET="${jwt_secret_from_auth}"
  fi
fi

# Last-resort fallback (keeps proxy from crashing, but won't match platform auth tokens).
export JWT_SECRET="${JWT_SECRET:-DEADBEEF}"
