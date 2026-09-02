# AxeBC2 Core 31 DEV release gates

The DEV recipe maps store ID `willitmod-dev-bc2` to canonical 5tratumOS app ID
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

- `CORE31_CANDIDATE_DIGEST_REQUIRED`
- `APP_CANDIDATE_DIGEST_REQUIRED`

They must be replaced with the exact verified multi-architecture candidate
digests. After substitution, the merged platform Compose must pass validation,
all images must pull anonymously by digest, init must complete successfully on
5tratumOS 0.7.11+, and the resulting installation must be tested on DEV before
any production promotion.
