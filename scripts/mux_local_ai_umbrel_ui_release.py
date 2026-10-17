"""Additive 0.9.83 admission for the two-file Local AI visibility correction.

The compiled application and companion retain their independently locked 0.9.82
qualification. New source, image and delivery locks require actual overlay and
UI receipts; an editable record cannot authorize itself.
"""
import copy
import json
from pathlib import Path
import re
import stat

import yaml
import mux_local_ai_umbrel_release as previous

ROOT = Path(__file__).resolve().parents[1]
APP = previous.APP
RECORD_NAME = "MUX-UMBREL-0.9.83-2026-10-17.json"
VERSIONS = {"DEV": "0.9.83-dev", "MAIN": "0.9.83"}
ADMISSION_LOCKS = {'DEV': 'cd536d0b9c0610cb356d58ebf5246267771171312e45d22df4ba66c8501966b2', 'MAIN': 'f5bc3203a6d8c1490bf4a1babef14a7e68d8102b2a2ee876090f4c8ea3e57de5'}
DELIVERY_LOCKS = {'DEV': 'dfa15c2174636e56660395814f37dbf5362787490efd638a50f201d3cce3e871', 'MAIN': '82a99a9a934a3456777d9b11d0c97f5566c206cd0217ebc6716a57665a3c9e39'}
IMAGE_REFS = {"DEV": "ghcr.io/willitmod/5tratmux-app:0.9.83-umbrel-dev@sha256:3e2067975c7b29d12a075a7947d3bd238db0702bc4ba826ffc2e1e2479a329e3",
    "MAIN": "ghcr.io/willitmod/5tratmux-app:0.9.83-umbrel@sha256:483de527d1de5b50a52b466f7875d31f3a2251177fd7bcff80dbf63ae06c2794"}
PLATFORM_PINS = {
    "MAIN": {"amd64": {"manifestDigest": "sha256:f40bb610d07b440c79b99b193cbe12812fbde99c25ed028c03506eec950ab439", "configDigest": "sha256:af91c1c26ed8c2e746e9d90abc556829c5d69dc2d5747d80a70427516a2dbfbe"},
        "arm64": {"manifestDigest": "sha256:cd886ac4d6c9beb69f7b55ca32a000a4746db4f6be81109e1c17c7efe819cdc9", "configDigest": "sha256:250fe991f1a70fafddd411ad528480bc09468daeeae137df35a5e8105c235bd8"}},
    "DEV": {"amd64": {"manifestDigest": "sha256:ee985273cfa1c574375cdf3bc61ff8b54b078a2679e63fe632822f507f8dfd3d", "configDigest": "sha256:7cb6524edc761c1a012f9f110725ebb7f5353f43bec6cc403766d4bb00743a07"},
        "arm64": {"manifestDigest": "sha256:526003d523a38f45bc62d70a3ceb6662027f92a9544cbfa3742a4d101dd6956d", "configDigest": "sha256:e87de399a12f1d52d32450bbad3b5c2e79fa311621ac06bcb449c80964d0f47b"}}}
UI_SOURCE = {"sourceRevision": "abe3c818c74102eebb971c3e5af1aeb39f408d3d",
    "sourceTree": "c8b3d996be016c5f88b6aed8fc7bb7c52dc55825",
    "changedFiles": {"static/index.html": "e29bcfe2d4628f13b27cac3334329112c3e257e1bdc54e679965b22dee2db656",
        "static/standalone-ui.css": "8439fa0a36fde0e2ea3bc690136de522195417c146b11b534c752e322a3d0456"}}
STATIC_FILES = {"app/" + key: value for key, value in UI_SOURCE["changedFiles"].items()}
SOURCE_REGRESSION_SHA256 = "e1adb52bfeaad596034f36d707fe8b85e034488a1f58f68650587360d2ebcb0a"
OVERLAY_REVIEW_SHA256 = "bfd176875766731c9f30d94d701d705f162a73edd2da053dfb46a965a63e94c5"
OVERLAY_PATHS = {"app/static/index.html", "app/static/standalone-ui.css"}
SOURCE_PATHS = {"static/index.html", "static/standalone-ui.css"}
PACKAGE_TRANSFORM = "qualified-0.9.82-image-and-version-with-UI-release-notes-only"
CONFIG_LABEL = "com.5tratmux.ui-source"
require = previous.require
sha256 = previous.sha256
locked_json = previous.locked_json


def referenced(root, reference):
    require(set(reference) == {"path", "sha256"}, "Exact retained evidence reference required")
    require(reference["path"].startswith("release-records/"), "Evidence must be retained with the release")
    return locked_json(root, reference["path"], reference["sha256"])


def canonical_layer(descriptor):
    # Docker's static overlay exporter may change only the format label while
    # retaining the exact compressed/uncompressed content digest and size.
    result = dict(descriptor)
    aliases = {"application/vnd.docker.image.rootfs.diff.tar": "application/vnd.oci.image.layer.v1.tar",
        "application/vnd.docker.image.rootfs.diff.tar.gzip": "application/vnd.oci.image.layer.v1.tar+gzip"}
    result["mediaType"] = aliases.get(result["mediaType"], result["mediaType"])
    return result


def predecessor(root):
    old = previous.record(root)
    # Verify the frozen historical evidence, without pretending the current UI
    # package is the old recipe or repeating model execution.
    previous.validate_delivery(root, old)
    return old


def record(root=ROOT):
    path = root / RECORD_NAME
    require(stat.S_ISREG(path.lstat().st_mode), "Release record must be regular")
    row = json.loads(path.read_bytes())
    channel = row["channel"]
    require(channel in VERSIONS and ADMISSION_LOCKS[channel] is not None,
            "0.9.83 publication has not been independently finalized")
    require(sha256(path.read_bytes()) == ADMISSION_LOCKS[channel], "Unreviewed 0.9.83 record")
    old = predecessor(root)
    require(old["channel"] == channel and row["schemaVersion"] == 1 and row["status"] == "qualified"
            and row["appId"] == APP and row["version"] == VERSIONS[channel], "Successor identity mismatch")
    require(row["predecessor"] == {"record": previous.RECORD_NAME,
            "sha256": previous.ADMISSION_LOCKS[channel], "delivery": old["publication"]},
            "The exact qualified 0.9.82 record and delivery must remain intact")
    require(UI_SOURCE is not None and row["uiSource"] == UI_SOURCE
            and all(previous.SHA1.fullmatch(UI_SOURCE[k]) for k in ("sourceRevision", "sourceTree"))
            and set(UI_SOURCE["changedFiles"]) == SOURCE_PATHS,
            "Exactly the reviewed UI source commit and two source files are required")
    require(STATIC_FILES is not None and row["staticFiles"] == STATIC_FILES
            and set(STATIC_FILES) == OVERLAY_PATHS
            and all(previous.SHA256.fullmatch(value) for value in STATIC_FILES.values()),
            "Exact delivered UI bytes require independent review")
    require(row["compiledApplicationSource"] == previous.APPLICATION_SOURCE
            and row["localAIImageRef"] == old["localAIImageRef"]
            and row["localAIPlatforms"] == old["localAIPlatforms"],
            "Compiled application and both companion identities must remain unchanged")
    require(row["packageBaseProducer"] == {key: old[key] for key in
            ("packageProducerSourceRevision", "packageProducerSourceTree", "packageProducerInputs")}
            and row["packageTransformation"] == PACKAGE_TRANSFORM,
            "The existing producer is the package base, not a new runtime build")
    tag = "0.9.83-umbrel" + ("-dev" if channel == "DEV" else "")
    require(IMAGE_REFS[channel] is not None and row["imageRef"] == IMAGE_REFS[channel]
            and re.fullmatch(r"ghcr\.io/willitmod/5tratmux-app:" + tag + r"@sha256:[0-9a-f]{64}", row["imageRef"]),
            "Exact independently admitted successor image required")
    require(row["platforms"] == PLATFORM_PINS[channel], "Both exact reviewed published architectures must remain supported")
    for platform in row["platforms"].values():
        require(set(platform) == {"manifestDigest", "configDigest"}
                and all(previous.DIGEST.fullmatch(value) for value in platform.values()), "Immutable platform identities required")
    return row, old


def validate_package(root, row, old):
    app = root / APP
    require({str(p.relative_to(app)) for p in app.rglob("*") if p.is_file() or p.is_symlink()}
            == previous.recipe.FILES, "Only the existing five Umbrel package files are allowed")
    require(set(row["packageFiles"]) == set(old["packageFiles"]), "No new package paths are allowed")
    for name, identity in row["packageFiles"].items():
        file = root / name
        mode = 0o755 if name.endswith("hooks/pre-start") else 0o644
        require(stat.S_ISREG(file.lstat().st_mode) and stat.S_IMODE(file.stat().st_mode) == mode
                and identity == {"sha256": sha256(file.read_bytes()), "mode": oct(mode)}, "Package bytes or modes changed")
        if name.endswith(("hooks/pre-start", "icon.png", "data/.gitkeep")):
            require(identity == old["packageFiles"][name], "Hook, artwork and data placeholder must remain exact")
    expected = previous.recipe.recipe_model(old["imageRef"], old["localAIImageRef"], old["channel"])
    expected["services"]["server"]["image"] = row["imageRef"]
    expected["services"]["server"]["environment"]["APP_VERSION"] = row["version"]
    require(yaml.safe_load((app / "docker-compose.yml").read_text()) == expected,
            "Only the APP image and APP_VERSION may change in the qualified recipe")
    manifest = yaml.safe_load((app / "umbrel-app.yml").read_text())
    expected = previous.recipe.manifest_model(row["channel"])
    expected["version"] = row["version"]
    notes = manifest.get("releaseNotes")
    require(isinstance(notes, str) and notes.strip(), "UI correction release notes are required")
    expected["releaseNotes"] = notes
    require(manifest == expected, "Only manifest version and release notes may change")


def validate_overlay(root, evidence, row, old, architecture, verification):
    proof = verification["platforms"][architecture]
    base_manifest = referenced(root, evidence["baseManifest"])
    manifest = referenced(root, evidence["manifest"])
    base_config = referenced(root, evidence["baseConfiguration"])
    config = referenced(root, evidence["configuration"])
    for ref, digest in ((evidence["baseManifest"], old["platforms"][architecture]["manifestDigest"]),
            (evidence["manifest"], row["platforms"][architecture]["manifestDigest"]),
            (evidence["baseConfiguration"], old["platforms"][architecture]["configDigest"]),
            (evidence["configuration"], row["platforms"][architecture]["configDigest"])):
        require("sha256:" + ref["sha256"] == digest, "Actual raw OCI object bytes must match immutable descriptors")
    require(base_manifest["config"]["digest"] == old["platforms"][architecture]["configDigest"]
            and manifest["config"]["digest"] == row["platforms"][architecture]["configDigest"], "Manifest/config binding mismatch")
    require({key: proof[key] for key in ("manifestDigest", "configDigest")} == row["platforms"][architecture]
            and proof["baseManifestDigest"] == old["platforms"][architecture]["manifestDigest"]
            and proof["baseConfigDigest"] == old["platforms"][architecture]["configDigest"], "Actual overlay audit identities differ")
    require([canonical_layer(layer) for layer in manifest["layers"][:-1]]
            == [canonical_layer(layer) for layer in base_manifest["layers"]]
            and len(manifest["layers"]) == len(base_manifest["layers"]) + 1,
            "The complete qualified parent layers must remain an exact prefix")
    require(base_config["architecture"] == config["architecture"] == architecture
            and base_config["os"] == config["os"] == "linux", "No emulation may be relabelled as another image architecture")
    expected = copy.deepcopy(base_config["config"])
    environment = expected["Env"]
    require(sum(v.startswith("APP_VERSION=") for v in environment) == 1, "The qualified base must contain one version environment entry")
    expected["Env"] = ["APP_VERSION=" + row["version"] if v.startswith("APP_VERSION=") else v for v in environment]
    expected.setdefault("Labels", {}).update({"org.opencontainers.image.version": row["version"],
        CONFIG_LABEL: row["uiSource"]["sourceRevision"]})
    require(config["config"] == expected, "Only APP_VERSION and the two reviewed image labels may change")
    ignore = {"created", "history", "rootfs", "config"}
    require({k: v for k, v in config.items() if k not in ignore}
            == {k: v for k, v in base_config.items() if k not in ignore}, "Other OCI configuration metadata changed")
    require(config["history"][:len(base_config["history"])] == base_config["history"], "Qualified image history prefix changed")
    require(config["rootfs"]["type"] == base_config["rootfs"]["type"] == "layers"
            and config["rootfs"]["diff_ids"][:-1] == base_config["rootfs"]["diff_ids"]
            and len(config["rootfs"]["diff_ids"]) == len(base_config["rootfs"]["diff_ids"]) + 1,
            "The root filesystem must append exactly one UI layer")
    require(proof["overlayLayerDigest"] == manifest["layers"][-1]["digest"]
            and all(proof[k] is True for k in ("baseLayerPrefixUnchanged", "baseRootfsPrefixUnchanged",
                "onlyTwoWebFilesChanged", "onlyVersionAndUiSourceConfigChanges", "userEntrypointPortsVolumesUnchanged",
                "overlayDiffIDVerified", "layerMediaTypeOnlyOciDockerAliasConversion"))
            and set(verification["overlayFiles"]) == OVERLAY_PATHS,
            "Actual appended layer must contain only the two reviewed regular UI files")
    for name, item in verification["overlayFiles"].items():
        require(item["sha256"] == row["staticFiles"][name]
                and item["mode"] == "0o644" and item["uid"] == item["gid"] == 0,
                "UI bytes/mode/ownership must match the reviewed overlay")


def validate_delivery(root, row, old):
    channel = row["channel"]
    ref = row["publication"]
    require(DELIVERY_LOCKS[channel] is not None and ref == {
        "path": f"release-records/mux-umbrel-{VERSIONS[channel]}-delivery.json", "sha256": DELIVERY_LOCKS[channel]},
        "Independently reviewed UI delivery lock required")
    delivery = referenced(root, ref)
    require(delivery["kind"] == "qualified-two-file-UI-overlay" and delivery["result"] == "PASS"
            and delivery["channel"] == channel and delivery["imageRef"] == row["imageRef"]
            and delivery["uiSource"] == row["uiSource"] and delivery["staticFiles"] == row["staticFiles"]
            and delivery["predecessor"] == row["predecessor"], "Reviewed UI delivery identity mismatch")
    require(delivery["runtimeQualification"] == {"scope": "unchanged-qualified-0.9.82-components-and-evidence",
            "evidence": old["publication"], "fullRuntimeQualificationRepeated": False},
            "Inherited qualification must be explicit and retain the original failures and limitations")
    for name, image_ref, platforms in (("baseIndex", old["imageRef"], old["platforms"]),
            ("index", row["imageRef"], row["platforms"])):
        reference = delivery[name]
        require(image_ref.rsplit("@sha256:", 1)[1] == reference["sha256"], "Actual raw public index must match the image reference")
        index = referenced(root, reference)
        require(len(index["manifests"]) == 2, "Exactly two supported platform descriptors required")
        descriptors = {entry["platform"]["architecture"]: entry for entry in index["manifests"]}
        require(set(descriptors) == {"amd64", "arm64"}
                and all(descriptors[arch]["platform"]["os"] == "linux"
                    and descriptors[arch]["digest"] == platforms[arch]["manifestDigest"] for arch in descriptors),
                "Actual public index must bind both reviewed platform manifests")
    verification = referenced(root, delivery["overlayVerification"])
    require(verification["result"] == "PASS" and verification["channel"] == channel
            and verification["version"] == row["version"] and verification["sourceRevision"] == UI_SOURCE["sourceRevision"]
            and verification["baseImageRef"] == old["imageRef"] and verification["imageRef"] == row["imageRef"]
            and set(verification["platforms"]) == {"amd64", "arm64"}, "Actual anonymous overlay graph audit required")
    require(delivery["independentOverlayReview"]["sha256"] == OVERLAY_REVIEW_SHA256,
            "Exact independent four-platform overlay review required")
    independent = referenced(root, delivery["independentOverlayReview"])
    require(independent["status"] == "UI083_MAIN_DEV_FOUR_PLATFORM_OVERLAY_RAW_GRAPH_REVIEW_PASS"
            and independent["sourceRevision"] == UI_SOURCE["sourceRevision"]
            and independent["sourceTree"] == UI_SOURCE["sourceTree"], "Independent overlay review source mismatch")
    require(set(delivery["platforms"]) == {"amd64", "arm64"}, "Both actual overlay architecture proofs required")
    for architecture, proof in delivery["platforms"].items():
        validate_overlay(root, proof, row, old, architecture, verification)
    smoke = referenced(root, delivery["nativeUiSmoke"])
    require(smoke["schemaVersion"] == 1 and smoke["result"] == "PASS"
            and smoke["sourceRevision"] == UI_SOURCE["sourceRevision"] and smoke["engineArchitecture"] == "arm64"
            and smoke["scope"] == "protected-APP-startup-auth-two-webfiles-no-runtime"
            and smoke["allOwnContainersRemoved"] is True and smoke["allOwnVolumesRemoved"] is True
            and len(smoke["rows"]) == 4, "Actual bounded four-image startup/authentication receipt required")
    seen = set()
    for tested in smoke["rows"]:
        tested_channel, architecture = tested["channel"], tested["architecture"]
        seen.add((tested_channel, architecture))
        require(tested["result"] == "PASS" and tested["imageRef"] == IMAGE_REFS[tested_channel]
                and {k: tested[k] for k in ("manifestDigest", "configDigest")} == PLATFORM_PINS[tested_channel][architecture]
                and tested["executionMode"] == ("native-arm64" if architecture == "arm64" else "qemu-amd64-on-arm64")
                and tested["version"] == tested["healthVersion"] == VERSIONS[tested_channel]
                and all(tested[k] == 200 for k in ("healthHttp", "loginHttp", "authenticatedAuthStatusHttp", "authenticatedStatusHttp"))
                and tested["unauthStatusHttp"] == 401
                and {"app/static/" + name: item["sha256"] for name, item in tested["servedFiles"].items()} == STATIC_FILES
                and tested["runtimeStarted"] is False and tested["modelStarted"] is False and tested["cleanupRemoved"] is True,
                "Actual image/served bytes/auth result and truthful native-versus-emulated scope required")
    require(seen == {(channel, arch) for channel in VERSIONS for arch in ("amd64", "arm64")}, "All four actual startup rows required")
    require(SOURCE_REGRESSION_SHA256 is not None and delivery["sourceRegression"]["sha256"] == SOURCE_REGRESSION_SHA256,
            "Exact reviewed browser source regression receipt required")
    regression = referenced(root, delivery["sourceRegression"])
    require(regression["apiCalls"] == 0 and regression["modelsOrRuntimeStarted"] is False
            and regression["packagedMinifiedBuildOrHostClaimed"] is False, "Source fixture must not masquerade as packaged or host QA")
    cases = {case["name"]: case for case in regression["results"]}
    require(set(cases) == {"before-managed", "after-managed", "after-unsupported", "after-native"}
            and cases["before-managed"]["settingsLocalAi"]["display"] == "none"
            and all(cases[name]["settingsLocalAi"] == {"hidden": False, "display": "grid", "rectCount": 1}
                    for name in ("after-managed", "after-native"))
            and cases["after-unsupported"]["settingsLocalAi"] == {"hidden": True, "display": "none", "rectCount": 0}
            and all(case["settingsLicence"]["display"] == "grid" for case in cases.values()),
            "Reviewed source CSS must reveal managed Local AI and retain the unsupported-platform restriction")
    return delivery


def validate(root=ROOT):
    row, old = record(root)
    validate_package(root, row, old)
    validate_delivery(root, row, old)
    return row


if __name__ == "__main__":
    print(json.dumps(validate()))
