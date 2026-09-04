# AxeBC2 Core 31 MAIN release record

The MAIN recipe maps its preserved store ID `willitmod-dev-bc2` to canonical
5tratumOS app ID `axebc2`. Its preserved data path is
`/var/lib/5tratumos/apps/axebc2`, matching the `app_id` in
`.5tratumos-rollback-policy.json`.

Every host bind uses `create_host_path: false`. The recipe contains the empty
runtime directories that 5tratumOS stages before Compose validation, so Docker
must not silently create a misspelled or missing source path.

The digest-pinned generic Alpine init container installs `jq` and
`gettext-envsubst` from Alpine 3.22 repositories at startup. This remains a
network-availability dependency, but an install failure occurs before any
persistent app-data or node-data mutation and prevents Core from starting. A
future dedicated, independently built and digest-pinned init image could remove
that availability dependency; it was not introduced in this consensus release.

## Finalized image set

The committed Compose file is finalized for AxeBC2 `0.1.10`. It contains no
release sentinel, one immutable application pin and two identical immutable
Core pins. CI validates it in the strict `finalized` phase and rejects partial,
mixed or mutable image state.

The released image set is:

- init: `alpine:3.22.1@sha256:4bcff63911fcb4448bd4fdacec207030997caf25e9bea4045fa6c8c44de311d1`;
- app: `ghcr.io/willitmod/axebc2-app:0.1.10@sha256:b7ba2df2f48389d145ad18a927b099f32b5aa7708a0ea617a1b04e25c8e7f961`;
- BitcoinII Core: `ghcr.io/willitmod/bitcoinii-core:31.1.0@sha256:8875917ece57668fe9925d40a256ce8d429a3071511bb555d4ace1fa4370afc6`;
- CKPool: `ghcr.io/willitmod/docker-ckpool-solo:590fb2a@sha256:8a9a7f10c8138d0f55533132ee7710a06715a42a49f75efb39be3350ada4fa6e`.

The Core service and `BTC2D_IMAGE` use the same Core reference. The CKPool
service and `CKPOOL_IMAGE` likewise use the same unchanged CKPool reference.
The app and Core indexes both advertise linux/amd64 and linux/arm64 and are
anonymously pullable by their exact digests.

## Source and promotion provenance

The stable app tag is a no-rebuild promotion of the DEV-tested candidate
`ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.10-candidate.6e4ef58218e8`.
Both tags resolve to app digest
`sha256:b7ba2df2f48389d145ad18a927b099f32b5aa7708a0ea617a1b04e25c8e7f961`.
The application source revision is
`6e4ef58218e8cd5a4d1113196f9872a7f501f52e`; promotion workflow run
`33881273637` completed successfully without rebuilding the candidate.

The stable Core tag is a no-rebuild promotion of the DEV-tested RC
`ghcr.io/willitmod/bitcoinii-core:31.1.0-rc.cdf44542dde2`. Both tags resolve to
Core digest
`sha256:8875917ece57668fe9925d40a256ce8d429a3071511bb555d4ace1fa4370afc6`.
The image pipeline revision is
`cdf44542dde255648008249d187fafc15f3a2f09`; candidate workflow run
`33675068951` and promotion workflow run `33881286149` completed successfully.
The image compiles official BitcoinII Core `v31.1.0` at upstream commit
`8daaf7b12e71d3646eed787f040bf2899a69dc1c` without patching ShockWave.

## Accepted DEV evidence

The exact candidate pair passed live DEV acceptance on `10.10.10.235` at
`2026-09-04T13:57:46Z` using the published 5tratumOS `v0.7.12-dev` bundle with
SHA-256
`11a35e68ab169eb0446485992a57b33fae018a92020b7d86bbf9a005571377af`.
The structured evidence is recorded in the DEV store at
[`DEV-ACCEPTANCE-EVIDENCE.json`](https://github.com/WillItMod/5tratStore-dev/blob/main/willitmod-dev-bc2/DEV-ACCEPTANCE-EVIDENCE.json).

The mandatory Core 31 full reindex completed and did not repeat after a full
app restart. Core reported version `310100`, passed `verifychain` level 4 and
matched the official BitcoinII explorer at height 58,433 and block hash
`0000000000000001077a5ea39eefb3a44e5d88357c723f56484840a7f89c5554`.
Five outbound Core 31 peers and zero competing valid post-checkpoint tips were
recorded. The payout configuration was preserved, and Stratum, UI privacy,
disabled telemetry, unpublished P2P, disabled NAT-PMP, app rollback rejection
and OS rollback rejection checks all passed.

## Migration and validation contract

5tratumOS `0.7.12` or newer is required. Existing node data receives a guarded
one-time full reindex. Persistent migration markers allow an interrupted reindex
to resume and prevent a completed reindex from being requested again. The
rollback policy prevents returning the migrated data to an incompatible older
app, Core or OS version, while the saved payout and unrelated persistent state
remain in place.

The store validator exercises a pinned copy of the relevant 5tratumOS
materialization contract from platform commit
`4f979cb9541622c1fdccdf43b8a885bbf845ba38`. It consumes `app_proxy`, publishes
the manifest port on the resolved app service, removes the legacy shared
network, normalizes restart policies and rejects implicit host-path creation.
The finalized MAIN checks also bind promotion to the exact accepted DEV
evidence and immutable image digests. The retained
`scripts/finalize-axebc2-0.1.10-main.sh` documents and tests the reproducible
finalization procedure; the current release requires no further sentinel
replacement or image promotion.
