"""Fail-closed 0.9.82 delivery admission; preserve the qualified 0.9.80 history.

ADMISSION_LOCKS stay unset until independently reviewed compiled multi-platform
images, actual inference and native Umbrel update receipts exist. A generated
package or editable receipt cannot authorize its own publication.
"""
import hashlib
import json
import math
from pathlib import Path
import re
import stat
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import mux_local_ai_umbrel_recipe as recipe

APP = recipe.APP
RECORD_NAME = "MUX-UMBREL-0.9.82-2026-10-16.json"
PREDECESSOR_NAME = "MUX-UMBREL-0.9.80-2026-10-16.json"
ADMISSION_LOCKS = {'DEV': '9969837502d109fe1be88ebf39c07dcaf3774082d7afd42d7ec3417fcd7b101d', 'MAIN': '5fd44715607b3962129f49c09cd011796f047ef6accbef1fc590473a37a32a23'}
DELIVERY_LOCKS = {'DEV': '25da1be5b6d882834e6cd53b7787279a30cd75a40284f73ba2f24f8bfae8168e', 'MAIN': '9441ccef7d5950ab47101c57716207fae0c0a25fc1b0ab50459b75436744527b'}
APPLICATION_SOURCE = {"sourceRevision": "138fd6cfd1b99cea858f19f39f8976015da1de1b",
                      "sourceTree": "75ed4c702490df1f168bf590ba055768c260d236"}
# APP-only public delivery was independently admitted before package QA.
# These pins do not open the companion, package or publication gates.
APPLICATION_IMAGE_REFS = {
    "DEV": "ghcr.io/willitmod/5tratmux-app:0.9.82-umbrel-dev@sha256:5eb55feec01de1a3b4bdf16027dd22a4fdf5844c83c016996eeeace0e876ca5e",
    "MAIN": "ghcr.io/willitmod/5tratmux-app:0.9.82-umbrel@sha256:9ef5ac209472b9f57cfb74eeda3e96e5a03f77747cab19a12cbfdf8abaafbe15"}
APPLICATION_AMD64_CONFIGS = {"DEV": "sha256:3cd72ad4d37a9a21ac7cca0a2cd085ea6eccc908c3a091df4af8ec40426c53bf",
    "MAIN": "sha256:73fc590eb227a54fb945ac0579b9af54b6d82db97b09a86d9be30aecddf232ba"}
# The portable AMD producer can follow the frozen application/ARM source.
# Review each actual compiled component independently before setting these.
COMPANION_SOURCE_PINS = {'amd64': {'sourceRevision': '595bd51be79995642da846afa2206d2ccb96bd08', 'sourceTree': 'fd8fdcb99068c3d7fb4185aff0260a86b43876a2'}, 'arm64': {'sourceRevision': '138fd6cfd1b99cea858f19f39f8976015da1de1b', 'sourceTree': '75ed4c702490df1f168bf590ba055768c260d236'}}
PACKAGE_PRODUCER_SOURCE = {'sourceRevision': '396c137930d27fb39251147426a70bd61307bf98', 'sourceTree': 'ec2daf28cc1920be3e83bc791e25f3e6443769cc'}
PACKAGE_PRODUCER_INPUTS = {'packaging/umbrel-local-ai-release/prepare_package.py': '7c3deed5b8aa35777d1776a6a15ce0be7217dc98d40a1e082af21e88c4cb0f1c', 'packaging/umbrel-local-ai-release/pre-start': 'fb25f9246aff606a00567ec0a0333b49397bf988b30deaff0c3da5baaaa4eb6e'}
PREDECESSOR_LOCKS = {"MAIN": "2f80bd07c6281d83fed7b98a782e03356871356fd68cbff27e811a01c03c9a5b",
                     "DEV": "3418fc3efa419895d0302da0804f76c96e56d6fcd36a45aefbb1d8cb86fec43c"}
PREDECESSOR_DELIVERY_LOCKS = {"MAIN": "053ab5acb86cb71e129b1d622b926bacfef950406b4ce844f137ad0ec485d514",
                              "DEV": "6f32f990c892b106656f036adaa5236fbf6a4ddaa6a41b3eb8b0a679bc40d080"}
HOOK_SHA256 = "fb25f9246aff606a00567ec0a0333b49397bf988b30deaff0c3da5baaaa4eb6e"
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
SHA1 = re.compile(r"[0-9a-f]{40}\Z")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
MODEL_SHA256 = "00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"
INTENT_SHA256 = "100cea9af32f231ffbb36ee57990dfe5b3c4d2aaaafecf48028288ce7fef83f6"
CORPUS_SHA256 = "701b5199b342bb5fe5f32bd367078475dc6805e768527a64d12273a73b816b24"
SEMANTIC_EVIDENCE_SHA256 = "008dfae21487e2fbe577f87aa927c4037af97d37092469ca51b0eeac8aeea98f"
RUNTIME_SHA256 = {
    "arm64": "e7a1fe417870f5bdbc826376ef1afae3986c8bb4de3dd3dce71e2ac4e2bf337b",
    # The first baseline binary failed the observed performance bound. A new
    # selected artifact needs its actual build/CPU/performance review here.
    "amd64-v2": '034a22de64cc6abf39039fcb29f3c3529c98a910c6b849b5fe15e768f2544fa4',
    "native-amd64-avx2": "6adb3cb8a59cdcdf5a2ef4ed2683220d8da818ecb89f243e02912c37b8e3553a",
}
REJECTED_EVIDENCE_SHA256 = {
    "baseline-4b-600s": "c311d5e8724be487b289615517bc0cd390fde0b0aac1f0c563b6a7ef9e559877",
    "baseline-0.8b": "d6d0b412d7ec4dac69a7e0d79ffdc20c9669d06a99c955deb3c020d29b3f8ce7",
}
SERVICE_REQUEST_BUDGET_SECONDS = {"amd64-v2": 600, "arm64": 180, "native-amd64-avx2": 180}
OPENBLAS_BINARY = "034a22de64cc6abf39039fcb29f3c3529c98a910c6b849b5fe15e768f2544fa4"
FRESH_DEV_FIRST_INTENT_LOCKS = {
    "firstHostEvidence": "d69be0973807594b5935978bbb2bcd0571900943c1ee03f6506229691827925d",
    "firstGuestEvidence": "3c6d4858a43ac255338e9f5ae53fcb8e7769622d6ccb1c20431d01fd83a53451",
    "independentFirstFailureReview": "96423a505682f67a9d195e06e51b2b3cc128a37f55cef164ec51fde33412640d",
    "explicitWarmAdmission": "36c315b7e6e832b479cd684ca0f305caf9f7bf4401284d0121d099ca7ddcfdb0",
}
FRESH_DEV_RESTART_EXPECTATION_FAILURE = "b5b82eeec80388fd3fc8bbe527947db781850bc531cbec0927e44f728916f677"
OPENBLAS_LICENCE = "190b5a9c8d9723fe958ad33916bd7346d96fab3c5ea90832bb02d854f620fcff"
OPENBLAS_NOTICES = "75701c2ed5e2a0e2b6448e7a51d410ce1b764346a7b8732f5e9f255f385e4fe5"
LLAMA_LICENCE = "94f29bbed6a22c35b992c5c6ebf0e7c92f13b836b90f36f461c9cf2f0f1d010d"
OPENBLAS_PATCH = {"path": "common/common.h",
    "beforeSha256": "7cfcc6a57122702ea35d04ed20861aef162bd94f55cfbbf9fd23ee3127fe6cb4",
    "afterSha256": "5e741b1b0e0826b075e9d6582207a5251ad112c75c4a02a81d395d9b56d3734c",
    "patchSha256": "461eb4eb61e5a01f282c996f86ef7c679d23363ec37ed6dfe5b21ed9e72fb94f",
    "defaultPollingLevel": 0}
# Existing642/643 paid identities belong to the retained owned lab authority.
# Never label those as default-production-authority paid qualification.
EXISTING_LAB_AUTHORITY_SOURCE = {
    642: {"classificationSha256": "315c0275c7e2d9f9e4358c07727bdd9699a9d0ba98c57570d08a91a60db157be",
          "referenceSha256": "1dad8d7f8e76144fe4b8be1578bcc3b894b23437ab3bc9d5390afd4a595e8ec5",
          "installedComposeSha256": "3f7482082efa5f7d4f0c23ba96e428a6ceb84f365f56404f86a140826350f6be"},
    643: {"classificationSha256": "b69419ff4a1a6dd513990e36d86659b1f59e4fc92dca22b966d44b214139c03c",
          "referenceSha256": "4f70231486782a443d1e23da971f073fb15b33f2a496ce9863421e1d6cc0fb54",
          "installedComposeSha256": "7007743185b8bb5c173ad5d25c89e1d425c18df0f15f6a22dfc132740622103b"}}
EXISTING_LAB_AUTHORITY_KEYS = ["MUX_LICENSING_FALLBACK_IP", "MUX_LICENSING_FALLBACK_IPS",
                               "MUX_LICENSING_PUBLIC_KEY", "MUX_LICENSING_URL"]
EXISTING_LAB_AUTHORITY_FILE = {"sha256": "47ac86e0a951db644f687a5e5336a33b83ae1387eabd669c965b78467b885383",
    "bytes": 181, "mode": "0o600", "uid": 0, "licensingKeyNamesOnly": EXISTING_LAB_AUTHORITY_KEYS}
EXISTING_LAB_AUTHORITY_ENV_SHA256 = "4898afbd65a4e32b88886c2cda9d863b2d3c153d09f1ac93cdd042c1056f5eda"
EXISTING_LAB_ENV_FILE_REFERENCE = ["${APP_DATA_DIR}/testoverride.env"]
# This reviewed component outcome retains a failed cold request. These pins
# grant no source-corpus, normal-package, actual69 or publication admission.
COMPILED_AMD_OPERATION_LOCKS = {
    "rawEvidence": "04ea1742894c9e5a1e73e8d316a7c2191fa68f13d88dd4a607c2879b5030e55c",
    "producerOutcomeSummary": "03113860a8b252290583243d38d9e5e6cc2e9289151c976f02d85b1e051106bc",
    "independentRootReview": "80b33ea8e16e9deda572e8e277e84d8051b2e96bacebd6c48daede0b3ea7cf83"}
UPSTREAM_COMMIT = "465e49b9cea78a68b9c244ffb48d0ee24a82873d"
UPSTREAM_ARCHIVE_SHA256 = "94b3e8281bbc803bdc081a5e54ea84c7e9004f1f2cf332662deef433d542a86a"
CORPUS_IDS = ('minimal-home', 'low-priority-home', 'low-priority-app', 'primary-lottery-low-app',
    'exact-home', 'exact-reduced-home', 'exact-plus-minimize', 'coordinated-targets', 'negated-minimize',
    'negated-coordinated', 'contradictory-priority', 'unsupported-subset', 'unsupported-upper-percentage',
    'unsupported-lower-percentage', 'unsupported-percentage-range', 'unsupported-percentage-inequality',
    'baseline-primary-lottery', 'baseline-fixed-remainder', 'baseline-named-app', 'baseline-rank',
    'baseline-rank-half', 'baseline-hash', 'baseline-group', 'low-priority-group', 'unsupported-temperature')


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def locked_json(root, path, digest):
    require(isinstance(path, str) and path and not Path(path).is_absolute() and ".." not in Path(path).parts,
            "Unsafe release receipt path")
    file = root / path
    require(stat.S_ISREG(file.lstat().st_mode), "Release evidence must be a regular file")
    raw = file.read_bytes()
    require(isinstance(digest, str) and SHA256.fullmatch(digest) and sha256(raw) == digest,
            "Reviewed release evidence bytes changed")
    return json.loads(raw)


def historical(root, channel):
    previous = locked_json(root, PREDECESSOR_NAME, PREDECESSOR_LOCKS[channel])
    require(previous["channel"] == channel and previous["version"] == ("0.9.80-dev" if channel == "DEV" else "0.9.80"),
            "Historical channel/version changed")
    publication = previous["publication"]
    require(publication["sha256"] == PREDECESSOR_DELIVERY_LOCKS[channel], "Historical delivery lock changed")
    locked_json(root, publication["path"], PREDECESSOR_DELIVERY_LOCKS[channel])
    older = previous["predecessor"]
    old_record = locked_json(root, older["record"], older["sha256"])
    require(older["delivery"] == old_record["publication"], "Historical predecessor binding changed")
    locked_json(root, older["delivery"]["path"], older["delivery"]["sha256"])
    return previous


def record(root=ROOT):
    raw = (root / RECORD_NAME).read_bytes()
    row = json.loads(raw)
    channel = row["channel"]
    require(channel in recipe.VERSIONS and ADMISSION_LOCKS[channel] is not None,
            "0.9.82 publication has not been independently finalized")
    require(stat.S_ISREG((root / RECORD_NAME).lstat().st_mode) and sha256(raw) == ADMISSION_LOCKS[channel],
            "Unreviewed 0.9.82 release record")
    require(row["schemaVersion"] == 1 and row["status"] == "qualified" and row["appId"] == APP
            and row["version"] == recipe.VERSIONS[channel], "Release identity mismatch")
    require({key: row[key] for key in APPLICATION_SOURCE} == APPLICATION_SOURCE,
            "Exact frozen application source identities required")
    recipe.image_refs(row["imageRef"], row["localAIImageRef"], channel)
    require(row["imageRef"] == APPLICATION_IMAGE_REFS[channel], "The independently admitted public APP index is required")
    previous = historical(root, channel)
    require(row["predecessor"] == {"record": PREDECESSOR_NAME, "sha256": PREDECESSOR_LOCKS[channel],
            "delivery": previous["publication"]}, "The qualified 0.9.80 predecessor must be retained")
    for product in ("platforms", "localAIPlatforms"):
        require(set(row[product]) == {"amd64", "arm64"}, "Both current Umbrel architectures must remain supported")
        for platform in row[product].values():
            fields = {"manifestDigest", "configDigest"}
            if product == "localAIPlatforms":
                fields |= {"companionSourceRevision", "companionSourceTree"}
            require(set(platform) == fields and all(DIGEST.fullmatch(platform[field]) for field in ("manifestDigest", "configDigest")),
                    "Exact platform manifest/config and component source identities required")
    validate_component_sources(row)
    return row


def validate_component_sources(release, proof=None):
    require({key: release.get(key) for key in APPLICATION_SOURCE} == APPLICATION_SOURCE,
            "Exact frozen application source identities required")
    actual_package = {"sourceRevision": release.get("packageProducerSourceRevision"),
                      "sourceTree": release.get("packageProducerSourceTree")}
    require(PACKAGE_PRODUCER_SOURCE is not None and actual_package == PACKAGE_PRODUCER_SOURCE
            and all(isinstance(value, str) and SHA1.fullmatch(value) for value in actual_package.values()),
            "The package producer requires its independently reviewed source revision/tree")
    inputs = release.get("packageProducerInputs")
    require(PACKAGE_PRODUCER_INPUTS is not None and inputs == PACKAGE_PRODUCER_INPUTS
            and isinstance(inputs, dict) and set(inputs) == {
                "packaging/umbrel-local-ai-release/prepare_package.py", "packaging/umbrel-local-ai-release/pre-start"}
            and all(isinstance(value, str) and SHA256.fullmatch(value) for value in inputs.values()),
            "Exact independently reviewed package producer and pre-start bytes required")
    if proof is not None:
        require(all(proof.get(field) == release[field] for field in
                    ("packageProducerSourceRevision", "packageProducerSourceTree", "packageProducerInputs")),
                "Package producer delivery source differs from its reviewed record")
    require(set(release["localAIPlatforms"]) == {"amd64", "arm64"}, "Both companion source identities required")
    for architecture, row in release["localAIPlatforms"].items():
        actual = {"sourceRevision": row.get("companionSourceRevision"), "sourceTree": row.get("companionSourceTree")}
        expected = COMPANION_SOURCE_PINS[architecture]
        require(expected is not None and actual == expected
                and all(isinstance(value, str) and SHA1.fullmatch(value) for value in actual.values()),
                "Each compiled companion requires its independently reviewed source revision/tree")
        if proof is not None:
            delivered = proof.get("localAIPlatforms", {}).get(architecture, {})
            require(all(delivered.get(field) == row[field] for field in ("companionSourceRevision", "companionSourceTree")),
                    "Compiled companion delivery source differs from its architecture-specific record")


def validate_package(root, release):
    app = root / APP
    actual = {str(path.relative_to(app)) for path in app.rglob("*") if path.is_file() or path.is_symlink()}
    require(actual == recipe.FILES and set(release["packageFiles"]) == {APP + "/" + name for name in recipe.FILES},
            "Only the reviewed normal Umbrel app package may be delivered")
    for name, identity in release["packageFiles"].items():
        path = root / name
        mode = 0o755 if name.endswith("hooks/pre-start") else 0o644
        require(stat.S_ISREG(path.lstat().st_mode) and stat.S_IMODE(path.stat().st_mode) == mode
                and identity == {"sha256": sha256(path.read_bytes()), "mode": oct(mode)}, "App package bytes/mode changed")
    require(sha256((app / "hooks/pre-start").read_bytes()) == HOOK_SHA256
            and sha256((app / "icon.png").read_bytes()) == recipe.ICON_SHA256, "Unreviewed hook/artwork")
    recipe.validate_recipe(yaml.safe_load((app / "docker-compose.yml").read_text()),
                           release["imageRef"], release["localAIImageRef"], release["channel"])
    require(yaml.safe_load((app / "umbrel-app.yml").read_text()) == recipe.manifest_model(release["channel"]),
            "Manifest storage, access, ports or release claims changed")


def referenced_proof(root, reference):
    require(set(reference) == {"path", "sha256"} and reference["path"].startswith("release-records/")
            and len(Path(reference["path"]).parts) == 2, "Use a retained release-records evidence file")
    return locked_json(root, reference["path"], reference["sha256"])


def validate_run(evidence, binary_sha, cpu_profile, intent_sha):
    require(isinstance(binary_sha, str) and SHA256.fullmatch(binary_sha), "Actual selected runtime digest required")
    require(evidence["kind"] == "unreviewed-real-inference-successor-evidence"
            and evidence["completeCorpus"] is True and evidence["ownedRuntimeStopped"] is True
            and evidence["routingAuthority"] == "none"
            and isinstance(evidence["startedAt"], str) and bool(evidence["startedAt"])
            and isinstance(evidence["endedAt"], str) and bool(evidence["endedAt"]),
            "Complete actual corpus and owned cleanup evidence required")
    require(evidence["runtimeBinarySha256"] == evidence["expectedRuntimeBinarySha256"] == binary_sha
            and evidence["runtimeCpuProfile"] in (None, cpu_profile) and evidence["intentProfileSha256"] == intent_sha == INTENT_SHA256
            and evidence["modelSha256"] == MODEL_SHA256 and evidence["modelId"] == "qwen3.5-4b",
            "Actual model/runtime/profile qualification identity mismatch")
    # Eligibility records the source policy at collection time. Release
    # admission comes from independent semantic, artifact and receipt locks.
    require(type(evidence["productionEligible"]) is bool and evidence["corpusSha256"] == CORPUS_SHA256
            and tuple(evidence["expectedCorpusCaseIds"]) == CORPUS_IDS
            and evidence["plannedCaseIds"] == evidence["expectedCorpusCaseIds"]
            and [row["id"] for row in evidence["cases"]] == evidence["expectedCorpusCaseIds"],
            "Partial or duplicate corpus evidence is not a complete run")
    require(all(row["verdict"] in ("pass", "fail", "requires_review", "technical_failure")
                and type(row["seconds"]) in (int, float)
                and math.isfinite(row["seconds"]) and row["seconds"] >= 0
                and (isinstance(row.get("result"), dict) or
                    (row["verdict"] == "technical_failure" and isinstance(row.get("error"), str)))
                for row in evidence["cases"]),
            "Retain actual verdicts and finite elapsed time for every case")
    passes = sum(row["verdict"] == "pass" for row in evidence["cases"])
    require(type(evidence["automaticPasses"]) is int and evidence["automaticPasses"] == passes,
            "The performance pass count must match the retained case verdicts")
    require(all(row["result"].get("actualInference") is True and row["result"].get("contractValid") is True
                for row in evidence["cases"] if row["verdict"] == "pass"),
            "Every passing case must contain actual successful inference")
    return evidence


def validate_corpus(evidence, binary_sha, cpu_profile, intent_sha):
    validate_run(evidence, binary_sha, cpu_profile, intent_sha)
    require(evidence["productionEligible"] is False, "The approved successor semantic evidence predates its production grant")
    require(evidence["automaticPasses"] == 25, "Semantic qualification requires all 25 actual inference cases")


def validate_semantic_qualification(root, reference):
    # This is one reviewed model/prompt/compiler qualification. Architecture,
    # CPU legality, cold start and deployment performance remain separate facts.
    require(reference["sha256"] == SEMANTIC_EVIDENCE_SHA256, "Use the exact independently reviewed semantic corpus")
    evidence = referenced_proof(root, reference)
    validate_corpus(evidence, RUNTIME_SHA256["arm64"], "arm64", INTENT_SHA256)
    return evidence


def performance_summary(evidence, cpu_profile):
    require(cpu_profile in SERVICE_REQUEST_BUDGET_SECONDS, "Explicit performance CPU profile required")
    budget = SERVICE_REQUEST_BUDGET_SECONDS[cpu_profile]
    first = evidence["cases"][0]
    error = first.get("result", {}).get("error") or {}
    passes = evidence["automaticPasses"]
    return {"scope": "laboratory-runtime-corpus", "caseCount": len(evidence["cases"]),
        "passes": passes, "failures": len(evidence["cases"]) - passes,
        "coldStart": {"caseId": first["id"], "verdict": first["verdict"], "seconds": first["seconds"],
            "errorCode": error.get("code"), "errorReason": error.get("reason"), "technicalError": first.get("error")},
        "configuredServiceBudgetSeconds": budget,
        "allCasesPassed": passes == 25,
        "allCasesPassedWithinServiceBudget": passes == 25
            and all(row["seconds"] <= budget for row in evidence["cases"])}


def validate_performance(root, reference, summary, cpu_profile):
    require(RUNTIME_SHA256[cpu_profile] is not None, "The selected compatible runtime artifact is not independently admitted")
    evidence = referenced_proof(root, reference)
    validate_run(evidence, RUNTIME_SHA256[cpu_profile], cpu_profile, INTENT_SHA256)
    require(summary == performance_summary(evidence, cpu_profile), "Performance claims must reproduce the actual run, including failures")
    # The complete native run retained 24 passes and its first cold failure.
    if cpu_profile == "native-amd64-avx2":
        cold = summary["coldStart"]
        require(cold["caseId"] == "minimal-home" and cold["verdict"] == "fail"
                and cold["errorCode"] == "runtime_timeout" and cold["errorReason"] == "intent_deadline"
                and cold["seconds"] >= 180,
                "The observed native 180s first cold timeout must be retained")
        require(evidence["automaticPasses"] == 24
                and all(row["verdict"] == "pass" and row["seconds"] <= 180 for row in evidence["cases"][1:]),
                "Native performance may retain only its one reviewed first cold failure and 24 bounded successes")
    else:
        require(evidence["automaticPasses"] == 25 and summary["allCasesPassed"] is True
                and summary["allCasesPassedWithinServiceBudget"] is True,
                "Final portable/ARM performance requires all25 actual passes within its per-profile service budget")
    return evidence


def validate_rejected_history(root, references):
    require(set(references) == set(REJECTED_EVIDENCE_SHA256), "Retain both actually rejected baseline variants")
    for name, reference in references.items():
        require(reference["sha256"] == REJECTED_EVIDENCE_SHA256[name], "Rejected partial evidence cannot be replaced by a later warm run")
        evidence = referenced_proof(root, reference)
        require(evidence["kind"] == "unreviewed-real-inference-successor-evidence"
                and evidence["completeCorpus"] is False and evidence["ownedRuntimeStopped"] is True
                and evidence["interruptedBy"] == "SIGTERM" and evidence["productionEligible"] is False
                and evidence["routingAuthority"] == "none" and evidence["intentProfileSha256"] == INTENT_SHA256
                and evidence["runtimeBinarySha256"] == evidence["expectedRuntimeBinarySha256"]
                    == "39ff55c3381e7d4cf5b007c78944a2e910233dcc1d32ea1c909942cb6c641b81",
                "Rejected partial runs must retain actual identity, interruption and owned cleanup")
        model = ("qwen3.5-4b", MODEL_SHA256) if name == "baseline-4b-600s" else (
            "qwen3.5-0.8b", "bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517")
        require((evidence["modelId"], evidence["modelSha256"]) == model,
                "Rejected model identities cannot be substituted")
        require(len(evidence["cases"]) == (2 if name == "baseline-4b-600s" else 6)
                and evidence["automaticPasses"] == (1 if name == "baseline-4b-600s" else 3)
                and sum(case["verdict"] == "pass" for case in evidence["cases"]) == evidence["automaticPasses"]
                and tuple(case["id"] for case in evidence["cases"]) == CORPUS_IDS[:len(evidence["cases"])],
                "Rejected partial runs are history, not full corpus or release performance acceptance")


def validate_cpu_build(evidence, binary_sha, cpu_profile):
    require(evidence["sourceCommit"] == UPSTREAM_COMMIT and evidence["sourceArchiveSha256"] == UPSTREAM_ARCHIVE_SHA256
            and evidence["binarySha256"] == binary_sha and evidence["cpuProfile"] == cpu_profile
            and type(evidence["compilerCommandsChecked"]) is int and evidence["compilerCommandsChecked"] > 0
            and evidence["productionQualificationGranted"] is False,
            "Retained actual source/compiler/ELF/ISA build evidence must bind this inference binary")
    if cpu_profile != "amd64-v2":
        require(evidence["kind"] == "actual-" + cpu_profile + "-runtime-build",
                "The unchanged ARM producer identity is required")
        return
    expected = {"kind": "actual-amd64-v2-static-nehalem-openblas-build", "binarySha256": OPENBLAS_BINARY,
        "upstreamBaseCommit": UPSTREAM_COMMIT, "upstreamSourceModified": True,
        "openblasVersion": "0.3.34", "openblasSourceCommit": "e0166008be8e466242aa76b2ff75ce3f0fbf574a",
        "openblasSourceSha256": "cd7e129868320cc2d033afa920e31202dfe0b8066a5b66661900ccc0f197dfed",
        "openblasStaticSha256": "7a586f302ff38736a0d4624eb2806c29614001bc7e3a3209943ce8a0b7cca4c9",
        "openblasProbeSha256": "1fa7dee6b784f301fd96e9e5cf103b8d9301697ef7046c9bfac2da34f4cf4b16",
        "openblasDynamicArchitecture": False, "openblasMathTeamMaximumThreads": 2, "openblasWorkerThreads": 1,
        "mathTeamIncludesCallingThread": True, "wholeServerThreadLimitClaimed": False,
        "actualDefaultGgmlPollingLevel": 0, "openblasThreadTimeoutExponent": 4,
        "compiledInitialOpenBlasThreadTimeoutTicks": 16, "guardedInstructionSites": 62,
        "guardedInstructionReviewSha256": "ee79136adb2dc1b59ddd2b8738ff4966ac7b681c14a0297aecf81d556fb02e54",
        "actualDisassemblySha256": "0659deb179905423755b03f437ccdcb822e4066abf99bc8948b7713bd805ef0f",
        "inferencePerformed": False, "modelWeightsIncluded": False}
    require(all(type(evidence.get(key)) is type(value) and evidence[key] == value for key, value in expected.items()),
            "Only the exact reviewed static NEHALEM OpenBLAS artifact/defaults are admitted as CPU build evidence")
    patch = {**OPENBLAS_PATCH, "upstreamBaseCommit": UPSTREAM_COMMIT, "upstreamSourceModified": True,
             "originalArchiveFilesChecked": 3543, "changedArchiveFiles": ["common/common.h"]}
    require(evidence.get("upstreamPatch") == patch, "The exact sole reviewed upstream patch is required")
    for name in ("openblasProbe", "openblasOverrideProbe"):
        probe = evidence.get(name, {})
        config, result = probe.get("config", {}), probe.get("result", {})
        shapes = probe.get("shapes", [])
        require(config.get("core") == "NEHALEM" and config.get("parallel") == 1
                and config.get("threadsBeforeSetter") == 2 and config.get("tasksBefore") == 2
                and result.get("correct") is True and result.get("apiOverrideClamped") is True
                and result.get("threads") == 2 and result.get("residentThreads") == 2
                and len(probe.get("threadCpuTickDeltas", {})) == 2
                and all(type(value) is int and value > 0 for value in probe["threadCpuTickDeltas"].values())
                and len(shapes) == 4 and {(row.get("m"), row.get("n"), row.get("k")) for row in shapes}
                    == {(512,512,512),(64,9216,2560),(64,2560,9216),(64,8192,2560)}
                and all(row.get("correct") is True and row.get("maxResidentThreads") == 2 for row in shapes),
                "Actual default and env/API override numeric two-thread probes are required")


def validate_runtime_inputs(inputs, config, row, cpu_profile):
    require(inputs["mode"] == "umbrel" and inputs["cpuProfile"] == cpu_profile
            and inputs["binarySha256"] == row["llamaSHA256"] and inputs["intentProfileSha256"] == INTENT_SHA256
            and inputs["privateSourceIncludedInFinalImage"] is False and inputs["modelWeightsIncluded"] is False
            and inputs["realInferenceQualification"] == "separate-required",
            "Actual protected runtime inputs do not match the delivered artifact")
    runtime = config["runtime"]
    require(runtime["binarySha256"] == row["llamaSHA256"] and runtime["cpuProfile"] == cpu_profile
            and runtime["binary"] == "/opt/5tratmux-local-ai/bin/llama-server"
            and runtime["modelDirectory"] == "/data/local-ai/models" and runtime["threads"] == 2
            and runtime["requestTimeoutSeconds"] == SERVICE_REQUEST_BUDGET_SECONDS[cpu_profile],
            "Actual packaged CPU/thread/deadline configuration must retain its reviewed per-profile bounds")
    require(config["resources"] == {"reserveBytes": 1073741824, "reserveFraction": 0.15,
            "monitorSeconds": 5, "allowUnvalidatedModels": True},
            "Host memory reserve/monitor and retained experimental-model policy cannot change")
    require(row["runtimeConfiguration"]["sha256"] == row["configSHA256"]
            and row["runtimeConfigurationVerified"] is True and row["runtimeNoticesVerified"] is True
            and row["runtimeReadOnlyRootfsVerified"] is True,
            "Audited actual config and notices byte bindings are required")
    if cpu_profile == "arm64":
        require(inputs["inputHashes"]["LLAMA-LICENSE"] == row["runtimeNoticesSHA256"] == LLAMA_LICENCE
                and "staticOpenBlas" not in inputs and "upstreamSourceModified" not in inputs,
                "The unchanged ARM licence and producer path must be retained")
        return
    require(inputs["binarySha256"] == OPENBLAS_BINARY and inputs.get("thirdPartyNoticesSha256")
            == row["runtimeNoticesSHA256"] == OPENBLAS_NOTICES,
            "Actual combined llama/OpenBLAS/local-patch notice bytes are required")
    require(inputs["inputHashes"]["OpenBLAS-LICENSE"] == OPENBLAS_LICENCE
            and inputs["inputHashes"]["LLAMA-LICENSE"] == LLAMA_LICENCE
            and inputs["inputHashes"]["THIRD_PARTY_NOTICES"] == OPENBLAS_NOTICES,
            "Both exact upstream licences and combined notices must remain in protected staging")
    require(inputs.get("staticOpenBlas") == {"version": "0.3.34",
        "sourceCommit": "e0166008be8e466242aa76b2ff75ce3f0fbf574a", "licenceSha256": OPENBLAS_LICENCE,
        "mathTeamMaximumThreads": 2, "mathTeamIncludesCallingThread": True, "admissionScope": "minimum-cpu-only",
        "performanceQualificationGranted": False, "threadTimeoutExponent": 4, "compiledInitialThreadTimeoutTicks": 16},
        "CPU build admission cannot self-authorize inference/performance qualification")
    require(inputs.get("upstreamSourceModified") is True and inputs.get("upstreamPatch")
            == {("sha256" if key == "patchSha256" else key): value for key, value in OPENBLAS_PATCH.items()},
            "Protected source must truthfully retain the exact reviewed local patch")


def validate_shared_channel_scope(evidence, release, delivery):
    channel = evidence["testedChannel"]
    require(channel in recipe.VERSIONS and evidence["testedVersion"] == recipe.VERSIONS[channel]
            and {key: evidence.get(key) for key in APPLICATION_SOURCE} == APPLICATION_SOURCE
            and evidence["protectedExecutableSHA256"] == delivery["platforms"]["amd64"]["protectedExecutableSHA256"]
            and evidence["localAIImageRef"] == release["localAIImageRef"],
            "State the actual tested channel and bind its common compiled application/companion")
    require(evidence["testedImageRef"] == APPLICATION_IMAGE_REFS[channel]
            and evidence["testedApplicationConfigDigest"] == APPLICATION_AMD64_CONFIGS[channel],
            "The tested channel must use its independently admitted APP index and AMD64 config")
    expected_recipe = (json.dumps(recipe.recipe_model(APPLICATION_IMAGE_REFS[channel], release["localAIImageRef"], channel), indent=2) + "\n").encode()
    require(evidence["testedPackageRecipeSHA256"] == sha256(expected_recipe),
            "The actual tested normal recipe must match the frozen producer contract and admitted APP index")
    recipe.image_refs(evidence["testedImageRef"], evidence["localAIImageRef"], channel)
    if channel == release["channel"]:
        require(evidence["testedImageRef"] == release["imageRef"], "The actual tested channel image differs")
    else:
        require(evidence.get("reuseForChannel") == release["channel"]
                and evidence.get("reuseScope") == "identical-protected-ELF-and-normal-package-contract"
                and evidence.get("recipeParityVerified") is True,
                "Cross-channel common lifecycle reuse must be explicit and independently reviewed")


def validate_existing_lab_authority_adaptation(root, evidence, release):
    target = evidence["targetVmid"]
    expected = EXISTING_LAB_AUTHORITY_SOURCE[target]
    adaptation = evidence["existingLabAuthorityAdaptation"]
    require(evidence["paidIdentityScope"] == "pre-existing-owned-lab-paid-identity"
            and evidence["defaultProductionAuthorityPaidProofClaimed"] is False
            and adaptation["kind"] == "retained-existing-lab-authority-env-file-reference"
            and adaptation["serverEnvFileReferences"] == EXISTING_LAB_ENV_FILE_REFERENCE
            and adaptation["authorityValuesUnchanged"] is True
            and adaptation["authorityKeysCopied"] is False and adaptation["licenceGrantOrProofEdited"] is False,
            "Only the disclosed existing lab-paid authority reference may be retained on642/643")
    classification_ref, reference_ref = adaptation["classificationEvidence"], adaptation["referenceEvidence"]
    require(classification_ref["sha256"] == expected["classificationSha256"]
            and reference_ref["sha256"] == expected["referenceSha256"],
            "The exact read-only pre-existing lab authority source evidence is required")
    classification, reference = referenced_proof(root, classification_ref), referenced_proof(root, reference_ref)
    require(classification["kind"] == "read-only-existing-qa-authority-source-classification"
            and classification["targetVmid"] == reference["targetVmid"] == target
            and classification["authoritySourceClassification"] == "existing-owned-lab-authority"
            and classification["licensingEnvironmentKeyNames"] == EXISTING_LAB_AUTHORITY_KEYS
            and classification["licensingEnvironmentMappingSha256"] == EXISTING_LAB_AUTHORITY_ENV_SHA256
            and classification["installedFiles"]["testoverride.env"] == EXISTING_LAB_AUTHORITY_FILE
            and classification["installedFiles"]["docker-compose.yml"]["sha256"] == expected["installedComposeSha256"]
            and reference["kind"] == "exact-existing-env-file-reference-read-only"
            and reference["composeSha256"] == expected["installedComposeSha256"]
            and reference["serverEnvFileReferences"] == EXISTING_LAB_ENV_FILE_REFERENCE,
            "Existing authority source/file/reference identity differs from the actual read-only snapshot")
    require(adaptation["fileBefore"] == adaptation["fileAfter"] == EXISTING_LAB_AUTHORITY_FILE
            and adaptation["licensingEnvironmentMappingSha256Before"]
                == adaptation["licensingEnvironmentMappingSha256After"] == EXISTING_LAB_AUTHORITY_ENV_SHA256
            and adaptation["preExistingInstalledComposeSha256"] == expected["installedComposeSha256"],
            "The existing authority file and effective values must remain byte-identical, without exporting values")
    channel = evidence["testedChannel"]
    original = recipe.recipe_model(APPLICATION_IMAGE_REFS[channel], release["localAIImageRef"], channel)
    overlay = {"services": {"server": {"env_file": EXISTING_LAB_ENV_FILE_REFERENCE}}}
    adapted = json.loads(json.dumps(original))
    adapted["services"]["server"]["env_file"] = EXISTING_LAB_ENV_FILE_REFERENCE
    source_hash = lambda value: sha256((json.dumps(value, indent=2) + "\n").encode())
    require(adaptation["originalPackageRecipeSHA256"] == evidence["testedPackageRecipeSHA256"] == source_hash(original)
            and adaptation["qaOverlaySHA256"] == source_hash(overlay)
            and adaptation["adaptedQaSourceRecipeSHA256"] == source_hash(adapted)
            and adaptation["minimalDifference"] == [{"operation": "add", "path": "/services/server/env_file",
                                                     "value": EXISTING_LAB_ENV_FILE_REFERENCE}],
            "Retain the exact public recipe and only its separately recorded pre-existing env_file QA adaptation")


def validate_compiled_amd_operation(root, references, delivery):
    require(set(references) == set(COMPILED_AMD_OPERATION_LOCKS)
            and all(references[key]["sha256"] == digest for key, digest in COMPILED_AMD_OPERATION_LOCKS.items()),
            "Retain the separately reviewed compiled cold failure, outcome summary and independent root review")
    raw, summary, review = (referenced_proof(root, references[key]) for key in
                            ("rawEvidence", "producerOutcomeSummary", "independentRootReview"))
    row = delivery["localAIPlatforms"]["amd64"]
    require(raw["kind"] == "unreviewed-real-compiled-amd64-v2-bounded-UDS-operation-evidence"
            and raw["scope"] == "bounded-compiled-operation-not-full25"
            and raw["sourceRevision"] == row["companionSourceRevision"]
            and raw["sourceTree"] == row["companionSourceTree"]
            and raw["imageId"] == raw["imageConfigId"] == row["configDigest"]
            and raw["compiledServiceSha256"] == row["serviceSHA256"]
            and raw["compiledSupervisorSha256"] == row["supervisorSHA256"]
            and raw["runtimeBinarySha256"] == row["llamaSHA256"] == OPENBLAS_BINARY
            and raw["intentProfileSha256"] == INTENT_SHA256 and raw["modelSha256"] == MODEL_SHA256
            and raw["cpuLimit"] == 2 and raw["memoryLimitBytes"] == 6 * 1024**3
            and summary["runtimeCpuLimit"] == 2
            and summary["runtimeMemoryLimitBytes"] == summary["runtimeMemorySwapLimitBytes"] == 6 * 1024**3
            and raw["requestTimeoutSeconds"] == 600 and raw["routingAuthority"] == "none",
            "Compiled operation evidence must bind the actual final AMD image/source/ELFs and retained bounds")
    require(raw["compiledBoundedOperationExecutionPassed"] is False and raw["modelInferenceAccepted"] is False
            and raw["completeCorpus"] is False and raw["completeRequestedCases"] is True
            and raw["automaticPasses"] == 1 and raw["automaticWarmRetries"] == 0
            and raw["selectedCanonicalCaseIds"] == ["minimal-home", "coordinated-targets"]
            and [case["id"] for case in raw["cases"]] == raw["selectedCanonicalCaseIds"],
            "The original failed aggregate and two distinct planned cases must not become a full/cold pass")
    cold, warm = raw["cases"]
    failure, result = cold["result"], warm["result"]
    require(cold["verdict"] == "fail" and failure["actualInference"] is False and failure["contractValid"] is False
            and failure["intent"] is None and failure["error"]["code"] == "runtime_timeout"
            and failure["error"]["reason"] == "intent_deadline" and failure["elapsedSeconds"] >= 600
            and cold["runtime"]["generation"]["completionReceived"] is False
            and warm["verdict"] == "pass" and result["actualInference"] is True and result["contractValid"] is True
            and result["elapsedSeconds"] <= 600 and result["intent"]["s"] == "resolved"
            and sorted((c["k"], c["a"], c["w"], c["v"], c["u"]) for c in result["intent"]["c"])
                == [("deprioritize", "5trat", "all", None, None), ("deprioritize", "bitcoin", "all", None, None)]
            and type(cold["runtime"]["pid"]) is int and cold["runtime"]["pid"] > 0
            and cold["runtime"]["pid"] == warm["runtime"]["pid"]
            and all(case["runtime"]["healthy"] is True for case in (cold, warm)),
            "Retain the guarded600s cold failure and separately correct same-process warm recovery")
    comparison = raw["normalCompare"]
    require(comparison["actualInference"] is True and comparison["contractValid"] is True
            and comparison["decision"] == "select" and comparison["selectedCandidateId"] == "retain-current"
            and comparison["runtimeBinarySha256"] == OPENBLAS_BINARY and comparison["modelSha256"] == MODEL_SHA256
            and raw["normalComparePassed"] is True and raw["onMonitorPassed"] is True
            and math.isfinite(raw["onMonitorSeconds"]) and raw["onMonitorSeconds"] >= 660
            and raw["disableReceipt"] == {"code": 200, "value": {"accepted": True, "phase": "off", "preferencesSaved": True}}
            and raw["finalOff"]["enabled"] is False and raw["finalOff"]["runtime"]["running"] is False
            and raw["ownedModelStopped"] is True,
            "Compiled comparison, active-job On elapsed scope and explicit Off/model release must remain separate facts")
    require(summary["kind"] == "producer-scoped-compiled-amd595-cold-timeout-and-same-process-recovery-outcome"
            and summary["rawEvidenceSHA256"] == review["rawEvidenceSha256"] == references["rawEvidence"]["sha256"]
            and review["producerOutcomeSummarySha256"] == references["producerOutcomeSummary"]["sha256"]
            and review["rawInventorySha256"] == summary["rawReceipts"]["final-operation-inventory.json"]
            and summary["originalDriverExit"] == review["originalClientExitCode"] == 1
            and summary["originalCompiledBoundedOperationExecutionPassed"] is False
            and summary["cold"]["generationElapsedSeconds"] == review["compiledColdGenerationSeconds"] == failure["elapsedSeconds"]
            and summary["cold"]["firstColdPassClaimed"] is False
            and summary["warmRecovery"]["generationElapsedSeconds"] == review["warmGenerationSeconds"] == result["elapsedSeconds"]
            and summary["normalComparison"]["elapsedSeconds"] == review["comparisonGenerationSeconds"] == comparison["elapsedSeconds"]
            and summary["onEvidence"]["reportedElapsedSeconds"] == review["onObservedSeconds"] == raw["onMonitorSeconds"]
            and summary["onEvidence"]["separatePassive660SampleSweepPerformed"] is False
            and summary["onEvidence"]["intermediateStatusPollsPersisted"] is False
            and summary["offAndCleanup"]["cachedModelUnchanged"] is True,
            "Compiled outcome claims must reproduce raw timings/failure and disclose the retained observation limits")
    require(review["reviewer"] == "/root" and review["scopeDecision"] == "SCOPED_COLD_FAILURE_AND_WARM_RECOVERY_ACCEPTED"
            and review["imageId"] == raw["imageId"] and review["sourceRevision"] == raw["sourceRevision"]
            and review["sourceTree"] == raw["sourceTree"] and review["originalAggregatePassed"] is False
            and review["compiledColdDeadlinePassed"] is False and review["firstColdPerformanceReliabilityGranted"] is False
            and review["fullCompiled25CorpusClaimed"] is False and review["passive660SampleSweepPerformed"] is False
            and review["sourceFull25CorpusAcceptanceStillRequired"] is True and review["normalPackageQaStillRequired"] is True
            and review["actual69DeploymentAcceptanceGranted"] is False and review["publicationGranted"] is False
            and review["offAndModelReleaseAccepted"] is True and review["modelCachePreserved"] is True
            and review["ownedContainersRemoved"] is True,
            "The independent compiled review cannot grant cold reliability, full25, package, actual69 or publication claims")
    return raw


def validate_memory_hold_update(root, evidence, version, release, delivery):
    require(evidence["result"] == "PASS" and evidence["architecture"] == "amd64"
            and evidence["kind"] == "normal-umbrel-update-with-memory-guard"
            and evidence["osVersion"] == version and evidence["targetVmid"] == {"1.7.4": 642, "2.0.0": 643}[version]
            and evidence["configuredMemoryMiB"] == 8192
            and evidence["runtimeCpuLimit"] == 2 and evidence["runtimeMemoryLimitBytes"] == 6 * 1024**3
            and evidence["runtimeMemorySwapLimitBytes"] == 6 * 1024**3
            and all(evidence[field] is True for field in ("nativeUpdateStopStartPersistenceVerified",
                "operatorAuthenticationVerified", "localAiOffCleanupVerified", "socketPeerIdentityVerified",
                "existingMuxStatePreserved", "existingPaidIdentityPreserved", "hardwareUnchanged",
                "storageRootContractVerified", "noHostControllerOrDockerSocket", "memoryGuardRefusedEnable"))
            and evidence["runtimeRunningAfterRefusal"] is False and evidence["onOrInferenceClaimed"] is False,
            "Existing8GB normal updates must preserve state and report their actual RAM hold")
    memory = evidence["memoryAdmission"]
    require(all(type(memory[field]) is int and memory[field] >= 0 for field in
                ("hostTotalBytes", "hostAvailableBytes", "hostReserveBytes", "modelBudgetBytes", "requiredHostBytes"))
            and 7 * 1024**3 <= memory["hostTotalBytes"] <= 8 * 1024**3
            and 0 < memory["hostAvailableBytes"] <= memory["hostTotalBytes"]
            and memory["modelBudgetBytes"] == 5 * 1024**3
            and memory["hostReserveBytes"] == max(1024**3, int(memory["hostTotalBytes"] * 0.15))
            and memory["requiredHostBytes"] == memory["modelBudgetBytes"] + memory["hostReserveBytes"]
            and memory["hostAvailableBytes"] < memory["requiredHostBytes"]
            and memory["allowed"] is False,
            "The RAM hold must reproduce the unchanged actual host reserve and model budget")
    validate_shared_channel_scope(evidence, release, delivery)
    validate_existing_lab_authority_adaptation(root, evidence, release)


def validate_full_unlicensed_lifecycle(evidence):
    require(type(evidence["continuousOnSeconds"]) in (int, float)
            and math.isfinite(evidence["continuousOnSeconds"]) and evidence["continuousOnSeconds"] >= 660
            and all(evidence[field] is True for field in ("onOffPersistenceVerified", "normalAppStopStartVerified",
                "runtimeRemovalReinstallOffVerified", "modelAndPreferencesRetained", "noEntitlementStop",
                "noOom", "socketPeerIdentityVerified")),
            "Actual>=660s On and private lifecycle evidence is required; RAM holds cannot substitute")


def validate_saved_preferences_restart_policy(root, evidence, release):
    require(evidence["savedOnAndOffPreferencesRetained"] is True and evidence["restartSafeOffVerified"] is True
            and evidence["explicitOwnerStartVerified"] is True and evidence["automaticModelRestoreVerified"] is False
            and evidence["modelRestartPolicy"] == "model-Off-on-service-restart-explicit-owner-Start",
            "Saved preferences, fail-safe Off and a separate owner Start must never become automatic restoration")
    policy = evidence["restartPolicyEvidence"]
    safe = referenced_proof(root, policy["safeOffEvidence"])
    channel = release["channel"]
    require(safe["result"] == "PASS" and safe["kind"] == "root-admitted-normal-package649-phase"
            and safe["targetVmid"] == 649 and safe["channel"] == channel
            and safe["automaticModelRestoreVerified"] is False
            and safe["afterSnapshot"]["imageId"] == APPLICATION_AMD64_CONFIGS[channel],
            "The actual channel must report its healthy service and model Off after restart")
    pending = safe["afterSavedOnRestartSafeOff"] if channel == "DEV" else safe["afterNormalUpdateLocalAI"]
    status = pending["status"]
    require(pending["result"] == "PASS" and pending["controlRequestsSent"] == 0
            and pending["automaticModelRestoreVerified"] is False and pending["memoryEvents"]["oom"] == 0
            and pending["memoryEvents"]["oom_kill"] == 0
            and pending["retainedModelPhysicalHash"]["sha256"] == MODEL_SHA256
            and status["enabled"] is False and status["runtime"]["running"] is False
            and status["runtime"]["healthy"] is False and status["runtime"]["pid"] is None
            and status["phase"] == "off" and status["busy"] is False and status["error"] is None
            and all(status["installation"][key] is True for key in ("installed", "running", "supported", "configurationMatches"))
            and status["installation"]["busy"] is False and status["installation"]["error"] is None
            and status["installation"]["updateRequired"] is False
            and status["preferences"]["desiredEnabled"] is True and status["preferences"]["state"] == "loaded"
            and status["preferences"]["resumeState"] == "pending" and status["preferences"]["restoreAuthority"] == "host"
            and pending["stateFiles"] == safe["beforeSnapshot"]["stateFiles"] == safe["afterSnapshot"]["stateFiles"],
            "Pending saved On requires a live configured service, stopped model, retained cache and no OOM/control")
    if channel == "DEV":
        original = referenced_proof(root, policy["originalRestartExpectationFailure"])
        require(policy["originalRestartExpectationFailure"]["sha256"] == FRESH_DEV_RESTART_EXPECTATION_FAILURE
                and original["result"] == "STOPPED_REQUIRES_REVIEW"
                and original["latestRestoredLocalAI"]["result"] == "READINESS_TIMEOUT"
                and safe["reconciledPriorRestartEvidence"]["sha256"] == policy["originalRestartExpectationFailure"]["sha256"]
                and safe["normalManagerMutationRepeated"] is False and safe["apiMutationAttempts"] == [],
                "The original incorrect auto-On expectation remains failed; reconcile without repeating manager actions")
    owner = referenced_proof(root, policy["explicitOwnerStartEvidence"])
    started = owner["actualOperatorOrMonitorResult"]
    require(owner["kind"] == "root-admitted-normal-package649-phase" and owner["result"] == started["result"] == "PASS"
            and owner["targetVmid"] == started["targetVmid"] == 649 and owner["channel"] == started["channel"] == channel
            and owner["explicitOwnerStart"] is True and owner["automaticModelRestoreVerified"] is False
            and started["kind"] == "actual-fresh649-normal-package-operator-step" and started["action"] == "enable"
            and started["imageRef"] == release["imageRef"] and started["localAIImageRef"] == release["localAIImageRef"]
            and started["singleMutationIntent"]["route"] == "/api/local-ai/enable"
            and 200 <= started["controlResponse"]["httpStatus"] < 300
            and started["controlResponse"]["value"]["accepted"] is True
            and started["localAiBefore"]["runtime"]["running"] is False
            and started["localAiBefore"]["preferences"]["desiredEnabled"] is True,
            "Owner Start is its own authenticated normal enable; it cannot be described as automatic startup")
    ready = referenced_proof(root, policy["explicitOwnerStartReadiness"])
    on = ready["status"]
    require(ready["result"] == "PASS" and ready["controlRequestsSent"] == 0
            and ready["applicationContainerId"] == started["applicationBoundaryAfter"]["containerId"]
            and ready["companionContainerId"] == started["companionBoundaryAfter"]["containerId"]
            and ready["stateFiles"] == started["stableFilesAfter"]
            and on["phase"] == "ready" and on["busy"] is False and on["enabled"] is True
            and on["preferences"]["desiredEnabled"] is True
            and on["runtime"]["running"] is True and on["runtime"]["healthy"] is True
            and type(on["runtime"]["pid"]) is int and on["runtime"]["pid"] > 0
            and on["runtime"]["binarySha256"] == OPENBLAS_BINARY and on["modelSha256"] == MODEL_SHA256
            and on["capabilities"]["missionIntentProfileSha256"] == INTENT_SHA256,
            "An accepted enable is insufficient: retain later GET-only healthy On for the same compiled service/model")


def validate_fresh_intent_outcome(root, evidence, release):
    require("firstIntentOutcome" in evidence, "Retain each channel's original649 intent outcome")
    outcome = evidence["firstIntentOutcome"]
    rows = {}
    for name in ("firstHostEvidence", "firstGuestEvidence", "successfulHostEvidence", "successfulGuestEvidence"):
        rows[name] = referenced_proof(root, outcome[name])
    channel = release["channel"]
    first, successful = rows["firstGuestEvidence"], rows["successfulGuestEvidence"]
    for prefix, guest in (("first", first), ("successful", successful)):
        host = rows[prefix + "HostEvidence"]
        require(host["kind"] == "root-admitted-normal-package649-phase" and host["targetVmid"] == 649
                and host["channel"] == channel and host["actualOperatorOrMonitorResult"] == guest
                and host["apiMutationAttempts"] == [] and host["automaticMutationRetries"] == 0
                and guest["kind"] == "actual-fresh649-normal-package-operator-step"
                and guest["targetVmid"] == 649 and guest["channel"] == channel
                and guest["action"] == "minimal-home-intent" and guest["imageRef"] == release["imageRef"]
                and guest["localAIImageRef"] == release["localAIImageRef"]
                and guest["automaticMutationRetry"] is False and guest["filesystemOrPromptCacheCleared"] is False,
                "Actual once-only compiled APP intent journals and channel identity must match")
        result = guest["intentResult"]
        require(result["requestId"] == guest["intentSubmission"]["requestId"]
                and result["inputSha256"] == guest["intentSubmission"]["inputSha256"]
                and result["modelSha256"] == MODEL_SHA256 and result["runtimeBinarySha256"] == OPENBLAS_BINARY
                and result["intentProfileSha256"] == INTENT_SHA256 and result["routingAuthority"] == "none"
                and type(result["elapsedSeconds"]) in (int, float) and math.isfinite(result["elapsedSeconds"])
                and result["elapsedSeconds"] > 0,
                "Intent outcomes must retain their actual correlated runtime/model/profile result and timing")
    require(rows["firstHostEvidence"]["actionId"] == channel.lower() + "-canonical-intent-first"
            and first["intentAttemptScope"] == "first-normal-package-mission-intent-on-this-channel",
            "A later warm result cannot replace the first channel attempt")
    original = first["intentResult"]
    passed = original["actualInference"] is True and original["contractValid"] is True
    require(outcome["firstAttemptPassed"] is passed
            and outcome["firstAttemptElapsedSeconds"] == original["elapsedSeconds"]
            and outcome["successfulGenerationSeconds"] == successful["intentResult"]["elapsedSeconds"]
            and outcome["automaticWarmRetries"] == 0,
            "Derived summaries must reproduce original and explicitly separate successful timing")
    result = successful["intentResult"]
    require(rows["successfulHostEvidence"]["result"] == successful["result"] == "PASS"
            and result["actualInference"] is True and result["contractValid"] is True
            and result["elapsedSeconds"] <= 600 and result["intent"]["s"] == "resolved"
            and [{key: row[key] for key in ("k", "a", "w", "v", "u")} for row in result["intent"]["c"]]
                == [{"k": "deprioritize", "a": "5trat", "w": "all", "v": None, "u": None}],
            "Actual successful canonical inference within the unchanged service budget is still required")
    if channel == "DEV":
        require(all(outcome[name]["sha256"] == expected for name, expected in FRESH_DEV_FIRST_INTENT_LOCKS.items())
                and outcome["firstColdDeadlinePassed"] is False and original["elapsedSeconds"] == 600.002,
                "The known normal649 DEV cold600 failure and explicit root warm admission are immutable")
    else:
        provider = referenced_proof(root, outcome["priorProviderComparison"])
        compared = provider["actualOperatorOrMonitorResult"]
        require(outcome["firstMissionIntentColdClaimed"] is False
                and provider["kind"] == "root-admitted-normal-package649-phase" and provider["targetVmid"] == 649
                and provider["result"] == compared["result"] == "PASS"
                and provider["actionId"] == "main-provider-comparison" and provider["channel"] == "MAIN"
                and compared["kind"] == "actual-fresh649-normal-package-operator-step"
                and compared["targetVmid"] == 649 and compared["channel"] == "MAIN"
                and compared["action"] == "provider-test" and compared["imageRef"] == release["imageRef"]
                and compared["localAIImageRef"] == release["localAIImageRef"]
                and compared["providerTest"]["testResult"]["actualInference"] is True
                and compared["providerTest"]["testResult"]["contractValid"] is True
                and compared["providerTest"]["testResult"]["modelId"] == "qwen3.5-4b"
                and compared["providerTest"]["testResult"]["modelSha256"] == MODEL_SHA256
                and compared["providerTest"]["testResult"]["decision"] == "select"
                and compared["localAiAfter"]["runtime"]["healthy"] is True
                and compared["localAiAfter"]["runtime"]["binarySha256"] == OPENBLAS_BINARY
                and compared["localAiAfter"]["runtime"]["pid"] == first["localAiBefore"]["runtime"]["pid"]
                and compared["endedAt"] <= first["intentSubmission"]["at"]
                and first["runtimeGenerationBefore"]["sequence"] > 0,
                "MAIN mission intent follows its actual provider inference and must not be called cold")
    if passed:
        require(rows["firstHostEvidence"]["result"] == first["result"] == "PASS"
                and outcome["firstHostEvidence"] == outcome["successfulHostEvidence"]
                and outcome["firstGuestEvidence"] == outcome["successfulGuestEvidence"],
                "A successful first attempt must be reported as its own actual result")
    else:
        review = referenced_proof(root, outcome["independentFirstFailureReview"])
        admission = referenced_proof(root, outcome["explicitWarmAdmission"])
        require(rows["firstHostEvidence"]["result"] == first["result"] == "STOPPED_REQUIRES_REVIEW"
                and original["actualInference"] is False and original["contractValid"] is False
                and original["intent"] is None and original["elapsedSeconds"] >= 600
                and original["error"] == {"code": "runtime_timeout", "reason": "intent_deadline",
                    "message": "The local model did not finish the complete instruction within the interpretation time limit."}
                and review["reviewer"] == "/root" and review["coldPassed"] is False
                and review["coldSeconds"] == original["elapsedSeconds"] and review["noUsableOutput"] is True
                and review["firstIntent"]["sha256"] == outcome["firstHostEvidence"]["sha256"]
                and admission["reviewer"] == "/root" and admission["maximumWarmAttempts"] == 1
                and admission["automaticRetriesAllowed"] == 0
                and admission["coldFailureRootReview"]["sha256"] == outcome["independentFirstFailureReview"]["sha256"]
                and admission["priorGuestFailure"]["sha256"] == outcome["firstGuestEvidence"]["sha256"],
                "The guarded cold failure needs its retained root review and separately authorised warm attempt")
        require(set(admission["actions"]) == {rows["successfulHostEvidence"]["actionId"]}, "Only one sealed warm action is admitted")
        action = admission["actions"][rows["successfulHostEvidence"]["actionId"]]
        pid = first["localAiBefore"]["runtime"]["pid"]
        require(type(pid) is int and pid > 0 and pid == outcome["sameModelPid"] == review["sameHealthyModelPid"]
                == action["requiredSameModelPid"] == successful["localAiBefore"]["runtime"]["pid"]
                == successful["localAiAfter"]["runtime"]["pid"]
                and successful["intentAttemptScope"] == "explicit-reviewed-warm-attempt"
                and successful["priorIntentReview"] == action["priorIntentReview"]
                and successful["rootAdmissionSha256"] == outcome["explicitWarmAdmission"]["sha256"],
                "The explicit warm success must retain the same healthy model process and root authorisation")


def validate_fresh_unlicensed(root, reference, release, delivery):
    evidence = referenced_proof(root, reference)
    require(evidence["result"] == "PASS" and evidence["kind"] == "fresh-unlicensed-normal-umbrel-package-qualification"
            and evidence["architecture"] == "amd64" and evidence["osVersion"] == "2.0.0"
            and evidence["targetVmid"] == 649 and evidence["configuredMemoryMiB"] == 16384
            and evidence["testedChannel"] == release["channel"]
            and evidence["testedImageRef"] == release["imageRef"]
            and all(evidence[field] is True for field in ("freshNormalOwnerVerified", "normalBaselineToCandidateTransitionVerified",
                "operatorAuthenticationVerified", "actualChannelInferenceVerified", "onPreferenceRetained",
                "actualModelAndConfigurationVerified", "socketPeerIdentityVerified", "noHostControllerOrDockerSocket",
                "hardwareUnchanged", "hostReserveUnchanged", "rootFilesystemReadOnlyVerified", "transitionPreservedState"))
            and evidence["licenceOrTrialActivationPerformed"] is False
            and evidence["licenceState"] == {"registered": True, "recordedState": "inactive", "accessAllowed": False, "source": "none"}
            and evidence["paidRoutingGuardHttpStatuses"] == {"settings": 402, "workerAllocation": 402}
            and evidence["runtimeCpuLimit"] == 2 and evidence["runtimeMemoryLimitBytes"] == 6 * 1024**3
            and evidence["runtimeMemorySwapLimitBytes"] == 6 * 1024**3
            and evidence["runtimeBinarySha256"] == RUNTIME_SHA256["amd64-v2"]
            and evidence["modelSha256"] == MODEL_SHA256 and evidence["intentProfileSha256"] == INTENT_SHA256
            and evidence["requestTimeoutSeconds"] == 600,
            "Each channel needs its actual fresh normal unlicensed image/inference/auth/402/config proof")
    expected_transition = ("public080-dev-to082-dev-normal-app-manager-update", "0.9.80-dev") if release["channel"] == "DEV" else (
        "DEV-to-MAIN-normal-app-manager-update", "0.9.82-dev")
    require((evidence["transitionKind"], evidence["priorVersion"]) == expected_transition,
            "Record the actual normal DEV baseline update or later MAIN channel transition")
    validate_shared_channel_scope(evidence, release, delivery)
    validate_fresh_intent_outcome(root, evidence, release)
    validate_saved_preferences_restart_policy(root, evidence, release)
    if evidence["lifecycleScope"] == "observed-this-channel":
        validate_full_unlicensed_lifecycle(evidence)
    else:
        require(evidence["lifecycleScope"] == "explicit-shared-DEV-companion-lifecycle"
                and evidence["testedChannel"] == "MAIN" and evidence["sharedLifecycleReuseExplicit"] is True,
                "Shared lifecycle evidence must never be described as observed MAIN checks")
        shared = referenced_proof(root, evidence["sharedLifecycleEvidence"])
        require(shared["kind"] == "fresh-unlicensed-normal-umbrel-package-qualification"
                and shared["result"] == "PASS" and shared["testedChannel"] == "DEV"
                and shared["lifecycleScope"] == "observed-this-channel"
                and shared["protectedExecutableSHA256"] == evidence["protectedExecutableSHA256"]
                and shared["localAIImageRef"] == evidence["localAIImageRef"]
                and shared["runtimeBinarySha256"] == evidence["runtimeBinarySha256"]
                and shared["modelSha256"] == evidence["modelSha256"]
                and evidence["recipeParityVerified"] is True,
                "Reused DEV lifecycle must bind identical actual compiled runtime/model/recipe")
        validate_full_unlicensed_lifecycle(shared)
        validate_fresh_unlicensed(root, evidence["sharedLifecycleEvidence"],
            {**release, "channel": "DEV", "imageRef": APPLICATION_IMAGE_REFS["DEV"]}, delivery)
    return evidence


def validate_arm_package(evidence, release, delivery):
    require(evidence["result"] == "PASS" and evidence["architecture"] == "arm64"
            and evidence["kind"] == "native-container-package-qualification"
            and evidence["testedChannel"] == release["channel"]
            and evidence["testedVersion"] == recipe.VERSIONS[release["channel"]]
            and evidence["imageRef"] == release["imageRef"] and evidence["localAIImageRef"] == release["localAIImageRef"]
            and evidence["applicationPlatform"] == release["platforms"]["arm64"]
            and evidence["companionPlatform"] == release["localAIPlatforms"]["arm64"]
            and all(evidence[field] is True for field in ("operatorAuthenticationVerified", "localAiOnOffRemovalVerified",
                "socketPeerIdentityVerified", "existingMuxStatePreserved", "noHostControllerOrDockerSocket")),
            "Actual ARM normal package smoke must bind both final channel images and platform identities")
    for field in ("sourceRevision", "sourceTree", "packageProducerSourceRevision", "packageProducerSourceTree", "packageProducerInputs"):
        require(evidence[field] == release[field], "ARM application and actual package producer source bindings differ")
    require(evidence["protectedExecutableSHA256"] == delivery["platforms"]["arm64"]["protectedExecutableSHA256"],
            "ARM package client must be the actual audited protected application")
    companion = delivery["localAIPlatforms"]["arm64"]
    for field in ("supervisorSHA256", "serviceSHA256", "llamaSHA256", "configSHA256", "intentProfileSHA256",
                  "companionSourceRevision", "companionSourceTree"):
        require(evidence[field] == companion[field], "ARM package must use the actual final compiled companion/config/source")
    expected_recipe = (json.dumps(recipe.recipe_model(release["imageRef"], release["localAIImageRef"], release["channel"]), indent=2) + "\n").encode()
    require(evidence["packageRecipeSHA256"] == release["packageFiles"][APP + "/docker-compose.yml"]["sha256"] == sha256(expected_recipe)
            and evidence["runtimeCpuLimit"] == 2 and evidence["runtimeMemoryLimitBytes"] == 6 * 1024**3
            and evidence["runtimeMemorySwapLimitBytes"] == 6 * 1024**3 and evidence["runtimeUser"] == "1000:1000"
            and evidence["runtimeReadOnlyRootfsVerified"] is True and evidence["sidecarPublishedPorts"] == []
            and evidence["requestTimeoutSeconds"] == 180,
            "ARM smoke must exercise the exact generated normal recipe and retained bounds")


def validate_delivery(root, release):
    channel = release["channel"]
    reference = release["publication"]
    require(reference["path"] == f"release-records/mux-umbrel-{recipe.VERSIONS[channel]}-delivery.json"
            and DELIVERY_LOCKS[channel] is not None and reference["sha256"] == DELIVERY_LOCKS[channel],
            "Independently reviewed 0.9.82 delivery lock required")
    proof = referenced_proof(root, reference)
    require(proof["schemaVersion"] == 1 and proof["result"] == "PASS"
            and (proof["sourceRevision"], proof["sourceTree"], proof["imageRef"], proof["localAIImageRef"])
            == (release["sourceRevision"], release["sourceTree"], release["imageRef"], release["localAIImageRef"]),
            "Delivery source/image binding mismatch")
    require(proof["anonymousMuxAndCompanionIndicesVerified"] is True, "Both public immutable image indices must be verified")
    validate_component_sources(release, proof)
    validate_semantic_qualification(root, proof["semanticQualification"])
    validate_rejected_history(root, proof["rejectedVariantHistory"])
    native_performance = proof["nativeRuntimePerformance"]
    validate_performance(root, native_performance["evidence"], native_performance["summary"], "native-amd64-avx2")
    for key in ("platforms", "localAIPlatforms"):
        require(set(proof[key]) == {"amd64", "arm64"}, "An AMD-only sidecar would break existing ARM installs")
        for architecture, row in proof[key].items():
            require({field: row[field] for field in release[key][architecture]} == release[key][architecture],
                    "Unreviewed published platform identity")
            require(row["allDistributedLayersAudited"] is True and row["allLayerDigestsVerified"] is True
                    and row["noApplicationPythonSources"] is True and row["noSourceMaps"] is True
                    and row["noApplicationPrivateKeyMaterial"] is True and row["nativeStartupVerified"] is True,
                    "Actual compiled native image and all-layer protection checks required")
            if key == "platforms":
                require(SHA256.fullmatch(row["protectedExecutableSHA256"]) and row["operatorAuthenticationVerified"] is True
                        and row["httpHealthVersion"] == recipe.VERSIONS[channel] and row["freshNativeBaseRootfsVerified"] is True,
                        "MUX must be freshly compiled, started and operator-authenticated")
            else:
                cpu_profile = "amd64-v2" if architecture == "amd64" else "arm64"
                require(row["cpuProfile"] == cpu_profile and row["llamaSHA256"] == RUNTIME_SHA256[cpu_profile]
                        and row["intentProfileSHA256"] == INTENT_SHA256 and all(SHA256.fullmatch(row[field]) for field in
                        ("supervisorSHA256", "serviceSHA256", "llamaSHA256", "intentProfileSHA256")),
                        "Correct actual compiled companion architecture/profile required")
                require(row["compiledProfileVerified"] is True and row["compiledCheckVerified"] is True
                        and row["cpuBuildProofVerified"] is True, "Compiled service and CPU provenance required")
                validate_cpu_build(referenced_proof(root, row["cpuBuildProof"]), row["llamaSHA256"], cpu_profile)
                require(SHA256.fullmatch(row["configSHA256"]) and SHA256.fullmatch(row["runtimeNoticesSHA256"]),
                        "Actual runtime config/notices byte identities are required")
                validate_runtime_inputs(referenced_proof(root, row["serviceBuildInputs"]),
                    referenced_proof(root, row["runtimeConfiguration"]), row, cpu_profile)
                validate_performance(root, row["performanceEvidence"], row["performanceSummary"], cpu_profile)
    require("compiledAmdOperation" in proof, "The separately reviewed compiled cold failure outcome cannot be omitted")
    validate_compiled_amd_operation(root, proof["compiledAmdOperation"], proof)
    require(set(proof["umbrelQualification"]) == {"1.7.4", "2.0.0"}, "Both supported Umbrel update contracts must be exercised")
    for version, reference in proof["umbrelQualification"].items():
        validate_memory_hold_update(root, referenced_proof(root, reference), version, release, proof)
    validate_fresh_unlicensed(root, proof["freshUnlicensedUmbrelQualification"], release, proof)
    arm = referenced_proof(root, proof["armNativePackageQualification"])
    validate_arm_package(arm, release, proof)
    return proof


def validate(root=ROOT):
    release = record(root)
    validate_package(root, release)
    validate_delivery(root, release)
    return release


if __name__ == "__main__":
    print(json.dumps(validate()))
