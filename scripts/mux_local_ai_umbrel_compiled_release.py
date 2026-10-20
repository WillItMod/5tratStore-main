"""Closed 0.9.85 UI refresh over the qualified 0.9.84 compiled APP; retain 0.9.83 and companion history.

Public image and publication locks are deliberately unset during preparation.
Source/compiled smoke evidence is distinct from unchanged companion inference
qualification. A native signed archive never substitutes for an Umbrel image.
"""
import datetime
import json
from pathlib import Path
import stat

import mux_local_ai_umbrel_ui_release as previous

ROOT = Path(__file__).resolve().parents[1]
APP = previous.APP
RECORD_NAME = "MUX-UMBREL-0.9.85-2026-10-20.json"
VERSIONS = {"DEV": "0.9.85-dev", "MAIN": "0.9.85"}
BASE_VERSIONS = {"DEV": "0.9.84-dev", "MAIN": "0.9.84"}
UI_SOURCE = {"sourceRevision": "e61719f4d357397a9bfd14a4e258973430bbd7e3",
             "sourceTree": "7d5d6eb45cbb697cad751b2c91ab51e8aa58ac75"}
INDEX_SHA256 = "b79e371ef85cae47bed69450296f032baa777609d7cc51918ba431166184ae86"
SOURCE = {"sourceRevision": "e0fcc8f0c11a5d923d5220b462d06b466c69037d",
          "sourceTree": "f194309a9ff33415e9709c4be59a0d206d512a07"}
ADMISSION_LOCKS = {'DEV': '722b23f2a81cdf9c8aef5a6f39c5285b262574ff0d9b0dc1604613b5827cc5aa', 'MAIN': 'd051673d3ea03df7126812f934735cdc074a198bd7b042fc2eaff872b9171b73'}
DELIVERY_LOCKS = {'DEV': '3017e33bd53708f3a095fa49fb6bf7ff67b3fa1e5570b4466868d608161fd582', 'MAIN': 'dbde0205b55a02f05c63c3369934049cd2e89671b13b6ebd226bd49ce7356896'}
IMAGE_REFS = {'DEV': 'ghcr.io/willitmod/5tratmux-app:0.9.85-umbrel-dev@sha256:d1b051d04eb00aed736bc227d560487d6e572a6207dbfe1b192c8759e49438f7', 'MAIN': 'ghcr.io/willitmod/5tratmux-app:0.9.85-umbrel@sha256:4209326af3d4810609dd9c51ca2dc2a0fd761df9c6d49f800a75fef28b12756f'}
PLATFORM_PINS = {'DEV': {'amd64': {'manifestDigest': 'sha256:143d25b14035158644fe24095b4f649a687e0ef60066a6fe3f81d3a2db37084f', 'configDigest': 'sha256:f73efecd569f8c0bb8b4ed34386c06155ac344619931dbedc5053ac269b40c45'}, 'arm64': {'manifestDigest': 'sha256:0030cc186899fede7ebcad30943d71fee032cc88f0bf063f9e3ce82049be23c3', 'configDigest': 'sha256:b598b147307d906906d716fde5416400f59a632934e0ce02da958494fb495b7a'}}, 'MAIN': {'amd64': {'manifestDigest': 'sha256:612b71ee250b455364e3e9d092ee8ca18fcdc0d1f618cb16cdcc1c9bc7e6fad2', 'configDigest': 'sha256:71cc15c2e95e7b4b3536c35b2f28f5c5a8a45c72ed25337fd2b5232df59cb709'}, 'arm64': {'manifestDigest': 'sha256:44e624f7e5e535006267ac3effc618a84d30056487951700560524de7367b02d', 'configDigest': 'sha256:1f8a3145b935baad11e5f14a97f5d04de2cc6924c8ba2839a4e941bf2873aa97'}}}
PUBLIC_GRAPH_LOCKS = {'DEV': '5569bc611f99e686c939515efdfedd508e65a90063121109055558024f73fdaa', 'MAIN': 'eaf540ae419758635d508a17463cea1b1737fd148e0c3be5b64f2c036a9b29fe'}
SMOKE_LOCKS = {
    "arm64": "570e677801f1637175f1176af05140f14e6cd82ad80b2c4540deb62b4111eb9d",
    "amd64": "802e7a9f5d2103835b83bc8c736ddab5d97ad0c4e56261d1c0ba28f993b9e6d2"}
BINARIES = {
    "arm64": "c1b769ed7ad46ec79582c6033d5d22c7072d0df6653b037823d15ff887e0d6f9",
    "amd64": "9f662fe9c81ceb6e2086830b96942d0eab2b00cfa177212cf3d1675a2e012e3c"}
ASSETS = {"/app.css": "a426d88ee14ff4d5baf87392be2e992d2a8a9c63257d09f04ea2e26d1bcedccb",
          "/app.js": "bdb37ef7a575df021f1f041762939ca19fc3666aac581e85715c38c3ae380e8a",
          "/index.html": "e29bcfe2d4628f13b27cac3334329112c3e257e1bdc54e679965b22dee2db656"}
require = previous.require
sha256 = previous.sha256


def referenced(root, reference):
    require(set(reference) == {"path", "sha256"}, "Exact retained evidence reference required")
    parts = Path(reference["path"]).parts
    require(len(parts) == 2 and parts[0] == "release-records" and parts[1] not in {".", ".."}
            and previous.previous.SHA256.fullmatch(reference["sha256"]), "Use one retained release-records file")
    directory, path = root / parts[0], root / reference["path"]
    require(not directory.is_symlink() and stat.S_ISREG(path.lstat().st_mode), "Evidence must be a regular retained file")
    require(sha256(path.read_bytes()) == reference["sha256"], "Retained evidence bytes changed")
    return json.loads(path.read_bytes())


def predecessor(root):
    old, older = previous.record(root)
    previous.validate_delivery(root, old, older)
    return old


def validate_package(root, row, old):
    # The recipe factory deliberately retains its qualified 0.9.82 input.
    # Its output is checked with only the new APP image and version replaced.
    template = dict(old)
    template["imageRef"] = previous.previous.APPLICATION_IMAGE_REFS[old["channel"]]
    previous.validate_package(root, row, template)


def record(root=ROOT):
    path = root / RECORD_NAME
    require(stat.S_ISREG(path.lstat().st_mode), "Release record must be regular")
    row = json.loads(path.read_bytes())
    channel = row["channel"]
    require(channel in VERSIONS and ADMISSION_LOCKS[channel] is not None,
            "0.9.85 publication has not been independently finalized")
    require(sha256(path.read_bytes()) == ADMISSION_LOCKS[channel], "Unreviewed 0.9.85 release record")
    old = predecessor(root)
    require(row["schemaVersion"] == 1 and row["status"] == "qualified" and row["appId"] == APP
            and channel == old["channel"] and row["version"] == VERSIONS[channel], "Successor identity mismatch")
    require(row["predecessor"] == {"record": previous.RECORD_NAME,
            "sha256": previous.ADMISSION_LOCKS[channel], "delivery": old["publication"]}, "Retain exact qualified 0.9.83 history")
    require(row["compiledApplicationSource"] == SOURCE, "The new compiled application must bind reviewed 0.9.84 source")
    require(row["localAIImageRef"] == old["localAIImageRef"] and row["localAIPlatforms"] == old["localAIPlatforms"]
            and row["packageBaseProducer"] == old["packageBaseProducer"], "Companion and existing package producer must remain exact")
    require(IMAGE_REFS[channel] is not None and row["imageRef"] == IMAGE_REFS[channel]
            and PLATFORM_PINS[channel] is not None and row["platforms"] == PLATFORM_PINS[channel],
            "Actual independently admitted public index and platform pins required")
    require(row["uiSource"] == UI_SOURCE, "Exact reviewed cache revision source required")
    tag = "0.9.85-umbrel" + ("-dev" if channel == "DEV" else "")
    import re
    require(re.fullmatch(r"ghcr\.io/willitmod/5tratmux-app:" + tag + r"@sha256:[0-9a-f]{64}", row["imageRef"])
            and set(row["platforms"]) == {"amd64", "arm64"}, "Both immutable protected Umbrel architectures required")
    for pin in row["platforms"].values():
        require(set(pin) == {"manifestDigest", "configDigest"}
                and all(previous.previous.DIGEST.fullmatch(value) for value in pin.values()), "Immutable platform identities required")
    return row, old


def validate_smoke(root, reference, architecture, row, producer, audit):
    require(reference["sha256"] == SMOKE_LOCKS[architecture], "Exact original compiled smoke receipt required")
    smoke = referenced(root, reference)
    require(smoke["schemaVersion"] == 1 and smoke["kind"] == "compiled-mux084-disposable-smoke-v2"
            and smoke["result"] == "PASS" and smoke["errorCode"] is None
            and {key: smoke[key] for key in SOURCE} == SOURCE, "Actual source-bound compiled smoke required")
    require(smoke["cleanup"] == {"complete": True, "forceOrPruneUsed": False, "unresolvedOwnedResourceNames": []}
            and all(smoke[k] is False for k in ("actualLiveProviderHealthOrInferenceQualified",
                "routingLicenceBypassOrGrantFabrication", "nativeOrUmbrelProductionTargetActions", "publicationAuthorized")),
            "Smoke cleanup and model-free qualification limitations must remain explicit")
    candidates = [item for item in smoke["rows"] if item["platform"] == "umbrel"
                  and item["architecture"] == architecture and item["version"] == BASE_VERSIONS[row["channel"]]]
    require(len(candidates) == 1, "Exactly one actual channel/platform smoke row required")
    tested = candidates[0]
    require(tested["imageId"] == producer.get("imageId", producer["imageConfigDigest"]) and tested["binarySha256"] == BINARIES[architecture]
            == audit["protectedExecutableSHA256"] and tested["assetSha256"] == ASSETS
            and tested["observedHttpVersion"] == BASE_VERSIONS[row["channel"]], "Smoke must execute the delivered compiled wrapper")
    require(tested["unauthStatus"] == 401 and tested["ownerAuthenticatedWhereRequired"] is True
            and tested["policyPostStatus"] == 402 and tested["compiledAttackMutationQualified"] is False
            and tested["providerCanaryRequests"] == 0 and tested["rawProviderPrivacyVerified"] is True
            and tested["noModelOrMiningCallsPerformed"] is True and tested["hostPublishedPorts"] == []
            and tested["httpClientScope"] == "same-owned-internal-network", "Actual auth, licence and bounded smoke scope required")
    provider = tested["provider"]
    require(provider["provider"] == {"id": "ollama", "label": "Ollama", "model": "phi4:latest",
                "revision": 3, "configured": True, "configurationScope": "provider_and_model_only"}
            and provider["activity"]["state"] == "idle" and provider["activity"]["scope"] == "mux_mission_review"
            and provider["activity"]["inferenceConfirmed"] is False and provider["lastReview"] is None
            and provider["reachability"] == {"state": "not_checked", "checkedAt": None}
            and provider["metrics"] == {"available": False}
            and provider["capabilities"] == {"test": False, "control": False, "discovery": False}, "Selected provider scope must not imply health or inference")
    observed = datetime.datetime.fromisoformat(provider["activity"]["observedAt"].replace("Z", "+00:00"))
    require(observed.utcoffset() == datetime.timedelta(0), "Actual provider observation must be timestamped UTC")
    state = tested["syntheticStatePreserved"]
    workers = {worker["id"]: worker for worker in state["workers"]}
    require(set(workers) == {"qa-ai-one", "qa-manual-two"}
            and workers["qa-ai-one"]["mode"] == "ai-controlled" and workers["qa-ai-one"]["aiManaged"] is True
            and workers["qa-ai-one"]["muxAttackExcluded"] is False
            and workers["qa-manual-two"]["mode"] == "allocation" and workers["qa-manual-two"]["muxAttackExcluded"] is True
            and all(worker["allocations"] == {"qa-offline-sha256": 100}
                    and worker["targetId"] == "qa-offline-sha256" for worker in workers.values())
            and state["plans"] == {"qa-ai-one": {"allocations": {"qa-offline-sha256": 100}, "missionId": "qa-disabled", "muxAttack": False}}
            and state["policies"] == {"worker:qa-ai-one": {"excluded": False, "revision": 1},
                                    "worker:qa-manual-two": {"excluded": True, "revision": 2}}
            and state["provider"] == {"aiEnabled": False, "aiMissions": [], "aiModel": "phi4:latest",
                                     "aiProvider": "ollama", "aiProviderRevision": 3},
            "Compiled smoke must retain independent attack policy and ordinary AI/manual allocations")


def validate_platform(root, evidence, architecture, row):
    pin = row["platforms"][architecture]
    manifest, config = referenced(root, evidence["manifest"]), referenced(root, evidence["configuration"])
    require("sha256:" + evidence["manifest"]["sha256"] == pin["manifestDigest"]
            and "sha256:" + evidence["configuration"]["sha256"] == pin["configDigest"]
            and manifest["config"]["digest"] == pin["configDigest"], "Raw published manifest/config bytes must bind exact pins")
    require(config["os"] == "linux" and config["architecture"] == architecture
            and manifest["config"]["size"] == (root / evidence["configuration"]["path"]).stat().st_size,
            "Actual published architecture and config descriptor size required")
    producer = referenced(root, evidence["wrapperProducer"])
    build = referenced(root, evidence["compiledBaseProducer"])
    audit = referenced(root, evidence["allLayerAudit"])
    for receipt in (producer, build, audit):
        require({"sourceRevision": receipt["sourceCommit"], "sourceTree": receipt["sourceTree"]} == SOURCE,
                "Compiled and wrapper provenance must name the new exact source")
    base_audit = referenced(root, evidence["compiledBaseAudit"])
    base_manifest = referenced(root, evidence["baseManifest"])
    base_config = referenced(root, evidence["baseConfiguration"])
    require(build["buildSucceeded"] is True and producer["buildSucceeded"] is True
            and audit["role"] == "umbrel" and producer["version"] == BASE_VERSIONS[row["channel"]]
            and producer["wrapperCompilerInvoked"] is False
            and producer["sourceArchiveSHA256"] == build["sourceArchiveSHA256"], "Original qualified compiled wrapper required")
    require(audit["result"] == base_audit["result"] == "PASS"
            and audit["scope"] == "archive-protection-only"
            and audit["producerReceiptSHA256"] == evidence["wrapperProducer"]["sha256"]
            and audit["archiveSHA256"] == producer["archiveSHA256"]
            and audit["configDigest"] == producer["imageConfigDigest"]
            and "sha256:" + evidence["baseConfiguration"]["sha256"] == audit["configDigest"]
            and base_manifest["config"]["digest"] == audit["configDigest"]
            and audit["protectedExecutableSHA256"] == base_audit["protectedExecutableSHA256"] == BINARIES[architecture]
            and audit["orderedRootfsDiffIDs"] == base_audit["orderedRootfsDiffIDs"]
            and audit["staticHashes"] == base_audit["staticHashes"]
            and all(audit[k] is True for k in ("allDistributedLayersAudited", "allLayerDigestsVerified",
                "noApplicationPrivateKeyMaterial", "noApplicationPythonSources", "noSourceMaps"))
            and audit["liveRuntimeQualified"] is False, "Original protected wrapper and compiled base must correlate")
    require(base_config["rootfs"] == {"type": "layers", "diff_ids": audit["orderedRootfsDiffIDs"]}
            and config["rootfs"]["type"] == "layers"
            and config["rootfs"]["diff_ids"][:-1] == audit["orderedRootfsDiffIDs"]
            and len(config["rootfs"]["diff_ids"]) == len(audit["orderedRootfsDiffIDs"]) + 1
            and [previous.canonical_layer(x) for x in manifest["layers"][:-1]]
                == [previous.canonical_layer(x) for x in base_manifest["layers"]],
            "One UI layer must retain the full qualified base")
    import copy
    expected = copy.deepcopy(base_config["config"])
    expected["Env"] = ["APP_VERSION=" + row["version"] if x.startswith("APP_VERSION=") else x for x in expected["Env"]]
    expected.setdefault("Labels", {}).update({"org.opencontainers.image.version": row["version"]})
    require(config["config"] == expected, "Only APP_VERSION and the version label may change")
    actual = config["config"]
    require(all(base_config["config"].get(key) == value for key, value in audit["runtimeConfig"].items()), "Published runtime config differs from archive audit")
    require(not actual.get("Volumes") and not actual.get("OnBuild") and not actual.get("Cmd"), "No additional image mounts or commands admitted")
    environment = {item.split("=", 1)[0]: item.split("=", 1)[1] for item in actual["Env"]}
    require(len(environment) == len(actual["Env"]) and environment.get("MUX_PLATFORM") == "umbrel"
            and environment.get("APP_VERSION") == row["version"] and environment.get("APP_CHANNEL") == row["channel"]
            and environment.get("STATE_DIR") == "/data/state" and actual["User"] == "1000:1000"
            and actual["Entrypoint"] == ["/app/5tratmux"] and actual["ExposedPorts"] == {"21222/tcp": {}, "7331/tcp": {}},
            "Umbrel runtime identity, version and security boundary required")
    require(all(audit["staticHashes"]["app/static" + path] == digest for path, digest in ASSETS.items()), "Audited browser bytes differ")
    validate_smoke(root, evidence["compiledSmoke"], architecture, row, producer, audit)


def validate_delivery(root, row, old):
    channel = row["channel"]
    require(DELIVERY_LOCKS[channel] is not None and row["publication"] == {
        "path": f"release-records/mux-umbrel-{VERSIONS[channel]}-delivery.json", "sha256": DELIVERY_LOCKS[channel]},
        "Independent compiled successor delivery lock required")
    delivery = referenced(root, row["publication"])
    require(delivery["kind"] == "protected-compiled-application-successor" and delivery["result"] == "PASS"
            and delivery["channel"] == channel and delivery["imageRef"] == row["imageRef"]
            and delivery["source"] == SOURCE and delivery["uiSource"] == UI_SOURCE and delivery["predecessor"] == row["predecessor"], "Compiled successor delivery identity differs")
    require(delivery["companionQualification"] == {"scope": "unchanged-local-ai-0.1.9-components-only",
            "evidence": old["predecessor"]["delivery"], "newModelInferenceClaimed": False},
            "Retain original companion qualification and its observed failures without relabelling APP qualification")
    require(delivery["index"]["sha256"] == row["imageRef"].rsplit("@sha256:", 1)[1], "Exact raw public index required")
    index = referenced(root, delivery["index"])
    graph_ref = delivery["independentPublicArchiveCorrelation"]
    require(PUBLIC_GRAPH_LOCKS[channel] is not None and graph_ref["sha256"] == PUBLIC_GRAPH_LOCKS[channel],
            "Independent public layer/archive correlation remains pending")
    graph = referenced(root, graph_ref)
    require(graph["kind"] == "mux085-public-overlay-correlation" and graph["result"] == "PASS"
            and graph["source"] == SOURCE and graph["uiSource"] == UI_SOURCE and graph["channel"] == channel and graph["imageRef"] == row["imageRef"]
            and set(graph["platforms"]) == {"amd64", "arm64"}, "Actual independently reviewed public graph correlation required")
    require(len(index["manifests"]) == 2, "Exactly two actual platform descriptors required")
    descriptors = {item["platform"]["architecture"]: item for item in index["manifests"]}
    require(set(descriptors) == set(delivery["platforms"]) == {"amd64", "arm64"}, "Both complete platform proofs required")
    for architecture, evidence in delivery["platforms"].items():
        descriptor = descriptors[architecture]
        require(descriptor["platform"]["os"] == "linux"
                and descriptor["digest"] == row["platforms"][architecture]["manifestDigest"]
                and descriptor["size"] == (root / evidence["manifest"]["path"]).stat().st_size,
                "Public index must bind each exact observed manifest")
        validate_platform(root, evidence, architecture, row)
        audit = referenced(root, evidence["allLayerAudit"])
        public_manifest = referenced(root, evidence["manifest"])
        proof = graph["platforms"][architecture]
        require(proof["manifestDigest"] == row["platforms"][architecture]["manifestDigest"]
                and proof["configDigest"] == row["platforms"][architecture]["configDigest"]
                and proof["archiveSHA256"] == audit["archiveSHA256"]
                and proof["allLayerAuditSHA256"] == evidence["allLayerAudit"]["sha256"]
                and proof["protectedExecutableSHA256"] == BINARIES[architecture]
                and proof["publicLayers"] == public_manifest["layers"]
                and proof["orderedUncompressedDiffIDs"][:-1] == audit["orderedRootfsDiffIDs"]
                and proof["overlayFiles"] == {"app/static/index.html": {"sha256": INDEX_SHA256, "mode": "0o644", "uid": 0, "gid": 0}}
                and all(proof[k] is True for k in ("allPublicBlobsDownloadedAndHashed",
                    "allPublicLayersDecompressedAndDiffIDsVerified", "auditedArchiveRootfsAndProductBytesMatch")),
                "Every public layer must be verified against the actual audited archive")
    return delivery


def validate(root=ROOT):
    row, old = record(root)
    validate_package(root, row, old)
    validate_delivery(root, row, old)
    return row


if __name__ == "__main__":
    print(json.dumps(validate()))
