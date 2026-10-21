"""Admit only the reviewed BCH/BCH2 liveness release and exact predecessor models.

Publication facts are locked after registry and native platform qualification.
An editable record, a plausible digest or a synthetic test is never admission.
The historical whole-catalogue check is explicit so unrelated future releases
are not permanently frozen by this app-specific gate.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECORD_NAME = "BCH-HEALTH-RELEASE-2026-10-16.json"
APPS = ("willitmod-dev-bch", "willitmod-dev-axebch2")
MUX = "willitmod-dev-5tratmux"
BASELINES = {"MAIN": "778a9005bfc3047e3ee1488b747d3a1032fbcc4c",
             "DEV": "5149d58513c929ac71f686377250a0fbae747413"}
VERSIONS = {"willitmod-dev-bch": "0.9.27", "willitmod-dev-axebch2": "0.2.2"}
BEFORE_VERSIONS = {"willitmod-dev-bch": "0.9.26", "willitmod-dev-axebch2": "0.2.1"}
SOURCES = {"willitmod-dev-bch": ("8e41868dc639d35376c1889f94871db79a05e251", "86d35dc632aa32d7492ca53c7adb44190e5f4143"),
           "willitmod-dev-axebch2": ("611287fd9d41656a3fd19651dcb2ce98dbebf5d3", "01bcf8f40403305aa2673f23eb3e6fd1c670e8ec")}
OS_MINIMUM_VERSION = "0.8.36"
RETENTION_EXTENSION = "x-5tratumos-stop-policy"
OLD_OS_REJECTION_SCOPE = 'OS 0.8.34 and 0.8.35 reject before application deployment: image pull, app stop/start or live Compose replacement. Lifecycle bookkeeping may still update locks, leases, environment repair or rollback copies.'
LOCKS = {'MAIN': '00b2034983ba6f07578f21da557688ba3d9bcb26bbb1e4d8835eefa4be133e82', 'DEV': '092ea7a26f43a1e32d59fe5fb118632d0c206dc24e4f0dc80f87b4d34dc8825e'}
NOTE = "Application health checks now respond without waiting for the node RPC. Slow or unavailable nodes remain visible in the detailed status APIs. Timed-out clients no longer produce broken-pipe tracebacks. Existing ports, node and pool images, mining configuration, payouts and stored data are retained. On 5tratumOS, update the OS to 0.8.36 before updating this app. OS 0.8.34 and 0.8.35 refuse this app update before pulling images, stopping apps or replacing the live Compose definition. Users on earlier OS versions must upgrade the OS first. Umbrel does not require this OS update."
PROBE = 'python -c "import json, urllib.request; r=urllib.request.urlopen(\'http://127.0.0.1:3000/api/health\', timeout=3); assert r.status == 200 and json.load(r).get(\'ok\') is True"'
HEALTHCHECK = {"test": ["CMD-SHELL", PROBE], "interval": "15s", "timeout": "5s", "retries": 20, "start_period": "90s"}
SHA = re.compile(r"[0-9a-f]{64}\Z")
REVISION = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE = re.compile(r"ghcr\.io/willitmod/(?:axebch-app(?:-umbrel-dev)?|axebch2-app):[A-Za-z0-9_.-]+@sha256:[0-9a-f]{64}\Z")
MANIFESTS = ("umbrel-app.yml", "global-app.yml", "5tratstore-app.yml")


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(model):
    return sha256(json.dumps(model, sort_keys=True, separators=(",", ":")).encode())


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root)


def channel(root=ROOT):
    value = json.loads((root / RECORD_NAME).read_text())["channel"]
    assert value in BASELINES
    return value


def version(app_id, release_channel):
    return VERSIONS[app_id] + ("-dev" if release_channel == "DEV" else "")


def predecessor(root, app_id, filename="docker-compose.yml"):
    return yaml.safe_load(git(root, "show", f"{BASELINES[channel(root)]}:{app_id}/{filename}"))


def record(root=ROOT):
    raw = (root / RECORD_NAME).read_bytes()
    release = json.loads(raw)
    release_channel = channel(root)
    assert LOCKS[release_channel] is not None, "Health release awaits actual publication and native qualification"
    assert sha256(raw) == LOCKS[release_channel], "Unreviewed health release record"
    assert release["schemaVersion"] == 1 and release["status"] == "qualified"
    assert release["baselineCommit"] == BASELINES[release_channel]
    assert set(release["apps"]) == set(APPS)
    for app_id, row in release["apps"].items():
        assert row["version"] == version(app_id, release_channel)
        assert (row["sourceRevision"], row["sourceTree"]) == SOURCES[app_id], "Unreviewed health source identity"
        assert IMAGE.fullmatch(row["imageRef"])
        assert ("axebch2-app:" in row["imageRef"]) == (app_id == APPS[1])
        validate_retention_requirement(app_id, row)
    return release


def validate_retention_requirement(app_id, row):
    requirement = row["retentionRequirement"]
    assert set(requirement) == {"appId", "appService", "appSourceRevision", "appImage", "platforms"}, "Unreviewed retention requirement fields"
    assert requirement["appId"] == ("axebch2" if app_id == APPS[1] else "axebch")
    assert requirement["appService"] == "app"
    assert requirement["appSourceRevision"] == row["sourceRevision"]
    assert requirement["appImage"] == row["imageRef"]
    repository = "ghcr.io/willitmod/" + ("axebch2-app" if app_id == APPS[1] else "axebch-app-umbrel-dev")
    assert isinstance(requirement["appImage"], str) and requirement["appImage"].split(":", 1)[0] == repository
    assert set(requirement["platforms"]) == {"amd64", "arm64"}
    for platform in requirement["platforms"].values():
        assert set(platform) == {"appConfigDigest", "appManifestDigest"}
        assert all(isinstance(value, str) and DIGEST.fullmatch(value) for value in platform.values())
    return requirement


def model(app_id, before, row, release_channel):
    expected = copy.deepcopy(before)
    application = expected["services"]["app"]
    application["image"] = row["imageRef"]
    environment = application["environment"]
    environment["APP_REVISION"] = row["sourceRevision"]
    environment["APP_CHANNEL"] = release_channel
    if app_id == APPS[1]:
        environment["APP_VERSION"] = version(app_id, release_channel)
        environment["APP_RELEASE_PHASE"] = "STABLE" if release_channel == "MAIN" else "RC"
    application["healthcheck"] = copy.deepcopy(HEALTHCHECK)
    expected[RETENTION_EXTENSION] = {"version": 2, "services": {},
                                     "requiresRetention": copy.deepcopy(validate_retention_requirement(app_id, row))}
    return expected


def bch2_successor(root=ROOT):
    spec = importlib.util.spec_from_file_location('bch2_retention_successor', root / 'scripts/bch2_retention_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def previous_model(app_id, current, root=ROOT, *, historical_models=()):
    if app_id not in APPS:
        return copy.deepcopy(current)
    before = predecessor(root, app_id)
    if current == before or digest(current) in historical_models:
        return copy.deepcopy(current)
    if app_id == APPS[1] and current.get('services', {}).get('app', {}).get('environment', {}).get('APP_VERSION') in ('0.2.3', '0.2.3-dev'):
        current = bch2_successor(root).previous_model(current, root)
    release = record(root)
    assert current == model(app_id, before, release["apps"][app_id], release["channel"]), "Unreviewed health runtime delta"
    return before


def previous_manifest(app_id, current, filename="umbrel-app.yml", root=ROOT):
    if app_id not in APPS:
        return copy.deepcopy(current)
    before = predecessor(root, app_id, filename)
    if current == before:
        return copy.deepcopy(current)
    if app_id == APPS[1] and current.get('version') in ('0.2.3', '0.2.3-dev'):
        current = bch2_successor(root).previous_manifest(current, filename, root)
    release = record(root)
    expected = copy.deepcopy(before)
    expected["version"] = version(app_id, release["channel"])
    expected["releaseNotes"] = NOTE + "\n" + before["releaseNotes"]
    assert current == expected, "Unreviewed health manifest delta"
    return before


def package_version(app_id, historical, root=ROOT):
    if app_id not in APPS:
        return historical
    release = record(root)
    release_channel = release["channel"]
    before = BEFORE_VERSIONS[app_id] + ("-dev" if release_channel == "DEV" else "")
    current = version(app_id, release_channel)
    assert historical in (before, current), "Unreviewed health predecessor version"
    return current


def package_files(root, app_id):
    return {str(path.relative_to(root)): {"sha256": sha256(path.read_bytes()), "mode": oct(stat.S_IMODE(path.lstat().st_mode))}
            for path in (root / app_id).rglob("*") if path.is_file() or path.is_symlink()}


def validate_package(root, app_id, release):
    row = release["apps"][app_id]
    names = git(root, "ls-tree", "-r", "--name-only", release["baselineCommit"], "--", app_id).decode().splitlines()
    actual = package_files(root, app_id)
    assert set(actual) == set(names), "Unexpected health package inventory"
    successor = None
    if app_id == APPS[1] and actual != row['packageFiles']:
        successor = bch2_successor(root)
        successor.validate(root)
        actual = {name: {'sha256': sha256(successor.previous_file_bytes((root / name).read_bytes(), name, root)),
                         'mode': value['mode']} for name, value in actual.items()}
    assert actual == row["packageFiles"], "Unreviewed health package bytes"
    for name in names:
        path = root / name
        assert stat.S_ISREG(path.lstat().st_mode), "Health package symlink forbidden"
        baseline_mode = git(root, "ls-tree", release["baselineCommit"], "--", name).decode().split()[0]
        assert ("100755" if path.stat().st_mode & 0o111 else "100644") == baseline_mode
        filename = Path(name).name
        if filename == "docker-compose.yml" and name == app_id + "/docker-compose.yml":
            assert previous_model(app_id, yaml.safe_load(path.read_text()), root) == predecessor(root, app_id)
        elif filename in MANIFESTS and name == app_id + "/" + filename:
            assert previous_manifest(app_id, yaml.safe_load(path.read_text()), filename, root) == predecessor(root, app_id, filename)
        else:
            assert path.read_bytes() == git(root, "show", f"{release['baselineCommit']}:{name}"), "Unrelated health package file changed"


def validate_publication(root, app_id, row):
    publication = row["publication"]
    short = "bch2" if app_id == APPS[1] else "bch"
    assert publication["path"] == f"release-records/{short}-{row['version']}-health-delivery.json"
    raw = (root / publication["path"]).read_bytes()
    assert SHA.fullmatch(publication["sha256"]) and sha256(raw) == publication["sha256"]
    proof = json.loads(raw)
    assert proof["schemaVersion"] == 1 and proof["result"] == "PASS"
    assert proof["appId"] == app_id
    for key in ("version", "sourceRevision", "sourceTree", "imageRef"):
        assert proof[key] == row[key]
    assert proof["anonymousIndexAndBothPlatformsVerified"] is True
    assert set(proof["platforms"]) == {"amd64", "arm64"}
    requirement = validate_retention_requirement(app_id, row)
    for architecture, platform in proof["platforms"].items():
        assert requirement["platforms"][architecture] == {"appConfigDigest": platform["configDigest"], "appManifestDigest": platform["manifestDigest"]}, "Retention admission differs from published platform identity"
        for key in ("manifestDigest", "configDigest"):
            assert DIGEST.fullmatch(platform[key])
        assert SHA.fullmatch(platform["protectedExecutableSHA256"])
        for key in ("noApplicationPythonSources", "noSourceMaps", "nativeStartupVerified", "healthIndependentOfNodeRpcVerified"):
            assert platform[key] is True
        assert platform["httpHealthVersion"] == row["version"]
    assert set(proof["qualification"]) == {"umbrel1.7.4", "umbrel2.0.0", "5tratumOS"}
    for qualification in proof["qualification"].values():
        assert qualification["result"] == "PASS" and SHA.fullmatch(qualification["receiptSHA256"])
        assert isinstance(qualification["receipt"], str) and qualification["receipt"] and "/" not in qualification["receipt"]
        receipt_path = root / "release-records" / qualification["receipt"]
        assert stat.S_ISREG(receipt_path.lstat().st_mode), "Qualification receipt must be a regular file"
        receipt_raw = receipt_path.read_bytes()
        assert sha256(receipt_raw) == qualification["receiptSHA256"], "Qualification receipt bytes changed"
        assert json.loads(receipt_raw)["result"] == "PASS"
        # Native managers exercised MAIN metadata. DEV uses the identical
        # immutable image with independently checked per-architecture metadata;
        # a native DEV installation or DEV OS update is never invented.
        assert qualification["nativeManagerObservationChannel"] == "MAIN"
        assert qualification["nativeManagerObservedVersion"] == VERSIONS[app_id]
        assert qualification["sharedImageRef"] == row["imageRef"]
        assert qualification["sharedConfigDigest"] == proof["platforms"]["amd64"]["configDigest"]
        for key in ("healthUnderBlockedRpcVerified", "clientDisconnectVerified", "unchangedPortsVerified", "persistentStatePreserved"):
            assert qualification[key] is True
    os_qualification = proof["qualification"]["5tratumOS"]
    assert os_qualification["osVersion"] == OS_MINIMUM_VERSION
    assert os_qualification["oldOsRejectionScope"] == OLD_OS_REJECTION_SCOPE
    for key in ("retentionAdmissionVerified", "oldOsRejectedBeforeMutationVerified"):
        assert os_qualification[key] is True
    return proof


def validate_baseline(root, release_channel):
    baseline = BASELINES[release_channel]
    names = git(root, "ls-tree", "-r", "--name-only", baseline).decode().splitlines()
    selected = set(APPS) | {MUX}
    protected = [name for name in names if
                 (name.startswith("willitmod-") and name.split("/", 1)[0] not in selected) or
                 (name.endswith(".json") and ("/" not in name or name.startswith("release-records/")))]
    assert protected
    assert git(root, "diff", "--name-only", baseline, "--", *protected).decode().splitlines() == [], "Preexisting app or historical release record changed"
    old_packages = {name for name in names if name.startswith("willitmod-")}
    current_packages = {str(path.relative_to(root)) for folder in root.glob("willitmod-*") if folder.is_dir()
                        for path in folder.rglob("*") if path.is_file() or path.is_symlink()}
    assert current_packages == old_packages, "Unexpected catalogue package inventory"


def validate(root=ROOT, *, check_baseline=False):
    release = record(root)
    for app_id in APPS:
        validate_package(root, app_id, release)
        validate_publication(root, app_id, release["apps"][app_id])
    if check_baseline:
        validate_baseline(root, release["channel"])
    return release


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-baseline", action="store_true", help="Release admission only: preserve all predecessor records and other app packages")
    args = parser.parse_args()
    release = validate(check_baseline=args.check_baseline)
    print(json.dumps({"status": "PASS", "channel": release["channel"], "versions": {a: release['apps'][a]['version'] for a in APPS}, "initialCatalogueBaselineChecked": args.check_baseline}))
