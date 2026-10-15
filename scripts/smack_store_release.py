"""Exact Smack 0.11.23 admission before the frozen historical release chain."""
import copy
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path(__file__).resolve().parents[1]
APP = "willitmod-dev-5tratsmack"
SOURCE = "42ef8e00bbdfe67dbade44ef6c56aa0f2676c986"
IMAGE = "ghcr.io/willitmod/5tratsmack-app:0.11.23-store.42ef8e00bbdf@sha256:598071c0e8a0e01e837b1b8c375c71390d75e2180673ea5dff1af1b613f50404"
OLD_IMAGE = "ghcr.io/willitmod/5tratsmack-app:0.11.22-hero.6fc6597c3aba@sha256:304566aaf4374398d10e53612f1b1ccce89344e6fcf4a51293006d9c8f2111e9"
PLATFORM = "${APP_5TRATSMACK_PLATFORM:-5TRATUMOS}"
EXPORT = b'#!/usr/bin/env bash\n# Umbrel sources this hook before Compose; native 5tratumOS uses the default.\nexport APP_5TRATSMACK_PLATFORM="UMBREL"\n'
LOCKS = {
    "DEV": "1da548e25ead150e98ed5adb30e169be886de9155f408dcf24e834d0baff59c6",
    "MAIN": "8ad3b52b42692289c68310662633a9742e489346243eaefcc05365c2c0252b04",
}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(model):
    return sha256(json.dumps(model, sort_keys=True, separators=(",", ":")).encode())


def record(root=ROOT):
    raw = (root / "SMACK-STORE-UPDATE-2026-10-15.json").read_bytes()
    result = json.loads(raw)
    assert result["schemaVersion"] == 1 and result["appId"] == APP
    assert sha256(raw) == LOCKS[result["channel"]], "Unreviewed Smack release record"
    assert result["imageRef"] == IMAGE and result["sourceRevision"] == SOURCE
    assert result["compiledCoreVersion"] == "0.11.23"
    return result


def package_version(app_id, historical):
    if app_id != APP:
        return historical
    r = record()
    assert historical in (r["previousVersion"], r["version"])
    return r["version"]


def previous_store_model(app_id, current):
    restored = copy.deepcopy(current)
    if app_id != APP:
        return restored
    r = record()
    c = r["runtimeContract"]
    if digest(current) == c["beforeModelSHA256"]:
        return restored
    assert digest(current) == c["afterModelSHA256"], "Unreviewed complete Smack model"
    expected = {
        ("services", "app", "image"): (OLD_IMAGE, IMAGE),
        ("services", "app", "environment", "APP_IMAGE"): (OLD_IMAGE, IMAGE),
        ("services", "app", "environment", "APP_VERSION"): ("0.11.21", r["version"]),
        ("services", "app", "environment", "FIVETRAT_RELEASE_TAG"): ("0.11.21", r["version"]),
        ("services", "app", "environment", "APP_REVISION"): ("f41e154a74afbd54f67545d0b95d18506a336fa1", SOURCE),
        ("services", "app", "environment", "APP_PLATFORM"): ("5TRATUMOS", PLATFORM),
    }
    assert len(c["changes"]) == len(expected)
    assert {tuple(row["path"]) for row in c["changes"]} == set(expected)
    for row in c["changes"]:
        path = tuple(row["path"])
        before, after = expected[path]
        assert (row["before"], row["after"]) == (before, after)
        node = restored
        for key in path[:-1]:
            node = node[key]
        assert node[path[-1]] == after
        node[path[-1]] = before
    assert digest(restored) == c["beforeModelSHA256"]
    return restored


def validate_files(root=ROOT):
    r = record(root)
    expected = r["packageFiles"]
    current = {str(p.relative_to(root)) for p in (root / APP).rglob("*") if p.is_file() or p.is_symlink()}
    assert current == set(expected), "Unexpected Smack package file inventory"
    for name, identity in expected.items():
        path = root / name
        s = path.lstat()
        assert stat.S_ISREG(s.st_mode), "Smack package file must be regular"
        assert sha256(path.read_bytes()) == identity["sha256"], "Smack package bytes differ: " + name
        assert oct(stat.S_IMODE(s.st_mode)) == identity["mode"], "Smack package mode differs: " + name
    assert (root / APP / "exports.sh").read_bytes() == EXPORT
    assert stat.S_IMODE((root / APP / "exports.sh").stat().st_mode) == 0o755
    for name, identity in r["frozenRecords"].items():
        assert sha256((root / name).read_bytes()) == identity, "Historical record changed: " + name
    p = r["publication"]
    raw = (root / p["path"]).read_bytes()
    assert sha256(raw) == p["sha256"] == "aa342c83324aea9e3d453170371a97a4371eb16e8dc5c8928b38909a51fe3664"
    publication = json.loads(raw)
    assert publication["source"] == SOURCE and publication["version"] == "0.11.23"
    assert publication["index"] == IMAGE.split("@", 1)[1]
    assert publication["run"] == p["workflowRun"] == 38750784963
    assert publication["anonymousTagAndImmutableIndexMatch"] is True
    assert publication["nativeHTTPHtmlAboutVersion"] == "0.11.23"
    assert publication["portsChanged"] is False
    assert set(publication["platforms"]) == {"amd64", "arm64"}
    assert all(row["nativeConfigExact"] and row["onlyOneAddedLayer"] for row in publication["platforms"].values())
    assert publication["all13ApplicationFilesAccountedForAnd11Unchanged"] is True
    platform = r["platformDelivery"]
    raw = (root / platform["path"]).read_bytes()
    assert sha256(raw) == platform["sha256"] == "a5068beb1ca459443237d5c83f44e7506d63ebcac79e8ea6779fa7e001de643d"
    proof = json.loads(raw)
    assert proof["schemaVersion"] == 1 and proof["result"] == "PASS"
    assert proof["appImageRef"] == IMAGE
    binding = proof["packageBinding"][r["channel"].lower()]
    assert binding["currentComposeSHA256"] == expected[APP + "/docker-compose.yml"]["sha256"]
    assert binding["exportsSHA256"] == sha256(EXPORT) and binding["exportsMode"] == "0755"
    assert binding["wholeParsedModelIdenticalToTested"] is True
    assert proof["runtimeDelta"]["expression"] == PLATFORM
    assert proof["runtimeDelta"]["allOtherRuntimeFieldsRetained"] is True
    assert proof["compose"]["bothChannelsPassed"] and proof["compose"]["wholeParsedModelsOnlyPlatformChanged"]
    assert {row["version"] for row in proof["umbrel"]} == {"1.7.4", "2.0.0"}
    assert all(row["sourceAppBeforeCompose"] for row in proof["umbrel"])
    tests = proof["catalogueTests"]
    assert sha256((root / tests["file"]).read_bytes()) == tests["sha256"]
    return r
