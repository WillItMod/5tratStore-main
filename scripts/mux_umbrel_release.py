"""Exact additive Umbrel-only MUX admission, including protected image receipts.

This gate never turns an editable JSON claim into release authorization. The
reviewed record and public delivery receipt are pinned below at finalization.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = "willitmod-dev-5tratmux"
RECORD_NAME = "MUX-UMBREL-0.9.79-2026-10-15.json"
SOURCE = "8e5868d4b86ca7a56a436684158c64dc17b120c8"
TREE = "a3c29335cf4680f38d95707814063ffba0298a89"
BASE = "d7d1ee750f440cf31cec4b0ca70af91269281f91"
BASELINES = {"MAIN": "562f221f7f325ea310c9803892a7a02a246ba294",
             "DEV": "4819b0e4a71d9568c98140259c0e342aa79fac8a"}
VERSIONS = {"MAIN": "0.9.79", "DEV": "0.9.79-dev"}
# Reviewed public image and delivery bindings; changes require renewed admission.
LOCKS = {'MAIN': '88d8d549d71fc041565bca4113278a85c684a177f42f928067467d53e1145ad5', 'DEV': '273ea43fabd4adb0eea92522aaa81daa93831bd4c1c6c8a300a9e5f7f120432f'}
PUBLICATION_LOCKS = {'MAIN': '013db0c1bb44c35075a1bc1c1c8a26772984b951c1c878746cf0a12f0459bdbb', 'DEV': 'f9395b68f35d5bc682f91480647f27d9259214d49d39dfcb53f9c96c27cfd451'}
IMAGE_REFS = {'MAIN': 'ghcr.io/willitmod/5tratmux-app:0.9.79-umbrel@sha256:13b78473d6c16ec5e9104695df030c240f4189c4d7488ba63377f8fd316c7391', 'DEV': 'ghcr.io/willitmod/5tratmux-app:0.9.79-umbrel-dev@sha256:d875ce12a5d23eeb63bf0bfcd88f0559cb69ff2445e38e15c2f7f68b56cbcc66'}
FILES = frozenset({"data/.gitkeep", "docker-compose.yml", "hooks/pre-start", "icon.png", "umbrel-app.yml"})
HOOK_SHA256 = "fefa82989c4646016643f78ff6a4efea179b712c5485fca64c3bbf1bb484737f"
ICON_SHA256 = "3eef68f8307de4df7a43386b2dbc3cdaa2b9e97423c93945c18e6be3256ad9e8"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
PORTS = {"umbrel-app.yml": 21222,
         "services": {"server": {"ports": ["7331:7331/tcp"], "expose": ["21222"]}}}


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _git(root, *arguments):
    return subprocess.check_output(["git", *arguments], cwd=root)


def record(root=ROOT):
    raw = (root / RECORD_NAME).read_bytes()
    result = json.loads(raw)
    channel = result["channel"]
    assert channel in VERSIONS and result["schemaVersion"] == 1
    assert LOCKS[channel] is not None, "MUX publication has not been finalized"
    assert sha256(raw) == LOCKS[channel], "Unreviewed MUX release record"
    assert result["status"] == "qualified"
    assert (result["appId"], result["version"], result["baselineCommit"]) == (APP, VERSIONS[channel], BASELINES[channel])
    assert (result["sourceRevision"], result["sourceTree"], result["canonicalBase"]) == (SOURCE, TREE, BASE)
    assert result["imageRef"] == IMAGE_REFS[channel] and result["imageRef"] is not None
    assert re.fullmatch(r"ghcr\.io/willitmod/5tratmux-app:[A-Za-z0-9_.-]+@sha256:[0-9a-f]{64}", result["imageRef"])
    return result


def recipe_model(image, channel):
    return {"version": "3.7", "services": {
        "app_proxy": {"environment": {"APP_HOST": APP + "_server_1", "APP_PORT": "21222"}},
        "server": {
            "image": image, "user": "1000:1000", "init": True,
            "restart": "unless-stopped", "read_only": True,
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "pids_limit": 256, "mem_limit": "1536m", "stop_grace_period": "30s",
            "tmpfs": ["/tmp:rw,nosuid,nodev,exec,size=256m,mode=1777"],
            "ports": ["7331:7331/tcp"], "expose": ["21222"],
            "volumes": ["${APP_DATA_DIR}/data:/data"],
            "environment": {
                "MUX_PLATFORM": "umbrel", "APP_HOST": "0.0.0.0", "APP_PORT": "21222",
                "STATE_DIR": "/data/state", "MUX_OPERATOR_PASSWORD": "${APP_PASSWORD}",
                "MUX_AUTH_TRUSTED_PROXIES": "${GATEWAY_IP}", "MUX_HTTP_STRICT_HOST": "1",
                "MUX_HTTP_ALLOWED_HOSTS": "${DEVICE_DOMAIN_NAME},${DEVICE_HOSTNAME},localhost",
                "APP_VERSION": VERSIONS[channel], "APP_CHANNEL": channel,
            },
        },
    }}


def validate_recipe(model, image, channel):
    assert json.dumps(model, sort_keys=True) == json.dumps(recipe_model(image, channel), sort_keys=True), "Unreviewed MUX runtime/security model"
    return model


def validate_manifest(model, channel):
    expected = {"manifestVersion": 1, "id": APP, "name": "5tratMux" + (" DEV" if channel == "DEV" else ""),
                "version": VERSIONS[channel], "port": 21222, "icon": "icon.png", "category": "crypto",
                "developer": "WillItMod", "website": "https://5tratum.com",
                "repo": "https://github.com/WillItMod/5tratMux", "support": "https://github.com/WillItMod/5tratMux/issues",
                "dependencies": [], "permissions": [], "gallery": [], "path": "", "defaultUsername": "",
                "deterministicPassword": True, "storage": {"dataRoot": "data"}}
    text_fields = {"tagline", "description", "releaseNotes"}
    assert set(model) == set(expected) | text_fields, "Unexpected MUX manifest fields"
    assert all(model[key] == value for key, value in expected.items()), "MUX metadata/authentication/port mismatch"
    assert all(isinstance(model[key], str) and model[key].strip() for key in text_fields)


def validate_package_files(root, release):
    package = root / APP
    actual = {str(path.relative_to(package)) for path in package.rglob("*") if path.is_file() or path.is_symlink()}
    assert actual == FILES, "MUX is Umbrel-only; extra files or OS manifests are forbidden"
    assert set(release["packageFiles"]) == {APP + "/" + name for name in FILES}
    for name, identity in release["packageFiles"].items():
        path = root / name
        info = path.lstat()
        assert stat.S_ISREG(info.st_mode), "MUX package files must be regular"
        expected_mode = 0o755 if name.endswith("hooks/pre-start") else 0o644
        assert stat.S_IMODE(info.st_mode) == expected_mode
        assert identity == {"sha256": sha256(path.read_bytes()), "mode": oct(expected_mode)}
    assert sha256((package / "hooks/pre-start").read_bytes()) == HOOK_SHA256
    assert sha256((package / "icon.png").read_bytes()) == ICON_SHA256
    validate_recipe(yaml.safe_load((package / "docker-compose.yml").read_text()), release["imageRef"], release["channel"])
    validate_manifest(yaml.safe_load((package / "umbrel-app.yml").read_text()), release["channel"])


def validate_baseline(root, channel):
    baseline = BASELINES[channel]
    names = _git(root, "ls-tree", "-r", "--name-only", baseline).decode().splitlines()
    protected = [name for name in names if name.startswith("willitmod-") or
                 name.endswith(".json") and ("/" not in name or name.startswith("release-records/"))]
    assert protected and not any(name.startswith(APP + "/") for name in protected)
    changed = _git(root, "diff", "--name-only", baseline, "--", *protected).decode().splitlines()
    assert changed == [], "Preexisting app package or historical JSON changed: " + ", ".join(changed)
    old_files = {name for name in protected if name.startswith("willitmod-")}
    current_files = {str(path.relative_to(root)) for package in root.glob("willitmod-*") if package.is_dir()
                     for path in package.rglob("*") if path.is_file() or path.is_symlink()}
    assert current_files == old_files | {APP + "/" + name for name in FILES}, "Unexpected catalogue package inventory"


def validate_publication(root, release):
    publication = release["publication"]
    channel = release["channel"]
    assert publication["path"] == f"release-records/mux-umbrel-{VERSIONS[channel]}-delivery.json"
    raw = (root / publication["path"]).read_bytes()
    assert PUBLICATION_LOCKS[channel] is not None
    assert sha256(raw) == publication["sha256"] == PUBLICATION_LOCKS[channel], "Unreviewed MUX delivery receipt"
    proof = json.loads(raw)
    assert proof["schemaVersion"] == 1 and proof["result"] == "PASS"
    assert (proof["sourceRevision"], proof["sourceTree"], proof["imageRef"]) == (SOURCE, TREE, release["imageRef"])
    assert proof["anonymousIndexAndBothPlatformsVerified"] is True
    assert set(proof["platforms"]) == {"amd64", "arm64"}
    for row in proof["platforms"].values():
        assert DIGEST.fullmatch(row["manifestDigest"]) and DIGEST.fullmatch(row["configDigest"])
        assert SHA256.fullmatch(row["protectedExecutableSHA256"])
        assert row["noApplicationPythonSources"] is True and row["noSourceMaps"] is True
        assert row["nativeStartupVerified"] is True and row["operatorAuthenticationVerified"] is True
        assert row["httpHealthVersion"] == VERSIONS[channel]
    assert set(proof["umbrelQualification"]) == {"1.7.4", "2.0.0"}
    for row in proof["umbrelQualification"].values():
        assert row["result"] == "PASS" and row["architecture"] == "amd64"
        assert row["nativeUpdateStopStartPersistenceVerified"] is True
        assert SHA256.fullmatch(row["receiptSHA256"]) and isinstance(row["receipt"], str) and row["receipt"]
    return proof


def validate(root=ROOT, *, check_baseline=False):
    release = record(root)
    validate_package_files(root, release)
    # This exact historical comparison admits the initial addition. It is an
    # explicit release step, never a permanent freeze of unrelated app updates.
    if check_baseline:
        validate_baseline(root, release["channel"])
    validate_publication(root, release)
    return release


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-baseline", action="store_true",
                        help="Initial release only: require every preexisting app and record to match its frozen baseline")
    arguments = parser.parse_args()
    release = validate(check_baseline=arguments.check_baseline)
    print(json.dumps({"status": "PASS", "channel": release["channel"], "version": release["version"],
                      "image": release["imageRef"], "initialCatalogueBaselineChecked": arguments.check_baseline}))
