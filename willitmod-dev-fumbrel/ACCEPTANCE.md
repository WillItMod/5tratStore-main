# Fumbrel 0.1.0-dev acceptance — 24 September 2026

## Results

| Check | Umbrel 1.7.4 | Umbrel 2.0.0 final |
| --- | --- | --- |
| Fresh Fumbrel installation | Pass | Pass |
| Anonymous gateway requires login | HTTP 302 | HTTP 302 |
| Authenticated Fumbrel UI | HTTP 200 | HTTP 200 |
| SSH to own host with pinned public key and sudo | Pass | Pass |
| Installed-app scan | 13 known apps found | 13 known apps found |
| Detect injected legacy BTC exports + missing dashboard hostname | Pass | Pass |
| Repair while retaining package version | Pass | Pass |
| All app-data file hashes unchanged during metadata-only repair | Pass | Pass |
| Restore recipe backup while stopped | Pass | Pass |
| Force-apply bundled BTC package, then normal Umbrel start | Pass | Pass |
| Authenticated recovered BTC dashboard | HTTP 200 | HTTP 200 |
| Final task apps stopped, auto-start disabled | Pass | Pass |

The recovery test deliberately restored the known old BTC exports file, removed
its dashboard hostname and set the older package version in a task-owned test
installation. Fumbrel repaired it, restored the broken recipe from its backup,
then successfully applied `0.7.82.10-dev` through the recovery UI's HTTP API and
started it. This is fault injection of retained legacy metadata, not a complete
1.7.4-to-2.0 OS upgrade or a test against an affected customer's actual machine.

Only task-owned test apps were selected for recovery. The pre-existing AxeBC2
reference on each VM was scanned but not updated, stopped or altered. Test apps
were stopped after their startup/authentication checks. The lab bounded shutdown
of its idle BTC test containers to 15 seconds while normal Umbrel stop was in
progress; no original/reference containers were included. BTC retained about
1 MiB of data on each VM. No full chain synchronization or mining test was run.

## Automated and UI verification

- 21 recovery/security tests pass locally and in GitHub Actions: preserved app
  data and images, known/unknown exports, MAIN identities, same-version reapply,
  downgrade protection, failed stop/start, backup/restore, file modes, symlink/
  hardlink/path rejection, trusted catalog integrity, API sessions, cross-origin
  blocking, login rate limiting, session expiry, and host-key mismatch.
- The four existing cross-version recipe regression tests pass.
- Login, installed-app selection and the update review dialog were inspected in
  the browser with a local preview fixture. Live API tests used real Umbrel and
  SSH authentication. The fixture is not part of the image or store package.
- Multi-architecture image build passed for Linux AMD64 and ARM64; anonymous
  registry access was verified. ARM hardware recovery has **not** been tested.

Image: `ghcr.io/willitmod/fumbrel:0.1.0-dev`

Pinned multi-architecture digest:
`sha256:a2f6f66a6227264ff88bd2053b36ea09ea55193b01730d467dfefd005165968b`

Build: https://github.com/WillItMod/5tratStore-dev/actions/runs/36026104099

MAIN-to-DEV identity retention and all 18 catalog IDs are covered by automated
tests. Live recovery was exercised with AxeBTC on both OS versions; it is not
claimed as a live recovery test of every family. The bundled DEV recipes also
have the earlier catalog-wide installation/startup evidence recorded at the
repository root in `UMBREL-COMPATIBILITY.md`.

Release scope: **DEV only**. No MAIN store changes or automatic promotion.
