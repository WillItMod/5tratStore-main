"""Exact additive share-partition repair release; pending publication is never admitted."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = "willitmod-dev-powpow"
CHANNEL = "MAIN"
BASELINE = '72e764558938feba3557ec23dbe6753a34771c63'
VERSION = '0.2.39'
PREVIOUS_VERSION = '0.2.38'
APP_RUNTIME_VERSION = "0.2.37"
SOURCE = 'cfbbfc500fdaac6a6bcaba01eb0f543782e67397'
SOURCE_TREE = '78868a4614fda2e8e1d648a02a8bc53b29d79db3'
WORKFLOW_RUN = 41484899413
IMAGE_TAG = 'ghcr.io/willitmod/powpow-pool:0.2.37-mux.cfbbfc500fda'
IMAGE_REF = 'ghcr.io/willitmod/powpow-pool:0.2.37-mux.cfbbfc500fda@sha256:a1fcca03de7339e1e93f0748e35c6d8fbe48435016202e0aca93d0d04772affd'
RECORD_NAME = 'POWPOW-SHARE-PARTITION-2026-11-02.json'
RECORD_SHA256 = '6b2ff57088b6f61fa89d1d61ec1e9c20ada37373bbd46b9956aacee2f38cd73e'
BOOTSTRAP_SHA256 = 'e4670bb15c1f8f4aba9fc872f62fa5fb82b97a979c666c0a317359454cc0ad48'
BEFORE_MODEL_SHA256 = '49fc1d9a12612887e876a01d0f0bc51420d7be90bde251b7c2a333d9a75994bd'
NOTE = 'Repairs missing share-table partitions automatically when the pool starts so new shares and pool statistics can be saved. Existing database rows are preserved, and custom pool names are supported.'
MANIFESTS = ("umbrel-app.yml", "global-app.yml")
REQUIRED_SCHEMA_CASES = ['ActualBundledEntrypointRepairsBeforeRPCWaitAndStopsCleanly', 'ConflictingChildNameFailsAndRollsBackAllSchemaChanges', 'ExistingDifferentlyNamedDefaultPartitionPreserved', 'MissingPartitionCOPYReproducedThenRecoveredWithRowsAndOIDsPreserved', 'concurrent_freshBootstrapsSerializeSuccessfully', 'concurrent_partitionedBootstrapsSerializeSuccessfully', 'existingPlainRowsAndOIDPreservedWithoutPartitionConversion', 'freshHistoricalSeedsThenTwoRepairsAndDefaultCustomPoolCOPY', 'unexpected_list_keyFailsWithoutChangingRowsOrSchema', 'unexpected_range_keyFailsWithoutChangingRowsOrSchema']


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root)


def baseline_bytes(path, root=ROOT):
    return git(root, "show", f"{BASELINE}:{path}")


def baseline_model(root=ROOT):
    model = yaml.safe_load(baseline_bytes(f"{APP}/docker-compose.yml", root))
    assert digest(model) == BEFORE_MODEL_SHA256, "Unreviewed complete predecessor model"
    return model


def require_image():
    assert IMAGE_REF is not None, "PowPow pool publication has not been finalized"
    assert IMAGE_TAG is not None, "PowPow pool publication has not been finalized"
    assert re.fullmatch(re.escape(IMAGE_TAG) + r"@sha256:[0-9a-f]{64}", IMAGE_REF)
    return IMAGE_REF


def validate_model(current, root=ROOT, image=None):
    image = require_image() if image is None else image
    expected = baseline_model(root)
    expected["services"]["pool"]["image"] = image
    assert digest(current) == digest(expected), "Unreviewed complete PowPow successor model"
    assert current["services"]["app"]["environment"]["APP_VERSION"] == APP_RUNTIME_VERSION
    return current


def previous_model(app_id, current, root=ROOT):
    if app_id != APP:
        return copy.deepcopy(current)
    previous = baseline_model(root)
    if digest(current) == BEFORE_MODEL_SHA256:
        return copy.deepcopy(current)
    validate_model(current, root)
    return previous


def package_version(app_id, historical, root=ROOT):
    if app_id != APP:
        return historical
    assert historical in (PREVIOUS_VERSION, VERSION), "Unreviewed preceding PowPow version"
    return VERSION


def expected_package_bytes(name, root=ROOT, image=None):
    raw = baseline_bytes(f"{APP}/{name}", root)
    if name == "docker-compose.yml":
        image = require_image() if image is None else image
        old = baseline_model(root)["services"]["pool"]["image"].encode()
        assert raw.count(old) == 1
        return raw.replace(old, image.encode(), 1)
    if name in MANIFESTS:
        old = f'version: "{PREVIOUS_VERSION}"\n'.encode()
        assert raw.count(old) == 1 and raw.count(b"releaseNotes: >-\n") == 1
        raw = raw.replace(old, f'version: "{VERSION}"\n'.encode(), 1)
        return raw.replace(b"releaseNotes: >-\n", ("releaseNotes: >-\n  " + NOTE + "\n\n").encode(), 1)
    return raw


def baseline_files(root=ROOT):
    rows = git(root, "ls-tree", "-r", BASELINE, "--", APP).decode().splitlines()
    return {line.split("\t", 1)[1]: line.split()[0] for line in rows}


def validate_package(root=ROOT, image=None):
    expected = baseline_files(root)
    current = {str(path.relative_to(root)): path for path in (root / APP).rglob("*") if not path.is_dir() or path.is_symlink()}
    assert set(current) == set(expected), "PowPow package file set changed"
    for name, path in current.items():
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode), f"PowPow file is not regular: {name}"
        assert stat.S_IMODE(info.st_mode) == int(expected[name], 8) & 0o777, f"PowPow file mode changed: {name}"
        assert path.read_bytes() == expected_package_bytes(str(path.relative_to(root / APP)), root, image), f"Unreviewed PowPow package bytes: {name}"
    validate_model(yaml.safe_load((root / APP / "docker-compose.yml").read_text()), root, image)
    return {name: {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "mode": oct(stat.S_IMODE(path.stat().st_mode))} for name, path in sorted(current.items())}


def validate_baseline(root=ROOT):
    """Release-time scope check; unrelated future app updates remain independent."""
    names = git(root, "ls-tree", "-r", "--name-only", BASELINE).decode().splitlines()
    protected = [name for name in names if (name.startswith("willitmod-") and not name.startswith(APP + "/")) or ("/" not in name and name.endswith(".json")) or name.startswith("powpow-release-records/")]
    # Later node-only successors: each validates its exact delta, then its
    # changed files are compared at their predecessor bytes.
    xec_node = node_core = dgb_core = None
    if (root / 'XEC-NODE-2026-11-10.json').is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('xec_node_partition_predecessor', root / 'scripts/xec_node_release.py')
        xec_node = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(xec_node)
        xec_node.validate(root)
    if (root / 'NODE-CORE-2026-11-10.json').is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('node_core_partition_predecessor', root / 'scripts/node_core_release.py')
        node_core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(node_core)
        node_core.validate(root)
    if (root / 'release-records/dgb-core-9.26.6-thaw-day-2026-11-10.json').is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('dgb_core_partition_predecessor', root / 'scripts/dgb_core_release.py')
        dgb_core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(dgb_core)
        dgb_core.validate(root)
    node_core_changed = node_core.changed_files(root) if node_core is not None else set()
    for name in protected:
        path = root / name
        assert path.is_file() and not path.is_symlink(), f"Protected predecessor file missing: {name}"
        raw = path.read_bytes()
        if xec_node is not None and name in xec_node.CHANGED:
            raw = xec_node.baseline_bytes(root, name)
        if name in node_core_changed:
            raw = node_core.current_bytes(root, name)
        if dgb_core is not None and name in dgb_core.CHANGED:
            raw = dgb_core.current_bytes(root, name)
        assert raw == baseline_bytes(name, root), f"Protected predecessor file changed: {name}"
        mode = git(root, "ls-tree", BASELINE, "--", name).decode().split()[0]
        assert stat.S_IMODE(path.stat().st_mode) == int(mode, 8) & 0o777, f"Protected predecessor mode changed: {name}"
    old_packages = {name for name in names if name.startswith("willitmod-")}
    actual = {str(path.relative_to(root)) for directory in root.glob("willitmod-*") if directory.is_dir() for path in directory.rglob("*") if not path.is_dir() or path.is_symlink()}
    # 5tratDoom (willitmod-axedoom) is a separately admitted new package;
    # its published ports are pinned by test_app_version_normalization.
    actual = {name for name in actual if not name.startswith("willitmod-axedoom/")}
    assert actual == old_packages, "Store package file set changed outside approved successor"


def validate_schema_qualification(qualification, platforms):
    assert qualification["result"] == "PASS" and set(qualification["platforms"]) == {"amd64", "arm64"}
    assert BOOTSTRAP_SHA256 is not None and re.fullmatch(r"[0-9a-f]{64}", BOOTSTRAP_SHA256)
    assert qualification["bootstrapSHA256"] == BOOTSTRAP_SHA256
    assert set(platforms) == {"amd64", "arm64"}
    for architecture, native in qualification["platforms"].items():
        assert native["result"] == "PASS" and native["bootstrapSHA256"] == BOOTSTRAP_SHA256
        assert native['nativeArchitecture'] == architecture
        assert native['verifiedNativeManifestDigest'] == platforms[architecture]['manifestDigest']
        assert native["allDisposableObjectsRemoved"] is True
        assert set(native["cases"]) == set(REQUIRED_SCHEMA_CASES)
        assert all(value is True for value in native["cases"].values())
    return qualification


def record(root=ROOT):
    image = require_image()
    assert RECORD_SHA256 is not None, "PowPow release evidence has not been finalized"
    raw = (root / RECORD_NAME).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == RECORD_SHA256, "Unreviewed PowPow release evidence"
    result = json.loads(raw)
    assert result["status"] == "qualified" and result["schemaVersion"] == 1
    assert (result["channel"], result["appId"], result["packageVersion"], result["retainedAppRuntimeVersion"]) == (CHANNEL, APP, VERSION, APP_RUNTIME_VERSION)
    assert (result["sourceRevision"], result["sourceTree"], result["workflowRun"], result["baselineCommit"]) == (SOURCE, SOURCE_TREE, WORKFLOW_RUN, BASELINE)
    assert result["imageRef"] == image and result["beforeModelSHA256"] == BEFORE_MODEL_SHA256
    model = yaml.safe_load((root / APP / "docker-compose.yml").read_text())
    assert result["afterModelSHA256"] == digest(validate_model(model, root))
    assert result["packageFiles"] == validate_package(root)
    assert set(result["platforms"]) == {"amd64", "arm64"}
    for row in result["platforms"].values():
        assert set(row) == {"manifestDigest", "configDigest"}
        assert all(re.fullmatch(r"sha256:[0-9a-f]{64}", value) for value in row.values())
    proof = result["publicationEvidence"]
    evidence_path = root / proof["path"]
    assert evidence_path.is_file() and not evidence_path.is_symlink()
    assert hashlib.sha256(evidence_path.read_bytes()).hexdigest() == proof["sha256"]
    evidence = json.loads(evidence_path.read_text())
    assert evidence["result"] == "PASS" and evidence["imageRef"] == image
    assert evidence["sourceRevision"] == SOURCE and evidence["platforms"] == result["platforms"]
    assert result["bootstrapSHA256"] == BOOTSTRAP_SHA256
    validate_schema_qualification(evidence["schemaRepairQualification"], result['platforms'])
    assert result["guestUpdateQualificationClaimed"] is False
    return result


def validate(root=ROOT, check_baseline=False):
    result = record(root)
    if check_baseline:
        validate_baseline(root)
    return result


def previous_package_bytes(name, raw, root=ROOT):
    """Restore only a byte-exact predecessor or this reviewed successor."""
    previous = baseline_bytes(f"{APP}/{name}", root)
    if raw == previous:
        return previous
    assert name in ("docker-compose.yml", *MANIFESTS), "Unreviewed PowPow successor file"
    assert raw == expected_package_bytes(name, root), "Unreviewed PowPow successor bytes"
    return previous


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-baseline", action="store_true")
    arguments = parser.parse_args()
    result = validate(check_baseline=arguments.check_baseline)
    print(json.dumps({"result": "PASS", "channel": CHANNEL, "packageVersion": VERSION, "imageRef": result["imageRef"]}, indent=2))
