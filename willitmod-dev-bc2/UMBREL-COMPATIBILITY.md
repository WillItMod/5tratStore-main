# Umbrel packaging

Umbrel renders the top-level `docker-compose.yml.template` before installation
and every start. It refreshes top-level templates and `hooks/` on upgrades.
The generated template uses `hooks/umbrel-init` and `hooks/umbrel-ckpool` as
container entrypoints, so an older initializer preserved under `data/` cannot
block an upgraded Umbrel installation.

5tratumOS consumes `docker-compose.yml` directly. The native recipe changes only the app image pin;
`data/init/init.sh` and the minimum OS check remain unchanged. The
Umbrel template needs no 5tratumOS host file and uses the same pinned app,
Core 31, CKPool, and initialization images.

The generated Umbrel initializer retains migration-marker validation, reindex
requirements, payout preservation, data ownership repair, and the persistent
application policy. The `.5tratumos-rollback-policy.json` filename is retained
because the app consumes it and it protects a later move to 5tratumOS.
Umbrel does not provide the 5tratumOS host rollback-policy enforcement API;
this package does not claim to add an Umbrel OS downgrade guard.

Regenerate after changing the shared recipe or initializer:

```sh
python3 scripts/build-axebc2-umbrel.py
python3 scripts/build-axebc2-umbrel.py --check
python3 scripts/validate-axebc2-core31-main.py --phase finalized
```

Generated entrypoints live in `hooks/` because it is an upstream update
whitelist directory. They are non-executable on the host and are invoked
explicitly by `/bin/sh` inside their pinned containers. Shell programs must
not be embedded in the Compose template: Umbrel's `envsubst` would consume
their local shell variables before container startup.

Runtime validation target: a fresh umbrelOS 1.7.4 amd64 VM. The existing Core 31
acceptance record describes the original 0.1.11 5tratumOS recipe; it is not evidence
that the new Umbrel path has passed runtime testing.

Upstream contract:
https://github.com/getumbrel/umbrel/blob/1.7.4/packages/umbreld/source/modules/apps/legacy-compat/app-script

## Initial packaging candidate 0.1.12 (superseded)

The initial packaging candidate used package version 0.1.12 with the
0.1.11 application image. Release 0.1.13 supersedes that candidate and aligns
the package and application versions; the node image is unchanged.

On 6 September 2026, both candidates passed the native installer and repeated
container initialization on 5tratumOS v0.7.12-dev at 10.10.10.235, using
isolated installation roots and disposable data. The original required mount
was also tested against an absent JSON source and reproduced the Docker bind
failure. Both generated Umbrel initializers passed without a host JSON bind.

The isolated DEV node, pool, and app started; the app page and node API
responded, including after restarting the app. That smoke test used localhost
access, resource limits, and no blockchain peer connections. It does not
establish synchronized mining or Umbrel dashboard authentication.

Automated validation: 33 DEV tests and 40 MAIN tests passed. Real Umbrel
installation, authenticated opening, and upgrade remain pending VM access.

## Aligned release 0.1.13

Application and package versions now align: 0.1.13-dev in DEV and 0.1.13 in
MAIN. Both use the same tested application digest with channel-specific image
tags. Core 31, CKPool, the native initializer, and persistent data paths retain
their accepted configuration. Historical 0.1.11/0.1.12 observations above remain
bound to those releases. See RELEASE-0.1.13-EVIDENCE.json for this release.
