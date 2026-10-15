"""Exact forward-version adapters before frozen historical package contracts."""
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
RECORD = json.loads((ROOT / "APP-VERSION-NORMALIZATION-2026-10-15.json").read_text())
APP = "willitmod-dev-axebch2"
VERSION = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-dev(?:\.(?:0|[1-9][0-9]*))?)?\Z")
MANIFESTS = ("umbrel-app.yml", "global-app.yml", "5tratstore-app.yml")
RELEASE_NOTE = "Standardizes the app version to 0.2.1. The running interface and catalogue use the same version. Existing ports, images, mining configuration and stored data are retained."
BTC_IDS = {"DEV": "willitmod-dev-btc", "MAIN": "willitmod-btc"}
BTC_NOTE = "Standardizes the app version to 0.7.83 in the running interface and catalogue. Existing ports, mining code, node and pool images, configuration and stored data are retained."
BTC_OLD = "ghcr.io/willitmod/axebtc-app-umbrel-dev:0.7.82.17@sha256:21334b67d803987a3ae4e79242ba2d74da0415d22e786783c73723a460d9c174"
BTC_IMAGE = "ghcr.io/willitmod/axebtc-app-umbrel-dev:0.7.83-dev@sha256:e2a213be2c2ff13fbf13c065d361b5a7a0be9601df05aa1edf9c68660802a698"
BTC_PUBLICATION = {
    "publicationRecord": "release-records/btc-0.7.83-dev-image.json",
    "publicationRecordSHA256": "f6c5ef4bc5682afc2392a6d3e5f36a492745e30e0eca68a29dadd70d99bc1308",
    "sourceRepository": "https://github.com/WillItMod/AxeBTC_Build",
    "sourceRevision": "93915c555621ec1aff80ac42cf3335201c670edb",
    "sourceTree": "4505888a70cf54e4b9ad31371ede97365b393662",
    "workflowRun": 38750325672,
    "publicationURL": "https://github.com/WillItMod/AxeBTC_Build/actions/runs/38750325672",
    "imageRef": BTC_IMAGE,
    "versionLiteral": "0.7.83",
    "applicationSourceSHA256": "54731405f387f6c8ecddd827e6571c1390ca998feb87edb7d43ac66c55f1e269",
    "previousApplicationSourceSHA256": "7cfb220103093497f4afaffbec74c6f56e2159d6df53045528e62ec9c9f1a781",
    "applicationModeUidGid": [436, 0, 0],
    "images": {
        "amd64": {"manifestDigest": "sha256:80832b8c1e93fa2b93141d5e1eac5a80729b0b5606e2eab0d3fe13c22478f7ce",
                  "configDigest": "sha256:72e532728ec3ef6413ff030c80c0d5e24aad6953075a366591299ab3199a34d1"},
        "arm64": {"manifestDigest": "sha256:c3e418fc7882bb215ab522c8262804bd5a0532c02284199421f16868eaa310ce",
                  "configDigest": "sha256:5ffa7f1d6af3b59fc231ea5a2b12ce552c28ab895edfcf9087b9bde3f2773c38"},
    },
    "actualNativePreAndPostPublicationVerified": True,
    "anonymousIndexAndBothPlatformConfigsVerified": True,
    "changedRuntimeFile": "/app/app.py",
    "runtimeChangeScope": "Only APP_VERSION literal; all other rootfs bytes, modes, owners, links and runtime config retained except source labels.",
    "guestUpdateQualificationClaimed": False,
}

# Values are reviewed source bindings, not permissions inferred from an
# editable record. Future image revisions require their own exact allowlist.
CONTRACTS = {
    "DEV": {
        "baselineCommit": "bee5c1c7bd2d267b55c8d597b29fa18a97fe2fcd",
        "publishedPortsSHA256": "2c186789d2d7809eefb6f359b5a125c0531171e10bc3b057e8b03cb7aa59afb1",
        "apps": {APP: {
            "beforeVersion": "0.2.0.12-dev.2", "version": "0.2.1-dev",
            "beforeModelSHA256": "ea2ad4c393c7d6f75c43902d4d8c597fe0aa0fba56df9e3849450bd76c88fe22",
            "afterModelSHA256": "3f53360b9bd6edee6a3de230475262a5e1ae9dab860ad5d119c1f64a88c2a782",
            "changes": [{"path": ["services", "app", "environment", "APP_VERSION"],
                         "before": "0.2.0.12-dev.2", "after": "0.2.1-dev"}],
        }, "willitmod-dev-btc": {
            "beforeVersion": "0.7.82.17-dev.1", "version": "0.7.83-dev",
            "beforeModelSHA256": "07a53e99f59be1b72a279d7743ad2091d0deeeeeb4f57e00b3b78e34072d49ab",
            "afterModelSHA256": "22d8c83b1a81bd786eea92760c4e840d5d2f3972189ffc280fcee3fb7b4dfc8f",
            "releaseNotePrefix": BTC_NOTE,
            "changes": [{"path": ["services", "app", "image"], "before": BTC_OLD, "after": BTC_IMAGE}],
        }},
    },
    "MAIN": {
        "baselineCommit": "08c0620ee99fd3c861f54610b32ec564c3501816",
        "publishedPortsSHA256": "cb0f737d9bc0968c9e2eaeaa05400d4703961fa2cfd71355f8f407e2d69c7813",
        "apps": {APP: {
            "beforeVersion": "0.2.0.12", "version": "0.2.1",
            "beforeModelSHA256": "5189e1a3169528c9c4240d3577872f135042541ab25080af66491d7399b22b15",
            "afterModelSHA256": "8be63c5a5e0fec27ba6b9fb3ac2866047f27488af6ec9bb28994a882214dbcb2",
            "changes": [{"path": ["services", "app", "environment", "APP_VERSION"],
                         "before": "0.2.0.12", "after": "0.2.1"}],
        }, "willitmod-btc": {
            "beforeVersion": "0.7.82.17", "version": "0.7.83",
            "beforeModelSHA256": "1868b18c4d002cf8c75ef1a591a77bd6042c7df72893082b8e09f26e8e48eb2a",
            "afterModelSHA256": "cfd50ba78f6b7fa49f6f7e01e0a0fc3d3cd3761934c445a3dd83388059a95410",
            "releaseNotePrefix": BTC_NOTE,
            "changes": [{"path": ["services", "app", "image"], "before": BTC_OLD, "after": BTC_IMAGE}],
        }},
    },
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def contract():
    assert RECORD["schemaVersion"] == 1 and RECORD["channel"] in CONTRACTS
    assert RECORD["releaseNotePrefix"] == RELEASE_NOTE
    assert RECORD["btcPublication"] == BTC_PUBLICATION
    expected = CONTRACTS[RECORD["channel"]]
    for key in ("baselineCommit", "publishedPortsSHA256", "apps"):
        assert RECORD[key] == expected[key], f"Unreviewed version-normalization {key}"
    return expected


def previous_app_version_model(app_id, current):
    restored = copy.deepcopy(current)
    row = contract()["apps"].get(app_id)
    if row is None:
        return restored
    if digest(current) == row["beforeModelSHA256"]:
        return restored
    assert digest(current) == row["afterModelSHA256"], "Unreviewed complete current model"
    for change in row["changes"]:
        node = restored
        for key in change["path"][:-1]:
            node = node[key]
        key = change["path"][-1]
        assert node[key] == change["after"]
        node[key] = change["before"]
    assert digest(restored) == row["beforeModelSHA256"]
    return restored


def package_version(app_id, historical):
    row = contract()["apps"].get(app_id)
    if row is None:
        return historical
    assert historical in (row["beforeVersion"], row["version"]), "Unreviewed preceding package version"
    return row["version"]


def source_bytes(path, revision=None):
    if revision is None:
        return (ROOT / path).read_bytes()
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT)


def package_files(revision=None):
    if revision is not None:
        names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True).splitlines()
        return sorted(name for name in names if name.startswith("willitmod-") and "/" in name)
    return sorted(str(p.relative_to(ROOT)) for p in ROOT.glob("willitmod-*/*") if p.is_file())


def manifest_version_audit():
    pending = []
    for path in package_files():
        if Path(path).name not in MANIFESTS:
            continue
        version = yaml.safe_load(source_bytes(path)).get("version")
        if not isinstance(version, str) or not VERSION.fullmatch(version):
            pending.append({"path": path, "version": version})
    return pending


def published_ports(revision=None):
    inventory = {}
    for path in package_files(revision):
        app_id, filename = path.split("/", 1)
        if filename not in (*MANIFESTS, "docker-compose.yml"):
            continue
        model = yaml.safe_load(source_bytes(path, revision))
        row = inventory.setdefault(app_id, {})
        if filename in MANIFESTS:
            row[filename] = model.get("port")
        else:
            row["services"] = {service: {key: value[key] for key in ("ports", "expose") if key in value}
                               for service, value in model["services"].items() if "ports" in value or "expose" in value}
    return inventory


if __name__ == "__main__":
    pending = manifest_version_audit()
    print(json.dumps({"channel": RECORD["channel"], "status": "pending" if pending else "ready",
                      "nonconformingManifests": pending}, indent=2))
    raise SystemExit(bool(pending))
