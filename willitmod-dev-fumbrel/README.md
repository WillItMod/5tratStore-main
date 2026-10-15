This MAIN package is for **Umbrel 1.7 and 2.0 only**. It is excluded from 5tratumOS.

Source, build scripts and tests referenced below are maintained in the [DEV repository](https://github.com/WillItMod/5tratStore-dev/tree/8c90bd4007cf9720afb72d594e033873ec014e80). The published image and inherited interface are unchanged.

# Fumbrel — Fuck Up on Umbrel

DEV-only recovery for installed WillItMod apps on Umbrel 1.x and 2.0.

## Use

1. Install **Fumbrel** from the WillItMod DEV store and open it through Umbrel.
2. Enter this Umbrel's SSH username (normally `umbrel`) and password. The account
   must be able to use `sudo`. SSH must be enabled. A separate sudo password is
   supported if the account uses one.
3. Review the installed-app scan and select the applications to recover.
4. Choose **Repair selected** to retain the installed version, or
   **Repair & update selected** to reapply the package bundled with Fumbrel.
   This also works when Umbrel's update preparation is broken or the versions
   already match. MAIN installations may receive DEV versions.
5. Leave “Start apps after recovery” unchecked to keep them stopped, or check it
   to start them through Umbrel after applying the recipe. Node startup is not
   a full sync or mining acceptance test.
6. Download the redacted report if help is needed, then disconnect. Stop Fumbrel
   when finished with recovery.

The review dialog shows the exact installed and target versions. This release
bundles reviewed snapshots; it does **not** fetch arbitrary latest packages.
Higher installed versions cannot be downgraded, including prerelease revisions
such as `4.0.28-dev.1` compared with `4.0.28-dev`. Numeric components (including
historical four-part versions) compare first, then SemVer prerelease identifiers;
a stable release is newer than its prereleases, and build metadata is ignored.
Unrecognized versions require manual review. MAIN IDs and their data
directories are retained, including `willitmod-btc` when using the DEV BTC
package. The MAIN store may continue advertising its older version until that
store is promoted. Fumbrel does not change store subscriptions.

## What it repairs

- Known legacy `exports.sh` auth lookups that abort start, stop, logs and update
  when the old auth container is absent. The fixed file is applied **before**
  stopping the app, breaking the update-preparation deadlock.
- Dashboard hostnames needed by the Umbrel 2 gateway.
- FracAttack's duplicate dashboard port binding.
- PowPow's Litecoin/Dogecoin process UID, matching the existing data owner.

Repair preserves image versions and other Compose settings. Unrecognized custom
exports are reported for review; an explicit package update replaces recipe
metadata with the reviewed package. Updates are serialized and stop on the first
failure. Fumbrel only manages its allowlisted installed WillItMod app IDs, never
third-party apps or itself. It does not fix processor instruction incompatibility,
chain corruption, unavailable storage, or every possible Umbrel failure.

## Recovery mechanics and data boundaries

Each operation first saves the old manifest, Compose, root templates, exports,
torrc and hooks, including modes/ownership and absent-file markers. The backup is
written below Fumbrel's host app directory at `data/backups/<id>/index.json`, with
root-only access. It can contain existing recipe secrets and is never served by
the web UI. Reports contain selected status fields only.

The engine repairs installed exports, uses `umbreld client apps.stop.mutate`,
checks for remaining containers, applies metadata atomically one file at a time,
and optionally calls `apps.start.mutate`. The host checkpoint records partial
operations so a failure does not silently appear successful. A stale legacy
`app_proxy` container can be stopped and removed only when its Compose project
label matches the selected app; volumes are never removed. Remaining node
containers block package replacement.

Fumbrel does not write `data/`, wallets, `.env` or `settings.yml` in the recovered
app. Normal Umbrel lifecycle actions update their own state, and normal app
startup can initialize or migrate its data. **Recipe backups are not data backups.**
Restore requires a stopped app, first backs up its current recipe, restores the
saved metadata, and leaves it stopped. It does not undo a node database migration;
review binary/data compatibility before restarting an older restored recipe.

PowPow's bundled `0.2.37-dev.3` recipe requires the two reviewed static SQL seeds
at `data/postgres-init/2-schema.sql` and `data/postgres-init/3-multi-pool-partition.sql`.
Fumbrel records only their expected hashes, and verifies the existing regular
files through a canonical local app-data path before creating a backup, stopping
the app or changing metadata. Missing, changed, linked or redirected seed files
disable package recovery and direct you to the normal Umbrel store update, whose
reviewed seed hook creates missing packaged seeds. Changed or redirected existing
seeds require manual review. Fumbrel never copies or rewrites these files, reads a
wallet/configuration as a seed, or supports redirected seed paths. Metadata-only
compatibility repair remains available without these package-update prerequisites.

Do not concurrently manage the selected apps in Umbrel while recovery runs.
If an SSH/browser connection fails, scan again and check the saved checkpoint
before retrying. An already-running host operation may finish after the browser
disconnects. There is deliberately no automatic rollback to an old binary after
a new binary might have opened its data.

## Access model

The container is unprivileged, runs as UID 1000, has a read-only filesystem and
no Docker socket, private SSH key, or app-data mounts. Its only host bind is
`/etc/ssh/ssh_host_ed25519_key.pub`, read-only. Paramiko verifies this key before
authenticating to fixed destination `host.docker.internal:22`. It cannot accept
an arbitrary remote host or shell command from the UI.

User credentials are sent over that verified SSH connection and supplied to sudo
on stdin, never command arguments, logs, browser storage, or persistent files.
They live in the server's memory for the authenticated session and any operation
already in progress. Logout removes the session; a background reaper removes idle
sessions after 30 minutes. Stopping the container discards all sessions. Python
does not guarantee physical zeroization of freed memory.

The UI remains behind Umbrel authentication and separately requires a random
Fumbrel session token. It uses per-origin sessionStorage and a custom request
header, not shared host cookies. Cross-origin API requests are rejected, failed
logins are rate limited, and raw host command output is not returned to browsers.
Use the same trusted connection to Umbrel that you use for its administrator UI.

## Package sources and development

The catalog covers 14 app families / 18 known MAIN and DEV installation IDs.
Thirteen packages come from DEV commit
`81535f05ffc82e742b9aa32299c806de6b3b712c`; MAIN-only AxeSim comes from
`5c68fc868c62eaeff2bb3f930cbf0193ac3931cb`. Each original file has a SHA-256 digest.
MAIN identity substitutions and explicit gateway hostnames are applied after
verifying those digests. AxeBC2 uses its Umbrel Compose template, not its native
5tratumOS definition.

`scripts/fumbrel/build_catalog.py` reads immutable Git blobs and their executable
modes. Its explicit DEV input is the commit above. Release 0.1.3
refreshes only PowPow to `0.2.37-dev.4` from
`94801dcd23fda52be1eb193637a13d73243b04f1`; all other entries, including MAIN
AxeSim, keep their exact previous bytes, modes and source references. Its retained-catalog input is
`6f8ae3e7949433e64a144c9707432636bafb3e8a`: the complete existing AxeSim entry is reused without changing
its MAIN source, bytes or modes. It does not read an uncommitted MAIN checkout.
Fumbrel itself is excluded. A maintainer must review new source versions and
refresh the snapshots before releasing a new Fumbrel package. Recovery executes
Umbrel's normal stop/start actions, but does not run update-specific hooks; packages
requiring those hooks need separate engine support before inclusion.

Reproduce or verify the release bundle from a Git checkout containing the input
commits:

```sh
python scripts/fumbrel/build_catalog.py \
  --dev-ref 81535f05ffc82e742b9aa32299c806de6b3b712c \
  --powpow-ref 94801dcd23fda52be1eb193637a13d73243b04f1 \
  --retained-catalog-ref 6f8ae3e7949433e64a144c9707432636bafb3e8a \
  --release 0.1.3-dev --check
```

Run:

```sh
python -m pip install -r willitmod-dev-fumbrel/app/requirements.txt PyYAML
python -m unittest discover -s tests/fumbrel -v
python -m unittest discover -s tests -p test_umbrel_cross_version.py -v
```

The image workflow tests source and builds the two-file overlay on native AMD64
and ARM64 workers without publishing. The artifact verifier requires every actual
0.1.2 base layer, unchanged runtime configuration, and a new layer containing only
the reviewed engine and catalog with root ownership and mode 0644. UI, authentication,
server and dependency files remain inherited from the tested base. Publishing requires an explicit manual run on the reviewed candidate branch
`fix/fumbrel-legacy-pow-stop-20261015` or `main`, with `publish` enabled and a
required `source_sha` equal to the run commit. The application context must be
clean. This uses the new `0.1.3-dev` tag, allowing publication and digest pinning
before the recipe is merged into DEV. These
publication runs are serialized for that tag, and an authenticated GHCR lookup
must return HTTP 404 with `MANIFEST_UNKNOWN` before pushing. An existing tag or
an authentication, network, rate-limit or other inconclusive error blocks the run.
The workflow never interprets a generic image-inspection failure as absence.
A second native verification reads the actual published index returned by the
publisher, never its mutable tag. Full receipts are written to logs and the job
summary before an optional artifact upload. The installed recipe pins published `0.1.3-dev` to immutable index
`sha256:06cc15c514acd9bec8ca3d3af70f6ba9e7fc369441a726ab9d84e87756b8c444`.
`release-records/fumbrel-0.1.3-dev-image.json` binds that index and both native
configurations to reviewed source `6648c00297b0953d9867ca338fbd81f0655a3591`.
`release-records/fumbrel-0.1.2-dev-image.json` binds its historical 0.1.2 index and both native
platform configurations to source commit `f666e677138aebe06a319459d8da62c4c02a4bea`.
Native artifact verification does not establish ordinary Umbrel update or recovery
acceptance; those platform receipts remain separate. The 0.1.3 candidate Dockerfile
inherits that tested `0.1.2-dev` index and adds only engine.py and catalog.json.
The recipe and manifest advance after actual native post-publication and
anonymous immutable artifact verification. Ordinary Umbrel running/recovery
acceptance remains separate; publishing does not establish those outcomes. Live acceptance results are
recorded separately in `ACCEPTANCE.md`; that file describes `0.1.0-dev` only.
Building ARM does not establish Raspberry Pi hardware recovery.


Selected legacy `willitmod-dev-ppc` nodes with less than the bundled two-minute
stop grace receive one preparatory standard Docker stop with an infinite grace.
The installed source, exact container/project/service, resolved image and process
generation must match before recovery continues. Fumbrel observes this for at
most 150 seconds; an unverified or still-pending shutdown stops recovery for
manual inspection without a forced kill or package replacement. Current nodes
with adequate grace and other app families use their ordinary lifecycle path.
The original build-only PPC recipe shape is recognized; custom build/image or
stop policies require manual review.

Selected historical PowPow Litecoin and Dogecoin containers with the exact known
images and ten-second stop policy receive one preparatory TERM-only Docker stop
with infinite grace before the normal Umbrel stop. Both nodes must be admitted
before either signal. The observer is bounded to 960 seconds; a pending, dirty,
changed-generation or unknown shutdown stops recovery for review without force
or recipe replacement. Existing 930-second nodes require no preparatory stop.
An exact Created/never-started node is distinguished from a cleanly stopped node.
Known Docker 29 immutable-index identities also require the exact platform rootfs
from the admitted configuration; arbitrary images/architecture/layers are refused.
Full PowPow updates require the bundled 930-second SIGTERM policy before any
backup, lifecycle change or recipe write, so recovery cannot reinstall the old
ten-second policy. Only recipe metadata changes; wallet, database and user-data
files remain outside Fumbrel's write scope.
