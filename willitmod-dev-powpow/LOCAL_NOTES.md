# PowPow MAIN Release Candidate Notes

This package is now wired to the real PowPow stack.

## Current status

- Uses GHCR images published from `WillItMod/PowPow_Build`
- Package version: `0.2.32`
- App image: `ghcr.io/willitmod/powpow-app:0.2.31`
- Service images:
  - `ghcr.io/willitmod/powpow-litecoin:0.2.32` (Litecoin Core `0.21.5.8`)
  - `ghcr.io/willitmod/powpow-dogecoin:0.2.26`
  - `ghcr.io/willitmod/powpow-pool:0.2.31`
- Acceptance testing for this update passed on `10.10.10.235` on `2026-09-16`.
- Miner endpoint hint is injected through packaging with `NETWORK_HOST_HINT: "${NETWORK_IP}"`
- App version display is set from `APP_VERSION`
- Litecoin Core is upgraded from `0.21.4` to `0.21.5.8` using official AMD64 and ARM64 release archives with pinned SHA-256 checksums.
- This release updates only the Litecoin node image. The app, pool, and Dogecoin images retain their existing pins.
- Litecoin chain data remains in the existing persistent `/data/litecoin` directory.

## Release validation

- Both official release archives passed SHA-256 verification during the image builds. The multiarch Litecoin image contains AMD64 and ARM64 variants with manifest digest `sha256:dc271eec167e4c33fdefea6524cf40d16d52ec56b94f6dfb0f052d21ea81b6ba`.
- Native ARM64 validation passed node startup, RPC, wallet creation, and generation of one regtest block.
- On `2026-09-16`, the AMD64 host reported `/LitecoinCore:0.21.5.8/`, fully synced with no warnings and 10 peers. Its mainnet tip advanced from `3178923` to `3178926`.
- Dogecoin was synced at `6376737`; the auxiliary chain recovered to active and the pool API was healthy. Stratum subscribe, authorize, and a nine-field mining notification passed after auxiliary-chain recovery.
- A candidate block constructed by PowPow, including SegWit and MWEB data, passed the node's nonbroadcast proposal check with a `null` result.
- All three source tests passed, and both Compose recipes validated with a stand-in for the platform-injected `app_proxy` service. A full cold backup was verified before the live upgrade.
- Upstream release: https://github.com/litecoin-project/litecoin/releases/tag/v0.21.5.8

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
tested DEV recipe. The AMD64 and ARM64 image checks and live acceptance passed
on `2026-09-16`; the MAIN package uses the same tested Litecoin image manifest.
