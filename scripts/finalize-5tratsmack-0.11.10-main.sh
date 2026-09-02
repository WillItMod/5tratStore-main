#!/usr/bin/env bash
set -Eeuo pipefail

if [[ "$#" -ne 3 ]]; then
  echo "usage: $0 SOURCE_REVISION APP_INDEX_DIGEST CKPOOL_INDEX_DIGEST" >&2
  exit 64
fi

source_revision="$1"
app_digest="$2"
ckpool_digest="$3"
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
compose="$repo_root/willitmod-dev-5tratsmack/docker-compose.yml"

[[ "$source_revision" =~ ^[0-9a-f]{40}$ ]]
[[ "$app_digest" =~ ^sha256:[0-9a-f]{64}$ ]]
[[ "$ckpool_digest" =~ ^sha256:[0-9a-f]{64}$ ]]

replace_once() {
  local needle="$1"
  local replacement="$2"
  local path="$3"
  local count tmp line
  count="$(grep -oF -- "$needle" "$path" | wc -l | tr -d ' ')"
  if [[ "$count" -lt 1 ]]; then
    echo "expected at least one $needle placeholder in $path, found $count" >&2
    exit 1
  fi
  tmp="$(mktemp "${path}.finalize.XXXXXX")"
  while IFS= read -r line || [[ -n "$line" ]]; do
    printf '%s\n' "${line//$needle/$replacement}"
  done <"$path" >"$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$path"
}

replace_once SOURCE_REVISION_REQUIRED "$source_revision" "$compose"
replace_once APP_INDEX_DIGEST_REQUIRED "$app_digest" "$compose"
replace_once CKPOOL_INDEX_DIGEST_REQUIRED "$ckpool_digest" "$compose"

if grep -F '_REQUIRED' "$compose"; then
  echo "unresolved release placeholder remains" >&2
  exit 1
fi
grep -Fx "    image: ghcr.io/willitmod/5tratsmack-app:0.11.10@${app_digest}" "$compose" >/dev/null
grep -Fx "    image: ghcr.io/willitmod/5tratsmack-ckpool:0.11.3@${ckpool_digest}" "$compose" >/dev/null
grep -Fx "      APP_IMAGE: ghcr.io/willitmod/5tratsmack-app:0.11.10@${app_digest}" "$compose" >/dev/null
grep -Fx "      APP_REVISION: ${source_revision}" "$compose" >/dev/null
grep -Fx "      BCH2_NODE_IMAGE: ghcr.io/willitmod/5tratsmack-core:0.11.2@sha256:7bf02513144c7a157965fb8e9ad5865f5e84fa679afa7cb61fc0a8e140a40070" "$compose" >/dev/null
grep -Fx "      CKPOOL_IMAGE: ghcr.io/willitmod/5tratsmack-ckpool:0.11.3@${ckpool_digest}" "$compose" >/dev/null
printf 'Prepared MAIN from source %s\napp=%s\nckpool=%s\n' "$source_revision" "$app_digest" "$ckpool_digest"
