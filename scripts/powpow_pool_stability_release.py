"""Exact PowPow pool-only successor; pending publication is never admitted."""
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
BASELINE = "7458a751b8ecb00c39a878ee6b31e3b78e2b6edf"
VERSION = "0.2.38"
PREVIOUS_VERSION = "0.2.37"
APP_RUNTIME_VERSION = "0.2.37"
SOURCE = "a20704f8b2adb93d17249944b4c1f1d9128305aa"
SOURCE_TREE = "60670662b59d34ce55ced4da4998bcee4a9bbf4e"
WORKFLOW_RUN = 41470941258
IMAGE_TAG = "ghcr.io/willitmod/powpow-pool:0.2.37-mux.a20704f8b2ad"
IMAGE_REF = 'ghcr.io/willitmod/powpow-pool:0.2.37-mux.a20704f8b2ad@sha256:16de156be9f022b1fa2a5d9859232845dd041c457836901647353dcc57851b3c'
RECORD_NAME = "POWPOW-POOL-STABILITY-2026-11-02.json"
RECORD_SHA256 = '96f0ba17d5a585f306703f3073e9f2c8be6b26514e299464dcedee9d560035ac'
BEFORE_MODEL_SHA256 = "cc80af4412bfdd9843fc6c8b4ac065c99fbce82e88283cb0424ad4b4e5cb2035"
NOTE = "Improves pool stability when miners reconnect and prevents failed share writes from exhausting database connections. Updates the pool service while retaining the application interface at version 0.2.37, node images, mining settings and stored data."
MANIFESTS = ("umbrel-app.yml", "global-app.yml")


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


def partition_successor(root=ROOT):
    """A separately locked successor precedes these frozen stability checks."""
    if not (root / 'POWPOW-SHARE-PARTITION-2026-11-02.json').is_file():
        return None
    import importlib.util
    spec = importlib.util.spec_from_file_location('powpow_share_partition_successor', root / 'scripts/powpow_share_partition_release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_image():
    assert IMAGE_REF is not None, "PowPow pool publication has not been finalized"
    assert re.fullmatch(re.escape(IMAGE_TAG) + r"@sha256:[0-9a-f]{64}", IMAGE_REF)
    return IMAGE_REF


def validate_model(current, root=ROOT, image=None):
    successor = partition_successor(root) if image is None else None
    image = require_image() if image is None else image
    expected = baseline_model(root)
    expected["services"]["pool"]["image"] = image
    if successor is not None and digest(current) != digest(expected):
        current = successor.previous_model(APP, current, root)
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
    successor = partition_successor(root) if image is None else None
    expected = baseline_files(root)
    current = {str(path.relative_to(root)): path for path in (root / APP).rglob("*") if not path.is_dir() or path.is_symlink()}
    assert set(current) == set(expected), "PowPow package file set changed"
    identities = {}
    for name, path in current.items():
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode), f"PowPow file is not regular: {name}"
        assert stat.S_IMODE(info.st_mode) == int(expected[name], 8) & 0o777, f"PowPow file mode changed: {name}"
        relative = str(path.relative_to(root / APP))
        raw = path.read_bytes()
        if successor is not None:
            raw = successor.previous_package_bytes(relative, raw, root)
        assert raw == expected_package_bytes(relative, root, image), f"Unreviewed PowPow package bytes: {name}"
        identities[name] = {"sha256": hashlib.sha256(raw).hexdigest(), "mode": oct(stat.S_IMODE(info.st_mode))}
    validate_model(yaml.safe_load((root / APP / "docker-compose.yml").read_text()), root, image)
    return dict(sorted(identities.items()))


def validate_baseline(root=ROOT):
    """Release-time scope check; unrelated future app updates remain independent."""
    names = git(root, "ls-tree", "-r", "--name-only", BASELINE).decode().splitlines()
    protected = [name for name in names if (name.startswith("willitmod-") and not name.startswith(APP + "/")) or ("/" not in name and name.endswith(".json"))]
    # Later node-only successors: each validates its exact delta, then its
    # changed files are compared at their predecessor bytes.
    xec_node = node_core = dgb_core = None
    if (root / 'XEC-NODE-2026-11-10.json').is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('xec_node_powpow_predecessor', root / 'scripts/xec_node_release.py')
        xec_node = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(xec_node)
        xec_node.validate(root)
    if (root / 'NODE-CORE-2026-11-10.json').is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('node_core_powpow_predecessor', root / 'scripts/node_core_release.py')
        node_core = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(node_core)
        node_core.validate(root)
    if (root / 'release-records/dgb-core-9.26.6-thaw-day-2026-11-10.json').is_file():
        import importlib.util
        spec = importlib.util.spec_from_file_location('dgb_core_powpow_predecessor', root / 'scripts/dgb_core_release.py')
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
    assert result["guestUpdateQualificationClaimed"] is False
    return result


def validate(root=ROOT, check_baseline=False):
    successor = partition_successor(root)
    if successor is not None:
        successor.validate(root)
    result = record(root)
    if check_baseline:
        validate_baseline(root)
    return result


def historical_protected_paths(root, previous_commit, protected):
    """Admit only this exact successor before an older other-app comparison."""
    validate(root)
    reviewed = {APP + '/' + name for name in ('docker-compose.yml', *MANIFESTS)}
    assert reviewed <= set(protected), 'Historical PowPow package inventory differs'
    for name in reviewed:
        assert baseline_bytes(name, root) == git(root, 'show', previous_commit + ':' + name), 'Historical PowPow predecessor bytes differ'
        before_mode = git(root, 'ls-tree', BASELINE, '--', name).decode().split()[0]
        historical_mode = git(root, 'ls-tree', previous_commit, '--', name).decode().split()[0]
        assert before_mode == historical_mode, 'Historical PowPow predecessor mode differs'
    return [name for name in protected if name not in reviewed]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-baseline", action="store_true")
    arguments = parser.parse_args()
    result = validate(check_baseline=arguments.check_baseline)
    print(json.dumps({"result": "PASS", "channel": CHANNEL, "packageVersion": VERSION, "imageRef": result["imageRef"]}, indent=2))
