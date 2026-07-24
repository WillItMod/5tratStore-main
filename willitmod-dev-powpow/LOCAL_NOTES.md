# PowPow MAIN Release Candidate Notes

This package is now wired to the real PowPow stack.

## Current status

- Uses GHCR images published from `WillItMod/PowPow_Build`
- App image: `ghcr.io/willitmod/powpow-app:0.2.31`
- Service images:
  - `ghcr.io/willitmod/powpow-litecoin:0.2.26`
  - `ghcr.io/willitmod/powpow-dogecoin:0.2.26`
  - `ghcr.io/willitmod/powpow-pool:0.2.31`
- Runtime UI behavior was smoke-tested on the maintained x86-64 5tratumOS test host.
- Miner endpoint hint is injected through packaging with `NETWORK_HOST_HINT: "${NETWORK_IP}"`
- App version display is set from `APP_VERSION`
- Difficulty presets are labelled and tuned around Scrypt GH/s miner hashrates. This release updates the app and pool images; the existing LTC/DOGE node images remain pinned and do not need to be replaced.

## Packaging notes

- The stale DigiByte/Miningcore package content is ignored via `.gitignore`
- PostgreSQL schema init files are copied from `PowPow_Build/postgres/init`
- The pool image also runs that bootstrap before starting dogepool, so schema recovery is not dependent on a separate bootstrap container
- `docker-compose.yml` now represents the PowPow-native stack:
  - `app`
  - `litecoin`
  - `dogecoin`
  - `pool`
  - `postgres`

## Deployment note

This package is the MAIN Community Store release candidate promoted from the
tested DEV recipe. Publish it only after the AMD64 and ARM64 image checks and
the live acceptance pass on the designated 5tratumOS test host.
