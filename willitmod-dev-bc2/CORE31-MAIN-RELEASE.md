# AxeBC2 Core 31 MAIN release gates

The MAIN recipe maps its preserved store ID `willitmod-dev-bc2` to canonical 5tratumOS app ID
`axebc2`. Its preserved data path is `/var/lib/5tratumos/apps/axebc2`, matching
the `app_id` in `.5tratumos-rollback-policy.json`.

Every host bind uses `create_host_path: false`. The recipe contains the empty
runtime directories that 5tratumOS stages before Compose validation, so Docker
must not silently create a misspelled or missing source path.

The digest-pinned generic Alpine init container installs `jq` and
`gettext-envsubst` from Alpine 3.22 repositories at startup. This remains a
network-availability dependency, but an install failure occurs before any
persistent app-data or node-data mutation and prevents Core from starting. A
future dedicated, independently built and digest-pinned init image could remove
that availability dependency; it is not introduced in this consensus release.

The committed Compose file deliberately retains these non-runnable sentinels:

- `CORE31_PROMOTED_DIGEST_REQUIRED`
- `APP_PROMOTED_DIGEST_REQUIRED`

CI treats this as the strict `prefinalization` phase. It accepts exactly all
three expected sentinel occurrences. Once finalization is committed, CI
switches to `finalized` and requires one immutable application sha256 pin and
two identical immutable Core sha256 pins. A partial or mixed state is rejected.

They must be replaced with the exact verified multi-architecture candidate
digests. After substitution, the merged platform Compose must pass validation,
all images must pull anonymously by digest, init must complete successfully on
5tratumOS 0.7.12+, and the exact promoted images must already have passed DEV
acceptance before this MAIN recipe is released.

The DEV evidence must name the published DEV-only 5tratumOS `v0.7.12-dev`
bundle and its exact SHA-256,
`11a35e68ab169eb0446485992a57b33fae018a92020b7d86bbf9a005571377af`.
MAIN finalization rejects any other bundle digest, including a different bundle
published under the same displayed version.

Run `scripts/finalize-axebc2-0.1.10-main.sh` with the promoted application
index digest, promoted Core index digest and a completed DEV acceptance JSON
based on `DEV-ACCEPTANCE-EVIDENCE.example.json`. The finalizer fails before
editing Compose unless the evidence identifies the exact DEV-tested Core RC
`31.1.0-rc.cdf44542dde2`, full Core source revision
`cdf44542dde255648008249d187fafc15f3a2f09`, candidate workflow run
`33675068951`, and both exact tested digests.
The application evidence must likewise identify the exact tested candidate
`ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.10-candidate.6e4ef58218e8` and its
full source revision; MAIN independently resolves the promoted stable app tag
to that same digest.
Free-form checklists are not accepted. The DEV evidence records typed observed
values for Core version and synchronization, valid migration marker state, the
official height-57,752 checkpoint, minimum chainwork, matching node/explorer
height and hash, at least three outbound Core 31 peers, verifychain level 4,
payout configuration/preservation booleans, pool/Stratum, UI privacy, disabled telemetry, rejected app
rollback and rejected OS rollback, together with node identity and timestamps.
Both stable GHCR tags must then resolve anonymously to the tested digests,
including stable Core `31.1.0` resolving to the exact DEV-tested RC digest.
Both indexes must advertise linux/amd64 and linux/arm64, and both architectures
must pull anonymously. The finalizer then
replaces all sentinels atomically and verifies that the Core service and
`BTC2D_IMAGE` use the identical digest.

The store validator exercises a pinned copy of the relevant 5tratumOS
materialization contract from platform commit `4f979cb9541622c1fdccdf43b8a885bbf845ba38`:
it consumes `app_proxy`, publishes the manifest port on the resolved app
service, removes the legacy shared network, and normalizes restart policies.
The platform currently exposes this logic only inside its mutating install and
update commands, so invoking the live implementation from isolated store CI
would require performing a stateful platform transaction. Final MAIN acceptance
therefore runs the real platform materializer and validates its generated
Compose file before containers are started.
