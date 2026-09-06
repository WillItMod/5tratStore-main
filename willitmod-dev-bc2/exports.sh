#!/usr/bin/env bash

# Umbrel's auth-server signs tokens with JWT_SECRET (not UMBREL_AUTH_SECRET).
# In some update/restart flows (especially manual SSH updates), JWT_SECRET may not
# be exported into the app environment, which causes app_proxy to reject logins.
#
# If it's missing, read it from a running legacy auth container so app_proxy can
# validate Umbrel JWTs reliably. This file is sourced by Umbrel, so it must not
# change the caller's shell options and every optional probe must tolerate a miss.

_axebc2_load_legacy_jwt_secret() {
  local auth_container jwt_secret_from_auth

  [[ -z "${JWT_SECRET:-}" ]] || return 0
  command -v docker >/dev/null 2>&1 || return 0
  for auth_container in auth umbrel-auth umbrel_auth; do
    jwt_secret_from_auth=""
    if jwt_secret_from_auth="$(
      docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${auth_container}" 2>/dev/null \
        | sed -n 's/^JWT_SECRET=//p' \
        | tail -n 1
    )" && [[ -n "${jwt_secret_from_auth}" ]]; then
      export JWT_SECRET="${jwt_secret_from_auth}"
      return 0
    fi
  done

  return 0
}

_axebc2_load_legacy_jwt_secret
unset -f _axebc2_load_legacy_jwt_secret

# Umbrel 2 implements the app gateway in umbreld and does not consume
# JWT_SECRET from app_proxy. Do not synthesize a credential when legacy auth is
# absent: only Umbrel's real secret can authenticate requests on older releases.
