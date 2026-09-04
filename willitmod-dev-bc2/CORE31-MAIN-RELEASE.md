# AxeBC2 0.1.11 / Core 31 MAIN promotion gates

The MAIN recipe maps its preserved store ID `willitmod-dev-bc2` to canonical
5tratumOS app ID `axebc2`. Its data remains at
`/var/lib/5tratumos/apps/axebc2`, matching the `app_id` in
`.5tratumos-rollback-policy.json`. The protected consensus rollback floor stays
at `0.1.10`; this application-only update must not repeat the completed Core 31
reindex.

Every host bind uses `create_host_path: false`. The recipe contains the runtime
directories staged before Compose validation, so Docker must not silently create
a misspelled or missing source path. The digest-pinned Alpine init container's
dependency installation still fails before persistent data mutation if its
repositories are unavailable.

## Finalized image set

The MAIN recipe is finalized with immutable application and Core digests. It has
no digest sentinel; CI rejects any partial, mixed, or unexpected image state.
Application promotion workflow run `33898645561` copied the exact DEV-tested
index to the stable tags without rebuilding it. The workflow's candidate-build
job was skipped as required.

The immutable release inputs are:

- init: `alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1`;
- app candidate: `ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.11-candidate.ecf6e2c8cfd0@sha256:23a7962e223da5549eba52697c6f4cfa16ab74cba935c68c48148a4c515302b4`;
- stable app: `ghcr.io/willitmod/axebc2-app:0.1.11@sha256:23a7962e223da5549eba52697c6f4cfa16ab74cba935c68c48148a4c515302b4`;
- BitcoinII Core: `ghcr.io/willitmod/bitcoinii-core:31.1.0@sha256:8875917ece57668fe9925d40a256ce8d429a3071511bb555d4ace1fa4370afc6`;
- CKPool: `ghcr.io/willitmod/docker-ckpool-solo:590fb2a@sha256:8a9a7f10c8138d0f55533132ee7710a06715a42a49f75efb39be3350ada4fa6e`.

The application candidate was built from source revision
`ecf6e2c8cfd0e42ea53d3cc146b18cd6d4c4b563` by workflow run `33895447789`.
The unchanged Core image was built from pipeline revision
`cdf44542dde255648008249d187fafc15f3a2f09`; candidate run `33675068951` and
promotion run `33881286149` completed successfully. It compiles official
BitcoinII Core `v31.1.0` at upstream commit
`8daaf7b12e71d3646eed787f040bf2899a69dc1c` without patching ShockWave.

The Core service and `BTC2D_IMAGE` retain the same exact Core reference. The
CKPool service and `CKPOOL_IMAGE` retain the same exact CKPool reference.

## Accepted DEV evidence

The exact 0.1.11 candidate completed a successful DEV update and acceptance run
on `10.10.10.235` at `2026-09-04T17:22:22Z`, using the pinned 5tratumOS
`v0.7.12-dev` bundle with SHA-256
`11a35e68ab169eb0446485992a57b33fae018a92020b7d86bbf9a005571377af`.
The evidence identifies tested DEV store revision
`249ab61506dc09c2151d39e2b210f5f18d75ff21` and its exact Compose SHA-256
`93ceba92069947f47d650a5fb32205836fe070d83707f36912a2e0e83beb1244`.
The prior Core 31 acceptance remains valid for the unchanged Core digest, but it
was supplemented by the new application and update-path checks.

The accepted run preserved chain data, migration markers, payout configuration,
pool data, privacy, telemetry and network exposure, and did not repeat the
reindex. Core `310100` reported height and headers `58,444`, chainwork
`00000000000000000000000000000000000000000000fb2888bffb8c3c655c9c`, and best
block hash `00000000000000001e6ee54b268e62f3f1306a04cdb8f08a30c712e3e1cc3996`.
The official explorer matched that exact height and hash, level-4 `verifychain`
passed, ten outbound Core 31 peers were observed, no competing valid tip was
present, and the non-submitting Stratum flow passed. The evidence also records:

- Core-accepted mainnet `1...`, `3...`, and `bc1...` payout families save;
- invalid, wrong-network, RPC-unavailable, and malformed RPC results do not
  mutate payout settings or history;
- old pending validation records resolve at the bounded recheck interval;
- MAIN/stable builds do not display the misleading payout banner;
- the targeted CKPool `/config` repair in the versioned Compose init command runs
  on every initializer start and makes atomic payout updates writable by uid/gid
  1000 on fresh and preserved installs, as confirmed by a live directory-write
  acceptance check;
- the separate conditional `/www` repair makes existing sharelog paths writable
  by uid/gid 1000 before the preserved, previously seeded init script runs,
  without rewriting a current config.

## Finalization completed

`scripts/finalize-axebc2-0.1.11-main.sh` completed against the exact accepted DEV
evidence and application digest. It verified that the stable application tag
resolved to the tested candidate digest, the retained stable Core tag resolved
to its fixed digest, both indexes exposed linux/amd64 and linux/arm64 and pulled
anonymously, and every required acceptance field passed. It then replaced only
the application sentinel atomically.

The store validator exercises the pinned 5tratumOS materialization contract from
platform commit `4f979cb9541622c1fdccdf43b8a885bbf845ba38`. It consumes
`app_proxy`, publishes the manifest port on the resolved app service, removes
the legacy shared network, normalizes restart policies, and rejects implicit
host-path creation.
