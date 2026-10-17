"""Synthetic adversarial successor admission; no runtime qualification claims."""
import copy
import fnmatch
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mux_local_ai_umbrel_release as mux

CHANNEL = json.loads((ROOT / mux.PREDECESSOR_NAME).read_text())["channel"]
SUPERVISOR = "ghcr.io/willitmod/5tratmux-app:local-ai-0.1.9-umbrel@sha256:" + "2" * 64
SYNTHETIC_SELECTED_BASELINE = mux.OPENBLAS_BINARY  # Only the digest is real; invented inference rows stay explicit fixtures.
SYNTHETIC_COMPANION_SOURCES = {"amd64": {"sourceRevision": "a" * 40, "sourceTree": "b" * 40},
    "arm64": dict(mux.APPLICATION_SOURCE)}
SYNTHETIC_PACKAGE_SOURCE = {"sourceRevision": "c" * 40, "sourceTree": "d" * 40}
SYNTHETIC_PACKAGE_INPUTS = {"packaging/umbrel-local-ai-release/prepare_package.py": "e" * 64,
                          "packaging/umbrel-local-ai-release/pre-start": mux.HOOK_SHA256}
PACKAGE_FIELDS = {"packageProducerSourceRevision": SYNTHETIC_PACKAGE_SOURCE["sourceRevision"],
                  "packageProducerSourceTree": SYNTHETIC_PACKAGE_SOURCE["sourceTree"],
                  "packageProducerInputs": SYNTHETIC_PACKAGE_INPUTS}


def images(channel=CHANNEL):
    return mux.APPLICATION_IMAGE_REFS[channel]


def corpus(cpu_profile="arm64"):
    binary = mux.RUNTIME_SHA256[cpu_profile] or SYNTHETIC_SELECTED_BASELINE
    evidence = {"syntheticUnitFixture": True, "kind": "unreviewed-real-inference-successor-evidence",
        "startedAt": "2026-10-16T00:00:00+00:00", "endedAt": "2026-10-16T00:20:00+00:00",
        "completeCorpus": True, "automaticPasses": 25, "ownedRuntimeStopped": True, "routingAuthority": "none",
        "runtimeBinarySha256": binary, "expectedRuntimeBinarySha256": binary,
        "runtimeCpuProfile": None, "intentProfileSha256": mux.INTENT_SHA256,
        "modelSha256": mux.MODEL_SHA256, "modelId": "qwen3.5-4b", "productionEligible": False,
        "corpusSha256": mux.CORPUS_SHA256, "expectedCorpusCaseIds": list(mux.CORPUS_IDS),
        "plannedCaseIds": list(mux.CORPUS_IDS), "cases": [{"id": name, "verdict": "pass", "seconds": 40.0,
        "result": {"actualInference": True, "contractValid": True}} for name in mux.CORPUS_IDS]}
    if cpu_profile == "native-amd64-avx2":
        evidence["automaticPasses"] = 24
        evidence["cases"][0].update(verdict="fail", seconds=600.006 if cpu_profile == "amd64-v2" else 180.004,
            result={"actualInference": False, "contractValid": False,
                    "error": {"code": "runtime_timeout", "reason": "intent_deadline"}})
    return evidence


def cpu_build(profile, binary):
    if profile == "amd64-v2":
        # Retained actual model-free source/ELF/probe output; unit execution
        # does not perform or authorize inference on this artifact.
        return json.loads((ROOT / "tests/fixtures/mux-openblas034-model-free-build.json").read_text())
    return {"syntheticUnitFixture": True, "kind": "actual-" + profile + "-runtime-build",
        "sourceCommit": mux.UPSTREAM_COMMIT, "sourceArchiveSha256": mux.UPSTREAM_ARCHIVE_SHA256,
        "binarySha256": binary, "cpuProfile": profile, "compilerCommandsChecked": 1,
        "productionQualificationGranted": False}


def runtime_inputs(profile, binary):
    config = {"syntheticUnitFixture": True, "runtime": {"binarySha256": binary, "cpuProfile": profile,
        "binary": "/opt/5tratmux-local-ai/bin/llama-server", "modelDirectory": "/data/local-ai/models",
        "threads": 2, "requestTimeoutSeconds": mux.SERVICE_REQUEST_BUDGET_SECONDS[profile]},
        "resources": {"reserveBytes": 1073741824, "reserveFraction": 0.15,
                      "monitorSeconds": 5, "allowUnvalidatedModels": True}}
    inputs = {"syntheticUnitFixture": True, "mode": "umbrel", "cpuProfile": profile, "binarySha256": binary,
        "intentProfileSha256": mux.INTENT_SHA256, "privateSourceIncludedInFinalImage": False,
        "modelWeightsIncluded": False, "realInferenceQualification": "separate-required",
        "inputHashes": {"LLAMA-LICENSE": mux.LLAMA_LICENCE}}
    if profile == "amd64-v2":
        inputs.update(thirdPartyNoticesSha256=mux.OPENBLAS_NOTICES, upstreamSourceModified=True,
            upstreamPatch={("sha256" if key == "patchSha256" else key): value for key, value in mux.OPENBLAS_PATCH.items()},
            staticOpenBlas={"version": "0.3.34", "sourceCommit": "e0166008be8e466242aa76b2ff75ce3f0fbf574a",
                "licenceSha256": mux.OPENBLAS_LICENCE, "mathTeamMaximumThreads": 2,
                "mathTeamIncludesCallingThread": True, "admissionScope": "minimum-cpu-only",
                "performanceQualificationGranted": False, "threadTimeoutExponent": 4,
                "compiledInitialThreadTimeoutTicks": 16})
        inputs["inputHashes"].update({"OpenBLAS-LICENSE": mux.OPENBLAS_LICENCE,
                                      "THIRD_PARTY_NOTICES": mux.OPENBLAS_NOTICES})
    return inputs, config


def channel_scope(channel=CHANNEL):
    return {**mux.APPLICATION_SOURCE, "testedChannel": channel, "testedVersion": mux.recipe.VERSIONS[channel],
        "testedImageRef": images(channel), "localAIImageRef": SUPERVISOR,
        "testedApplicationConfigDigest": mux.APPLICATION_AMD64_CONFIGS[channel],
        "testedPackageRecipeSHA256": mux.sha256((json.dumps(mux.recipe.recipe_model(images(channel), SUPERVISOR, channel), indent=2)+"\n").encode()),
        "protectedExecutableSHA256": "7" * 64}


def fresh_unlicensed(channel=CHANNEL):
    return {**channel_scope(channel), "syntheticUnitFixture": True, "result": "PASS",
        "kind": "fresh-unlicensed-normal-umbrel-package-qualification", "architecture": "amd64",
        "osVersion": "2.0.0", "targetVmid": 649, "configuredMemoryMiB": 16384,
        **{name: True for name in ("freshNormalOwnerVerified", "normalBaselineToCandidateTransitionVerified",
            "operatorAuthenticationVerified", "actualChannelInferenceVerified", "onPreferenceRetained",
            "actualModelAndConfigurationVerified", "socketPeerIdentityVerified", "noHostControllerOrDockerSocket",
            "hardwareUnchanged", "hostReserveUnchanged", "rootFilesystemReadOnlyVerified",
            "onOffPersistenceVerified", "normalAppStopStartVerified", "runtimeRemovalReinstallOffVerified",
            "modelAndPreferencesRetained", "noEntitlementStop", "noOom", "transitionPreservedState")},
        "transitionKind": "public080-dev-to082-dev-normal-app-manager-update" if channel == "DEV" else "DEV-to-MAIN-normal-app-manager-update",
        "priorVersion": "0.9.80-dev" if channel == "DEV" else "0.9.82-dev",
        "licenceOrTrialActivationPerformed": False,
        "licenceState": {"registered": True, "recordedState": "inactive", "accessAllowed": False, "source": "none"},
        "paidRoutingGuardHttpStatuses": {"settings": 402, "workerAllocation": 402},
        "runtimeCpuLimit": 2, "runtimeMemoryLimitBytes": 6 * 1024**3, "runtimeMemorySwapLimitBytes": 6 * 1024**3,
        "runtimeBinarySha256": SYNTHETIC_SELECTED_BASELINE, "modelSha256": mux.MODEL_SHA256,
        "intentProfileSha256": mux.INTENT_SHA256, "requestTimeoutSeconds": 600,
        "continuousOnSeconds": 661.0, "lifecycleScope": "observed-this-channel",
        "firstIntentOutcome": fresh_intent_fixture(channel)[0],
        "restartPolicyEvidence": restart_policy_fixture(channel)[0],
        "savedOnAndOffPreferencesRetained":True,"restartSafeOffVerified":True,"explicitOwnerStartVerified":True,
        "automaticModelRestoreVerified":False,"modelRestartPolicy":"model-Off-on-service-restart-explicit-owner-Start"}


def restart_policy_fixture(channel):
    documents={}
    def retain(name,value):
        documents[name]=value
        return {"path":"release-records/"+name,"sha256":mux.sha256((json.dumps(value,sort_keys=True)+"\n").encode())}
    status={"enabled":False,"runtime":{"running":False,"healthy":False,"pid":None},
        "phase":"off","busy":False,"error":None,
        "installation":{"installed":True,"running":True,"supported":True,"configurationMatches":True,
            "busy":False,"error":None,"updateRequired":False},
        "preferences":{"desiredEnabled":True,"state":"loaded","resumeState":"pending","restoreAuthority":"host"}}
    pending={"result":"PASS","controlRequestsSent":0,"automaticModelRestoreVerified":False,"status":status,
        "memoryEvents":{"oom":0,"oom_kill":0},"retainedModelPhysicalHash":{"sha256":mux.MODEL_SHA256},"stateFiles":{}}
    safe={"syntheticUnitFixture":True,"kind":"root-admitted-normal-package649-phase","targetVmid":649,
        "channel":channel,"result":"PASS","automaticModelRestoreVerified":False,
        "beforeSnapshot":{"stateFiles":{}},"afterSnapshot":{"imageId":mux.APPLICATION_AMD64_CONFIGS[channel],"stateFiles":{}}}
    refs={}
    if channel=="DEV":
        original=retain("dev-original-auto-on-expectation-failed.json",{"syntheticUnitFixture":True,
            "result":"STOPPED_REQUIRES_REVIEW","latestRestoredLocalAI":{"result":"READINESS_TIMEOUT"}})
        safe.update(afterSavedOnRestartSafeOff=pending,reconciledPriorRestartEvidence=original,
            normalManagerMutationRepeated=False,apiMutationAttempts=[])
        refs["originalRestartExpectationFailure"]=original
    else:safe["afterNormalUpdateLocalAI"]=pending
    refs["safeOffEvidence"]=retain(channel.lower()+"-saved-on-safe-off.json",safe)
    started={"kind":"actual-fresh649-normal-package-operator-step","targetVmid":649,"channel":channel,
        "result":"PASS","action":"enable","imageRef":images(channel),"localAIImageRef":SUPERVISOR,
        "singleMutationIntent":{"route":"/api/local-ai/enable"},"controlResponse":{"httpStatus":200,"value":{"accepted":True}},
        "localAiBefore":status,"applicationBoundaryAfter":{"containerId":"synthetic-app"},
        "companionBoundaryAfter":{"containerId":"synthetic-companion"},"stableFilesAfter":{}}
    refs["explicitOwnerStartEvidence"]=retain(channel.lower()+"-explicit-owner-start.json",{
        "syntheticUnitFixture":True,"kind":"root-admitted-normal-package649-phase","targetVmid":649,
        "channel":channel,"result":"PASS","explicitOwnerStart":True,"automaticModelRestoreVerified":False,
        "actualOperatorOrMonitorResult":started})
    refs["explicitOwnerStartReadiness"]=retain(channel.lower()+"-explicit-owner-settled-on.json",{
        "syntheticUnitFixture":True,"result":"PASS","controlRequestsSent":0,
        "applicationContainerId":"synthetic-app","companionContainerId":"synthetic-companion","stateFiles":{},
        "status":{"enabled":True,"phase":"ready","busy":False,"preferences":{"desiredEnabled":True},
            "runtime":{"running":True,"healthy":True,"pid":123,"binarySha256":mux.OPENBLAS_BINARY},
            "modelSha256":mux.MODEL_SHA256,"capabilities":{"missionIntentProfileSha256":mux.INTENT_SHA256}}})
    return refs,documents


def fresh_intent_fixture(channel):
    documents = {}
    def retain(name, value):
        documents[name] = value
        return {"path": "release-records/" + name,
                "sha256": mux.sha256((json.dumps(value, sort_keys=True) + "\n").encode())}
    def host(guest, action_id):
        return {"syntheticUnitFixture": True, "kind": "root-admitted-normal-package649-phase", "targetVmid":649,
            "channel":channel, "result":guest["result"], "actionId":action_id, "apiMutationAttempts":[],
            "automaticMutationRetries":0, "actualOperatorOrMonitorResult":guest}
    successful_result = {"requestId":"synthetic", "inputSha256":"1"*64, "modelSha256":mux.MODEL_SHA256,
        "runtimeBinarySha256":mux.OPENBLAS_BINARY, "intentProfileSha256":mux.INTENT_SHA256,
        "routingAuthority":"none", "actualInference":True, "contractValid":True, "elapsedSeconds":100.0,
        "intent":{"s":"resolved","c":[{"k":"deprioritize","a":"5trat","w":"all","v":None,"u":None}]}}
    first = {"syntheticUnitFixture":True, "kind":"actual-fresh649-normal-package-operator-step", "targetVmid":649,
        "channel":channel,"action":"minimal-home-intent","imageRef":images(channel),"localAIImageRef":SUPERVISOR,
        "automaticMutationRetry":False,"filesystemOrPromptCacheCleared":False,
        "intentAttemptScope":"first-normal-package-mission-intent-on-this-channel",
        "intentSubmission":{"requestId":"synthetic","inputSha256":"1"*64,"at":"2026-10-16T02:00:00+00:00"},
        "localAiBefore":{"runtime":{"pid":89}},"localAiAfter":{"runtime":{"pid":89}},
        "runtimeGenerationBefore":{"sequence":1 if channel=="MAIN" else 0},
        "result":"PASS","intentResult":copy.deepcopy(successful_result)}
    if channel == "DEV":
        first.update(result="STOPPED_REQUIRES_REVIEW",intentResult={**successful_result,"actualInference":False,
            "contractValid":False,"intent":None,"elapsedSeconds":600.002,
            "error":{"code":"runtime_timeout","reason":"intent_deadline",
                "message":"The local model did not finish the complete instruction within the interpretation time limit."}})
    guest_ref=retain(channel.lower()+"-first-guest.json",first)
    host_ref=retain(channel.lower()+"-first-host.json",host(first,channel.lower()+"-canonical-intent-first"))
    outcome={"firstHostEvidence":host_ref,"firstGuestEvidence":guest_ref,"successfulHostEvidence":host_ref,
        "successfulGuestEvidence":guest_ref,"firstAttemptPassed":channel=="MAIN",
        "firstAttemptElapsedSeconds":first["intentResult"]["elapsedSeconds"],"successfulGenerationSeconds":100.0,
        "automaticWarmRetries":0}
    if channel == "DEV":
        review=retain("dev-first-root-review.json",{"syntheticUnitFixture":True,"reviewer":"/root","coldPassed":False,
            "coldSeconds":600.002,"noUsableOutput":True,"firstIntent":host_ref,"sameHealthyModelPid":89})
        prior={"reportId":"dev-canonical-intent-first","sha256":guest_ref["sha256"],
            "explicitWarmAttemptAuthorised":True,"rootReviewSha256":review["sha256"]}
        admission=retain("dev-warm-root-admission.json",{"syntheticUnitFixture":True,"reviewer":"/root",
            "maximumWarmAttempts":1,"automaticRetriesAllowed":0,"coldFailureRootReview":review,"priorGuestFailure":guest_ref,
            "actions":{"dev-explicit-warm":{"requiredSameModelPid":89,"priorIntentReview":prior}}})
        warm={**first,"result":"PASS","intentResult":successful_result,
            "intentAttemptScope":"explicit-reviewed-warm-attempt","priorIntentReview":prior,
            "rootAdmissionSha256":admission["sha256"]}
        outcome.update(successfulGuestEvidence=retain("dev-warm-guest.json",warm),
            successfulHostEvidence=retain("dev-warm-host.json",host(warm,"dev-explicit-warm")),
            independentFirstFailureReview=review,explicitWarmAdmission=admission,sameModelPid=89,firstColdDeadlinePassed=False)
    else:
        provider={"kind":"actual-fresh649-normal-package-operator-step","targetVmid":649,"channel":"MAIN",
            "action":"provider-test","result":"PASS","imageRef":images(channel),"localAIImageRef":SUPERVISOR,
            "providerTest":{"testResult":{"actualInference":True,"contractValid":True,
                "modelId":"qwen3.5-4b","modelSha256":mux.MODEL_SHA256,"decision":"select"}},
            "localAiAfter":{"runtime":{"pid":89,"healthy":True,"binarySha256":mux.OPENBLAS_BINARY}},
            "endedAt":"2026-10-16T01:59:00+00:00"}
        outcome.update(firstMissionIntentColdClaimed=False,
            priorProviderComparison=retain("main-prior-provider.json",host(provider,"main-provider-comparison")))
    return outcome, documents


def existing_lab_authority_adaptation(root, target, channel=CHANNEL):
    def retain_actual(name):
        raw = (ROOT / "tests/fixtures" / name).read_bytes()
        path = "release-records/" + name
        (root / path).write_bytes(raw)
        return {"path": path, "sha256": mux.sha256(raw)}
    original = mux.recipe.recipe_model(images(channel), SUPERVISOR, channel)
    adapted = copy.deepcopy(original)
    adapted["services"]["server"]["env_file"] = mux.EXISTING_LAB_ENV_FILE_REFERENCE
    overlay = {"services": {"server": {"env_file": mux.EXISTING_LAB_ENV_FILE_REFERENCE}}}
    source_hash = lambda value: mux.sha256((json.dumps(value, indent=2)+"\n").encode())
    return {"paidIdentityScope": "pre-existing-owned-lab-paid-identity",
        "defaultProductionAuthorityPaidProofClaimed": False,
        "existingLabAuthorityAdaptation": {"kind": "retained-existing-lab-authority-env-file-reference",
            "serverEnvFileReferences": mux.EXISTING_LAB_ENV_FILE_REFERENCE,
            "authorityValuesUnchanged": True, "authorityKeysCopied": False, "licenceGrantOrProofEdited": False,
            "classificationEvidence": retain_actual("authority-source-"+str(target)+"-readonly.json"),
            "referenceEvidence": retain_actual("authority-env-file-reference-"+str(target)+"-readonly.json"),
            "fileBefore": copy.deepcopy(mux.EXISTING_LAB_AUTHORITY_FILE),
            "fileAfter": copy.deepcopy(mux.EXISTING_LAB_AUTHORITY_FILE),
            "licensingEnvironmentMappingSha256Before": mux.EXISTING_LAB_AUTHORITY_ENV_SHA256,
            "licensingEnvironmentMappingSha256After": mux.EXISTING_LAB_AUTHORITY_ENV_SHA256,
            "preExistingInstalledComposeSha256": mux.EXISTING_LAB_AUTHORITY_SOURCE[target]["installedComposeSha256"],
            "originalPackageRecipeSHA256": source_hash(original), "qaOverlaySHA256": source_hash(overlay),
            "adaptedQaSourceRecipeSHA256": source_hash(adapted),
            "minimalDifference": [{"operation": "add", "path": "/services/server/env_file",
                                   "value": mux.EXISTING_LAB_ENV_FILE_REFERENCE}]}}


def compiled_operation_fixture(retain, row):
    identity = {"sourceRevision": row["companionSourceRevision"], "sourceTree": row["companionSourceTree"],
        "imageId": row["configDigest"], "imageConfigId": row["configDigest"],
        "compiledServiceSha256": row["serviceSHA256"], "compiledSupervisorSha256": row["supervisorSHA256"],
        "runtimeBinarySha256": mux.OPENBLAS_BINARY, "intentProfileSha256": mux.INTENT_SHA256,
        "modelSha256": mux.MODEL_SHA256}
    raw = {"syntheticUnitFixture": True, **identity,
        "kind": "unreviewed-real-compiled-amd64-v2-bounded-UDS-operation-evidence",
        "scope": "bounded-compiled-operation-not-full25", "cpuLimit": 2,
        "memoryLimitBytes": 6*1024**3,
        "requestTimeoutSeconds": 600, "routingAuthority": "none",
        "compiledBoundedOperationExecutionPassed": False, "modelInferenceAccepted": False,
        "completeCorpus": False, "completeRequestedCases": True, "automaticPasses": 1, "automaticWarmRetries": 0,
        "selectedCanonicalCaseIds": ["minimal-home", "coordinated-targets"],
        "cases": [{"id": "minimal-home", "verdict": "fail", "result": {"actualInference": False,
            "contractValid": False, "intent": None, "error": {"code": "runtime_timeout", "reason": "intent_deadline"},
            "elapsedSeconds": 600.002}, "runtime": {"pid": 37, "healthy": True, "generation": {"completionReceived": False}}},
            {"id": "coordinated-targets", "verdict": "pass", "result": {"actualInference": True,
            "contractValid": True, "elapsedSeconds": 137.701, "intent": {"s": "resolved", "c": [
                {"k": "deprioritize", "a": asset, "w": "all", "v": None, "u": None} for asset in ("5trat", "bitcoin")]}},
             "runtime": {"pid": 37, "healthy": True}}],
        "normalCompare": {"actualInference": True, "contractValid": True, "decision": "select",
            "selectedCandidateId": "retain-current", "runtimeBinarySha256": mux.OPENBLAS_BINARY,
            "modelSha256": mux.MODEL_SHA256, "elapsedSeconds": 193.017},
        "normalComparePassed": True, "onMonitorPassed": True, "onMonitorSeconds": 934.461,
        "disableReceipt": {"code":200,"value":{"accepted":True,"phase":"off","preferencesSaved":True}},
        "finalOff": {"enabled":False,"runtime":{"running":False}}, "ownedModelStopped":True}
    raw_ref = retain("compiled-amd-synthetic-raw.json", raw)
    summary = {"syntheticUnitFixture": True,
        "kind": "producer-scoped-compiled-amd595-cold-timeout-and-same-process-recovery-outcome",
        "runtimeCpuLimit":2,"runtimeMemoryLimitBytes":6*1024**3,"runtimeMemorySwapLimitBytes":6*1024**3,
        "rawEvidenceSHA256": raw_ref["sha256"], "rawReceipts": {"final-operation-inventory.json":"a"*64},
        "originalDriverExit":1,"originalCompiledBoundedOperationExecutionPassed":False,
        "cold":{"generationElapsedSeconds":600.002,"firstColdPassClaimed":False},
        "warmRecovery":{"generationElapsedSeconds":137.701}, "normalComparison":{"elapsedSeconds":193.017},
        "onEvidence":{"reportedElapsedSeconds":934.461,"separatePassive660SampleSweepPerformed":False,
            "intermediateStatusPollsPersisted":False},"offAndCleanup":{"cachedModelUnchanged":True}}
    summary_ref = retain("compiled-amd-synthetic-summary.json", summary)
    review = {"syntheticUnitFixture":True,"reviewer":"/root", "scopeDecision":"SCOPED_COLD_FAILURE_AND_WARM_RECOVERY_ACCEPTED",
        "rawEvidenceSha256":raw_ref["sha256"],"producerOutcomeSummarySha256":summary_ref["sha256"],
        "rawInventorySha256":"a"*64,"originalClientExitCode":1,"compiledColdGenerationSeconds":600.002,
        "warmGenerationSeconds":137.701,"comparisonGenerationSeconds":193.017,"onObservedSeconds":934.461,
        **{name: identity[name] for name in ("imageId","sourceRevision","sourceTree")},
        **{name:False for name in ("originalAggregatePassed","compiledColdDeadlinePassed",
            "firstColdPerformanceReliabilityGranted","fullCompiled25CorpusClaimed","passive660SampleSweepPerformed",
            "actual69DeploymentAcceptanceGranted","publicationGranted")},
        **{name:True for name in ("sourceFull25CorpusAcceptanceStillRequired","normalPackageQaStillRequired",
            "offAndModelReleaseAccepted","modelCachePreserved","ownedContainersRemoved")}}
    return {"rawEvidence": raw_ref,"producerOutcomeSummary":summary_ref,
            "independentRootReview":retain("compiled-amd-synthetic-root-review.json",review)}


class SuccessorAdmissionTests(unittest.TestCase):
    def test_workflow_covers_all_retained_evidence_and_supporting_fixtures(self):
        workflow=mux.yaml.safe_load((ROOT/'.github/workflows/validate-mux-umbrel.yml').read_text())
        triggers=workflow.get('on',workflow.get(True))
        changed_files=('release-records/normal649-dev-intent.json','release-records/normal-existing-642-capture.json',
            'release-records/root-companion-public-admission.json','release-records/authority-source-642-readonly.json',
            'tests/fixtures/authority-source-642-readonly.json','tests/fixtures/mux-openblas034-model-free-build.json')
        for event in ('pull_request','push'):
            for path in changed_files:
                with self.subTest(event=event,path=path):
                    self.assertTrue(any(fnmatch.fnmatchcase(path,pattern)for pattern in triggers[event]['paths']))

    def test_reviewed_model_free_build_requires_exact_patch_defaults_and_bounded_numeric_probes(self):
        raw = (ROOT / "tests/fixtures/mux-openblas034-model-free-build.json").read_bytes()
        self.assertEqual(mux.sha256(raw), "d0bc0dfb5c3fa94b94e70c99ddfd8b3f1832461b0920e2f25080092efc066315")
        actual = json.loads(raw)
        mux.validate_cpu_build(actual, mux.OPENBLAS_BINARY, "amd64-v2")
        for mutate in (lambda x: x.update(kind="actual-amd64-v2-runtime-build"),
                lambda x: x.update(upstreamSourceModified=False),
                lambda x: x["upstreamPatch"].update(afterSha256="0" * 64),
                lambda x: x.update(actualDefaultGgmlPollingLevel=50),
                lambda x: x.update(compiledInitialOpenBlasThreadTimeoutTicks=2**28),
                lambda x: x.update(openblasMathTeamMaximumThreads=64),
                lambda x: x["openblasOverrideProbe"]["result"].update(apiOverrideClamped=False),
                lambda x: x["openblasProbe"]["shapes"][0].update(correct=False),
                lambda x: x.update(guardedInstructionSites=63),
                lambda x: x.update(productionQualificationGranted=True)):
            changed = copy.deepcopy(actual); mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(AssertionError):
                mux.validate_cpu_build(changed, mux.OPENBLAS_BINARY, "amd64-v2")

    def test_actual_packaged_profile_budgets_and_licences_do_not_weaken_resource_guards(self):
        for profile in ("amd64-v2", "arm64"):
            binary = mux.OPENBLAS_BINARY if profile == "amd64-v2" else mux.RUNTIME_SHA256[profile]
            inputs, config = runtime_inputs(profile, binary)
            row = {"llamaSHA256": binary, "runtimeNoticesSHA256": mux.OPENBLAS_NOTICES if profile == "amd64-v2" else mux.LLAMA_LICENCE,
                "runtimeConfiguration": {"sha256": "1" * 64}, "configSHA256": "1" * 64,
                "runtimeConfigurationVerified": True, "runtimeNoticesVerified": True, "runtimeReadOnlyRootfsVerified": True}
            mux.validate_runtime_inputs(inputs, config, row, profile)
            for mutate in (lambda i,c,r: c["runtime"].update(requestTimeoutSeconds=180 if profile == "amd64-v2" else 600),
                    lambda i,c,r: c["runtime"].update(threads=4),
                    lambda i,c,r: c["resources"].update(reserveBytes=0),
                    lambda i,c,r: c["resources"].update(reserveFraction=0),
                    lambda i,c,r: r.update(runtimeReadOnlyRootfsVerified=False),
                    lambda i,c,r: i["inputHashes"].update({"LLAMA-LICENSE": "0" * 64})):
                staged, configured, record = copy.deepcopy((inputs, config, row));mutate(staged,configured,record)
                with self.subTest(profile=profile, mutation=mutate), self.assertRaises(AssertionError):
                    mux.validate_runtime_inputs(staged, configured, record, profile)
            if profile == "amd64-v2":
                for mutate in (lambda x: x["inputHashes"].update({"OpenBLAS-LICENSE": "0" * 64}),
                        lambda x: x.update(thirdPartyNoticesSha256="0" * 64),
                        lambda x: x["staticOpenBlas"].update(performanceQualificationGranted=True)):
                    changed=copy.deepcopy(inputs);mutate(changed)
                    with self.subTest(mutation=mutate), self.assertRaises(AssertionError):
                        mux.validate_runtime_inputs(changed, config, row, profile)
        arm = corpus(); arm["cases"][0]["seconds"] = 200
        self.assertFalse(mux.performance_summary(arm, "arm64")["allCasesPassedWithinServiceBudget"])
        amd = corpus("amd64-v2"); amd["cases"][0].update(verdict="pass", seconds=596.83,
            result={"actualInference":True,"contractValid":True});amd["automaticPasses"]=25
        self.assertTrue(mux.performance_summary(amd, "amd64-v2")["allCasesPassedWithinServiceBudget"])
        self.assertEqual(mux.performance_summary(amd, "amd64-v2")["configuredServiceBudgetSeconds"], 600)

    def test_existing8gb_normal_update_reports_real_ram_hold_without_claiming_on_or_inference(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release,proof,_=self.delivery_fixture(root)
            evidence=mux.referenced_proof(root,proof["umbrelQualification"]["1.7.4"])
            mux.validate_memory_hold_update(root,evidence,"1.7.4",release,proof)
            for mutate in (lambda x:x.update(onOrInferenceClaimed=True),
                    lambda x:x.update(existingPaidIdentityPreserved=False),
                    lambda x:x.update(hardwareUnchanged=False),
                    lambda x:x.update(runtimeMemoryLimitBytes=8*1024**3),
                    lambda x:x["memoryAdmission"].update(hostTotalBytes=0),
                    lambda x:x["memoryAdmission"].update(hostReserveBytes=0),
                    lambda x:x["memoryAdmission"].update(hostAvailableBytes=8*1024**3)):
                changed=copy.deepcopy(evidence);mutate(changed)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):
                    mux.validate_memory_hold_update(root,changed,"1.7.4",release,proof)

    def test_existing_lab_paid_adaptation_cannot_be_relabelled_or_expand_its_existing_override(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release,proof,retain=self.delivery_fixture(root)
            evidence=mux.referenced_proof(root,proof["umbrelQualification"]["1.7.4"])
            mux.validate_memory_hold_update(root,evidence,"1.7.4",release,proof)
            for mutate in (lambda x:x.update(paidIdentityScope="production-paid-identity"),
                    lambda x:x.update(defaultProductionAuthorityPaidProofClaimed=True),
                    lambda x:x["existingLabAuthorityAdaptation"].update(authorityValuesUnchanged=False),
                    lambda x:x["existingLabAuthorityAdaptation"].update(authorityKeysCopied=True),
                    lambda x:x["existingLabAuthorityAdaptation"].update(licenceGrantOrProofEdited=True),
                    lambda x:x["existingLabAuthorityAdaptation"].update(serverEnvFileReferences=["/tmp/arbitrary.env"]),
                    lambda x:x["existingLabAuthorityAdaptation"]["fileAfter"].update(sha256="0"*64),
                    lambda x:x["existingLabAuthorityAdaptation"]["fileBefore"].update(mode="0o644"),
                    lambda x:x["existingLabAuthorityAdaptation"].update(licensingEnvironmentMappingSha256After="0"*64),
                    lambda x:x["existingLabAuthorityAdaptation"].update(preExistingInstalledComposeSha256="0"*64),
                    lambda x:x["existingLabAuthorityAdaptation"].update(originalPackageRecipeSHA256="0"*64),
                    lambda x:x["existingLabAuthorityAdaptation"].update(qaOverlaySHA256="0"*64),
                    lambda x:x["existingLabAuthorityAdaptation"].update(adaptedQaSourceRecipeSHA256="0"*64),
                    lambda x:x["existingLabAuthorityAdaptation"]["minimalDifference"].append(
                        {"operation":"add","path":"/services/server/environment/MUX_LICENSING_URL","value":"arbitrary"}),
                    lambda x:x["existingLabAuthorityAdaptation"]["classificationEvidence"].update(sha256="0"*64)):
                changed=copy.deepcopy(evidence);mutate(changed)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):
                    mux.validate_memory_hold_update(root,changed,"1.7.4",release,proof)
            changed=copy.deepcopy(evidence)
            actual=mux.referenced_proof(root,changed["existingLabAuthorityAdaptation"]["classificationEvidence"])
            actual["authoritySourceClassification"]="production-paid-authority"
            changed["existingLabAuthorityAdaptation"]["classificationEvidence"]=retain("rewritten-authority-source.json",actual)
            with self.assertRaises(AssertionError):
                mux.validate_memory_hold_update(root,changed,"1.7.4",release,proof)

    def test_separate_compiled_outcome_retains_failed_cold_and_scope_after_recomputed_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release,proof,retain=self.delivery_fixture(root)
            original=proof["compiledAmdOperation"]
            values={key:mux.referenced_proof(root,ref) for key,ref in original.items()}
            def check(data):
                raw_ref=retain("compiled-adversarial-raw.json",data["rawEvidence"])
                summary=copy.deepcopy(data["producerOutcomeSummary"]);summary["rawEvidenceSHA256"]=raw_ref["sha256"]
                summary_ref=retain("compiled-adversarial-summary.json",summary)
                review=copy.deepcopy(data["independentRootReview"])
                review.update(rawEvidenceSha256=raw_ref["sha256"],producerOutcomeSummarySha256=summary_ref["sha256"])
                refs={"rawEvidence":raw_ref,"producerOutcomeSummary":summary_ref,
                    "independentRootReview":retain("compiled-adversarial-review.json",review)}
                with patch.dict(mux.COMPILED_AMD_OPERATION_LOCKS,{key:ref["sha256"]for key,ref in refs.items()}):
                    return mux.validate_compiled_amd_operation(root,refs,proof)
            check(values)
            for mutate in (lambda x:x["rawEvidence"].update(compiledBoundedOperationExecutionPassed=True),
                    lambda x:x["rawEvidence"].update(completeCorpus=True),
                    lambda x:x["rawEvidence"]["cases"][0].update(verdict="pass"),
                    lambda x:x["rawEvidence"]["cases"][0]["result"].update(elapsedSeconds=599),
                    lambda x:x["rawEvidence"]["cases"][1]["runtime"].update(pid=38),
                    lambda x:x["rawEvidence"]["cases"][1]["result"]["intent"]["c"].pop(),
                    lambda x:x["rawEvidence"].update(imageId="sha256:"+"0"*64),
                    lambda x:x["rawEvidence"].update(compiledServiceSha256="0"*64),
                    lambda x:x["rawEvidence"]["normalCompare"].update(contractValid=False),
                    lambda x:x["rawEvidence"]["finalOff"]["runtime"].update(running=True),
                    lambda x:x["producerOutcomeSummary"].update(originalDriverExit=0),
                    lambda x:x["producerOutcomeSummary"]["cold"].update(firstColdPassClaimed=True),
                    lambda x:x["producerOutcomeSummary"]["onEvidence"].update(separatePassive660SampleSweepPerformed=True),
                    lambda x:x["independentRootReview"].update(publicationGranted=True),
                    lambda x:x["independentRootReview"].update(sourceFull25CorpusAcceptanceStillRequired=False),
                    lambda x:x["independentRootReview"].update(fullCompiled25CorpusClaimed=True)):
                changed=copy.deepcopy(values);mutate(changed)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):check(changed)

    def test_fresh_unlicensed_actual_channel_proof_and_explicit_shared_lifecycle_scope(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(mux.RUNTIME_SHA256,{"amd64-v2":mux.OPENBLAS_BINARY}):
            root=Path(directory);release,proof,retain=self.delivery_fixture(root)
            reference=proof["freshUnlicensedUmbrelQualification"]
            mux.validate_fresh_unlicensed(root,reference,release,proof)
            for mutate in (lambda x:x["licenceState"].update(recordedState="active"),
                    lambda x:x.update(licenceOrTrialActivationPerformed=True),
                    lambda x:x.update(actualChannelInferenceVerified=False),
                    lambda x:x.update(runtimeMemoryLimitBytes=8*1024**3),
                    lambda x:x.update(continuousOnSeconds=659),
                    lambda x:x["paidRoutingGuardHttpStatuses"].update(settings=200)):
                changed=fresh_unlicensed();mutate(changed)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):
                    mux.validate_fresh_unlicensed(root,retain("changed-fresh.json",changed),release,proof)
            main=fresh_unlicensed("MAIN");main.update(lifecycleScope="explicit-shared-DEV-companion-lifecycle",
                sharedLifecycleReuseExplicit=True,recipeParityVerified=True,
                sharedLifecycleEvidence=retain("shared-dev.json",fresh_unlicensed("DEV")))
            for field in ("continuousOnSeconds","onOffPersistenceVerified","normalAppStopStartVerified",
                    "runtimeRemovalReinstallOffVerified","modelAndPreferencesRetained","noEntitlementStop","noOom"):
                main.pop(field)
            main_release={**release,"channel":"MAIN","imageRef":images("MAIN")}
            mux.validate_fresh_unlicensed(root,retain("actual-main.json",main),main_release,proof)
            main["actualChannelInferenceVerified"]=False
            with self.assertRaises(AssertionError):
                mux.validate_fresh_unlicensed(root,retain("main-missing-actual-inference.json",main),main_release,proof)
            main["actualChannelInferenceVerified"]=True
            altered=fresh_unlicensed("DEV")
            altered["testedImageRef"]=images("DEV").split("@")[0]+"@sha256:"+"3"*64
            altered["testedPackageRecipeSHA256"]=mux.sha256((json.dumps(mux.recipe.recipe_model(
                altered["testedImageRef"],SUPERVISOR,"DEV"),indent=2)+"\n").encode())
            main["sharedLifecycleEvidence"]=retain("shared-dev-digest-and-recipe-rehashed.json",altered)
            with self.assertRaises(AssertionError):
                mux.validate_fresh_unlicensed(root,retain("main-rehashed-dev-reference.json",main),main_release,proof)

    def test_known649_cold_failure_cannot_be_omitted_recast_or_hidden_by_warm_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release,proof,retain=self.delivery_fixture(root)
            dev=fresh_unlicensed("DEV");dev_release={**release,"channel":"DEV","imageRef":images("DEV")}
            mux.validate_fresh_intent_outcome(root,dev,dev_release)
            for mutate in (lambda x:x.pop("firstIntentOutcome"),
                    lambda x:x["firstIntentOutcome"].update(firstAttemptPassed=True),
                    lambda x:x["firstIntentOutcome"].update(firstColdDeadlinePassed=True),
                    lambda x:x["firstIntentOutcome"].update(firstAttemptElapsedSeconds=100.0),
                    lambda x:x["firstIntentOutcome"].update(sameModelPid=90),
                    lambda x:x["firstIntentOutcome"].update(automaticWarmRetries=1)):
                changed=copy.deepcopy(dev);mutate(changed)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):
                    mux.validate_fresh_intent_outcome(root,changed,dev_release)
            changed=copy.deepcopy(dev)
            guest=json.loads((root/changed["firstIntentOutcome"]["firstGuestEvidence"]["path"]).read_text())
            guest["intentResult"].update(actualInference=True,contractValid=True,elapsedSeconds=100.0)
            changed["firstIntentOutcome"]["firstGuestEvidence"]=retain("rehashed-fake-cold-pass.json",guest)
            with self.assertRaises(AssertionError):
                mux.validate_fresh_intent_outcome(root,changed,dev_release)
            main=fresh_unlicensed("MAIN");main["firstIntentOutcome"]["firstMissionIntentColdClaimed"]=True
            with self.assertRaises(AssertionError):
                mux.validate_fresh_intent_outcome(root,main,{**release,"channel":"MAIN","imageRef":images("MAIN")})
            for mutate in (lambda x:x.update(targetVmid=643),
                    lambda x:x["actualOperatorOrMonitorResult"].update(targetVmid=643),
                    lambda x:x["actualOperatorOrMonitorResult"].update(channel="DEV"),
                    lambda x:x["actualOperatorOrMonitorResult"].update(kind="prototype"),
                    lambda x:x["actualOperatorOrMonitorResult"]["providerTest"]["testResult"].update(modelSha256="0"*64),
                    lambda x:x["actualOperatorOrMonitorResult"]["providerTest"]["testResult"].update(decision="hold"),
                    lambda x:x["actualOperatorOrMonitorResult"]["localAiAfter"]["runtime"].update(binarySha256="0"*64)):
                changed=fresh_unlicensed("MAIN")
                provider=json.loads((root/changed["firstIntentOutcome"]["priorProviderComparison"]["path"]).read_text())
                mutate(provider)
                changed["firstIntentOutcome"]["priorProviderComparison"]=retain("changed-main-prior-provider.json",provider)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):
                    mux.validate_fresh_intent_outcome(root,changed,{**release,"channel":"MAIN","imageRef":images("MAIN")})

    def test_saved_on_restart_safe_off_and_explicit_start_cannot_be_automatic_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release,proof,retain=self.delivery_fixture(root)
            for channel in ("DEV","MAIN"):
                evidence=fresh_unlicensed(channel)
                bound={**release,"channel":channel,"imageRef":images(channel)}
                mux.validate_saved_preferences_restart_policy(root,evidence,bound)
                changed=copy.deepcopy(evidence);changed["automaticModelRestoreVerified"]=True
                with self.assertRaises(AssertionError):
                    mux.validate_saved_preferences_restart_policy(root,changed,bound)
                for mutate in (lambda x:x.update(controlRequestsSent=1),
                        lambda x:x["status"]["installation"].update(running=False),
                        lambda x:x["status"]["runtime"].update(running=True),
                        lambda x:x["status"]["preferences"].update(desiredEnabled=False),
                        lambda x:x["status"]["preferences"].update(restoreAuthority="self"),
                        lambda x:x["retainedModelPhysicalHash"].update(sha256="0"*64)):
                    changed=copy.deepcopy(evidence)
                    reference=changed["restartPolicyEvidence"]["safeOffEvidence"]
                    safe=json.loads((root/reference["path"]).read_text())
                    mutate(safe["afterSavedOnRestartSafeOff"] if channel=="DEV" else safe["afterNormalUpdateLocalAI"])
                    changed["restartPolicyEvidence"]["safeOffEvidence"]=retain("changed-safe-off.json",safe)
                    with self.subTest(channel=channel,mutation=mutate),self.assertRaises(AssertionError):
                        mux.validate_saved_preferences_restart_policy(root,changed,bound)
                changed=copy.deepcopy(evidence)
                reference=changed["restartPolicyEvidence"]["explicitOwnerStartReadiness"]
                ready=json.loads((root/reference["path"]).read_text());ready["status"]["runtime"]["healthy"]=False
                changed["restartPolicyEvidence"]["explicitOwnerStartReadiness"]=retain("accepted-enable-not-healthy.json",ready)
                with self.assertRaises(AssertionError):
                    mux.validate_saved_preferences_restart_policy(root,changed,bound)

    def test_arm_normal_package_cannot_reuse_prototype_or_rehashed_wrong_image_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);release,proof,retain=self.delivery_fixture(root)
            arm=mux.referenced_proof(root,proof["armNativePackageQualification"])
            mux.validate_arm_package(arm,release,proof)
            for mutate in (lambda x:x.update(imageRef=images().split("@")[0]+"@sha256:"+"3"*64),
                    lambda x:x.update(localAIImageRef=SUPERVISOR.split("@")[0]+"@sha256:"+"3"*64),
                    lambda x:x["applicationPlatform"].update(configDigest="sha256:"+"0"*64),
                    lambda x:x["companionPlatform"].update(manifestDigest="sha256:"+"0"*64),
                    lambda x:x.update(serviceSHA256="0"*64),lambda x:x.update(supervisorSHA256="0"*64),
                    lambda x:x.update(configSHA256="0"*64),lambda x:x.update(companionSourceRevision="0"*40),
                    lambda x:x.update(packageRecipeSHA256="0"*64),lambda x:x.update(runtimeMemoryLimitBytes=8*1024**3)):
                changed=copy.deepcopy(arm);mutate(changed)
                reference=retain("wrong-arm-identity-rehashed.json",changed)
                with self.subTest(mutation=mutate),self.assertRaises(AssertionError):
                    mux.validate_arm_package(mux.referenced_proof(root,reference),release,proof)

    def test_application_and_each_companion_have_distinct_independently_reviewed_source_bindings(self):
        release = {**mux.APPLICATION_SOURCE, **PACKAGE_FIELDS, "localAIPlatforms": {arch: {
            "companionSourceRevision": row["sourceRevision"], "companionSourceTree": row["sourceTree"]}
            for arch, row in SYNTHETIC_COMPANION_SOURCES.items()}}
        with patch.dict(mux.COMPANION_SOURCE_PINS, {"amd64": None, "arm64": None}):
            with self.assertRaisesRegex(AssertionError, "independently reviewed"):
                mux.validate_component_sources(release)
        with patch.dict(mux.COMPANION_SOURCE_PINS, SYNTHETIC_COMPANION_SOURCES), \
             patch.object(mux, "PACKAGE_PRODUCER_SOURCE", SYNTHETIC_PACKAGE_SOURCE), \
             patch.object(mux, "PACKAGE_PRODUCER_INPUTS", SYNTHETIC_PACKAGE_INPUTS):
            mux.validate_component_sources(release)
            for mutate in (lambda row: row.update(sourceRevision="c" * 40),
                    lambda row: row["localAIPlatforms"]["amd64"].update(companionSourceRevision=mux.APPLICATION_SOURCE["sourceRevision"]),
                    lambda row: row["localAIPlatforms"]["arm64"].pop("companionSourceTree")):
                changed = copy.deepcopy(release); mutate(changed)
                with self.subTest(mutation=mutate), self.assertRaises(AssertionError):
                    mux.validate_component_sources(changed)

    def test_package_producer_source_and_input_bytes_cannot_collapse_into_application_or_companion(self):
        release = {**mux.APPLICATION_SOURCE, **copy.deepcopy(PACKAGE_FIELDS), "localAIPlatforms": {arch: {
            "companionSourceRevision": row["sourceRevision"], "companionSourceTree": row["sourceTree"]}
            for arch, row in SYNTHETIC_COMPANION_SOURCES.items()}}
        with patch.dict(mux.COMPANION_SOURCE_PINS, SYNTHETIC_COMPANION_SOURCES), \
             patch.object(mux, "PACKAGE_PRODUCER_SOURCE", SYNTHETIC_PACKAGE_SOURCE), \
             patch.object(mux, "PACKAGE_PRODUCER_INPUTS", SYNTHETIC_PACKAGE_INPUTS):
            mux.validate_component_sources(release, copy.deepcopy(release))
            for mutate in (lambda row: row.pop("packageProducerSourceTree"),
                    lambda row: row.update(packageProducerSourceRevision=mux.APPLICATION_SOURCE["sourceRevision"]),
                    lambda row: row.update(packageProducerSourceRevision=SYNTHETIC_COMPANION_SOURCES["amd64"]["sourceRevision"]),
                    lambda row: row["packageProducerInputs"].update({"packaging/umbrel-local-ai-release/pre-start": "0" * 64}),
                    lambda row: row["packageProducerInputs"].update({"extra.py": "0" * 64})):
                changed = copy.deepcopy(release); mutate(changed)
                with self.subTest(mutation=mutate), self.assertRaises(AssertionError):
                    mux.validate_component_sources(changed)
                with self.subTest(deliveryMutation=mutate), self.assertRaises(AssertionError):
                    mux.validate_component_sources(release, changed)

    def test_companion_only_accepts_the_exact_supervisor_tag_and_digest(self):
        mux.recipe.image_refs(images(), SUPERVISOR, CHANNEL)
        for replacement in ("0.9.82-umbrel", "local-ai-0.1.9", "local-ai-0.1.9-umbrel-dev", "local-ai-0.1.8-umbrel"):
            with self.subTest(tag=replacement), self.assertRaises(ValueError):
                mux.recipe.image_refs(images(), SUPERVISOR.replace("local-ai-0.1.9-umbrel", replacement), CHANNEL)
        for wrong in (SUPERVISOR.split("@")[0], SUPERVISOR.replace("5tratmux-app", "5tratmux-local-ai"),
                SUPERVISOR.replace("5tratmux-app:local-ai-0.1.9-umbrel", "5tratmux-local-ai-umbrel:0.1.9")):
            with self.subTest(image=wrong), self.assertRaises(ValueError):
                mux.recipe.image_refs(images(), wrong, CHANNEL)

    def test_current_qualified_history_is_retained_exactly(self):
        previous = mux.historical(ROOT, CHANNEL)
        self.assertEqual(previous["version"], "0.9.80-dev" if CHANNEL == "DEV" else "0.9.80")
        if mux.ADMISSION_LOCKS[CHANNEL] is None:
            self.assertIsNone(mux.DELIVERY_LOCKS[CHANNEL])
        else:
            mux.record(ROOT)

    def test_editable_new_receipt_cannot_self_authorize(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(mux.ADMISSION_LOCKS, {CHANNEL: None}):
            root = Path(directory)
            (root / mux.RECORD_NAME).write_text(json.dumps({"channel": CHANNEL, "status": "qualified"}))
            with self.assertRaisesRegex(AssertionError, "not been independently finalized"):
                mux.record(root)

    def test_historical_record_or_delivery_mutation_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = json.loads((ROOT / mux.PREDECESSOR_NAME).read_text())
            for name in (mux.PREDECESSOR_NAME, old["publication"]["path"], old["predecessor"]["record"],
                         old["predecessor"]["delivery"]["path"]):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            mux.historical(root, CHANNEL)
            for name in (mux.PREDECESSOR_NAME, old["publication"]["path"]):
                target = root / name
                original = target.read_bytes()
                target.write_bytes(original + b"\n")
                with self.subTest(name=name), self.assertRaises(AssertionError):
                    mux.historical(root, CHANNEL)
                target.write_bytes(original)

    def test_real_corpus_contract_admits_only_full_actual_inference_and_correct_identity(self):
        evidence = corpus()
        mux.validate_corpus(evidence, mux.RUNTIME_SHA256["arm64"], "arm64", mux.INTENT_SHA256)
        mutations = [lambda row: row.update(automaticPasses=24),
            lambda row: row.update(modelSha256="0" * 64),
            lambda row: row.update(runtimeBinarySha256="0" * 64),
            lambda row: row.update(runtimeCpuProfile="amd64-v2"),
            lambda row: row.update(intentProfileSha256="0" * 64),
            lambda row: row.update(corpusSha256="0" * 64),
            lambda row: row.update(ownedRuntimeStopped=False),
            lambda row: row.update(productionEligible=True),
            lambda row: row["cases"].pop(),
            lambda row: row["cases"][0].update(id=row["cases"][1]["id"]),
            lambda row: row["cases"][0].update(seconds=float("nan")),
            lambda row: row["cases"][0]["result"].update(actualInference=False)]
        for mutate in mutations:
            changed = copy.deepcopy(evidence)
            mutate(changed)
            with self.subTest(mutation=mutate), self.assertRaises(AssertionError):
                mux.validate_corpus(changed, mux.RUNTIME_SHA256["arm64"], "arm64", mux.INTENT_SHA256)

    def test_performance_retains_cold_timeout_without_claiming_all_architectures_passed(self):
        evidence = corpus("amd64-v2")
        evidence["automaticPasses"] = 24
        evidence["cases"][0].update(verdict="fail", seconds=600.006,
            result={"actualInference":False,"contractValid":False,
                "error":{"code":"runtime_timeout","reason":"intent_deadline"}})
        mux.validate_run(evidence, SYNTHETIC_SELECTED_BASELINE, "amd64-v2", mux.INTENT_SHA256)
        summary = mux.performance_summary(evidence, "amd64-v2")
        self.assertEqual(summary["passes"], 24)
        self.assertEqual(summary["failures"], 1)
        self.assertEqual(summary["coldStart"]["seconds"], 600.006)
        self.assertFalse(summary["allCasesPassed"])
        self.assertFalse(summary["allCasesPassedWithinServiceBudget"])
        with self.assertRaisesRegex(AssertionError, "all 25"):
            mux.validate_corpus(evidence, SYNTHETIC_SELECTED_BASELINE, "amd64-v2", mux.INTENT_SHA256)

    def test_truthful_recomputed_failure_or_excess_deadline_summary_cannot_admit_final_performance(self):
        with tempfile.TemporaryDirectory() as directory,patch.dict(mux.RUNTIME_SHA256,{"amd64-v2":mux.OPENBLAS_BINARY}):
            root=Path(directory);(root/"release-records").mkdir()
            def check(profile,evidence):
                raw=json.dumps(evidence).encode();name="release-records/recomputed.json";(root/name).write_bytes(raw)
                return mux.validate_performance(root,{"path":name,"sha256":mux.sha256(raw)},
                    mux.performance_summary(evidence,profile),profile)
            for profile in ("amd64-v2","arm64","native-amd64-avx2"):
                good=corpus(profile);check(profile,good)
                failed=copy.deepcopy(good);failed["automaticPasses"]-=1
                failed["cases"][1].update(verdict="fail",result={"actualInference":False,"contractValid":False})
                with self.subTest(profile=profile,mutation="truthful additional failure"),self.assertRaises(AssertionError):
                    check(profile,failed)
                excessive=copy.deepcopy(good);excessive["cases"][1]["seconds"]=mux.SERVICE_REQUEST_BUDGET_SECONDS[profile]+.001
                with self.subTest(profile=profile,mutation="truthful over-budget pass"),self.assertRaises(AssertionError):
                    check(profile,excessive)

    def test_interrupted_rejected_run_cannot_be_used_as_final_performance_acceptance(self):
        evidence = corpus("amd64-v2")
        evidence.update(completeCorpus=False, interruptedBy="SIGTERM")
        evidence["cases"] = evidence["cases"][:2]
        evidence["automaticPasses"] = 1
        with self.assertRaisesRegex(AssertionError, "Complete actual corpus"):
            mux.validate_run(evidence, SYNTHETIC_SELECTED_BASELINE, "amd64-v2", mux.INTENT_SHA256)

    def test_performance_preserves_technical_failure_and_review_verdicts_without_calling_them_passes(self):
        evidence = corpus()
        evidence["cases"][0].pop("result")
        evidence["cases"][0].update(verdict="technical_failure", error="ExampleError: synthetic failure")
        evidence["cases"][1]["verdict"] = "requires_review"
        evidence["automaticPasses"] = 23
        mux.validate_run(evidence, mux.RUNTIME_SHA256["arm64"], "arm64", mux.INTENT_SHA256)
        summary = mux.performance_summary(evidence, "arm64")
        self.assertEqual(summary["passes"], 23)
        self.assertEqual(summary["failures"], 2)
        self.assertEqual(summary["coldStart"]["technicalError"], "ExampleError: synthetic failure")
        self.assertFalse(summary["allCasesPassed"])
        with self.assertRaises(AssertionError):
            mux.validate_corpus(evidence, mux.RUNTIME_SHA256["arm64"], "arm64", mux.INTENT_SHA256)

    def test_later_performance_may_truthfully_record_previously_granted_model_eligibility(self):
        evidence = corpus()
        evidence["productionEligible"] = True
        mux.validate_run(evidence, mux.RUNTIME_SHA256["arm64"], "arm64", mux.INTENT_SHA256)
        self.assertTrue(mux.performance_summary(evidence, "arm64")["allCasesPassed"])
        with self.assertRaisesRegex(AssertionError, "predates"):
            mux.validate_corpus(evidence, mux.RUNTIME_SHA256["arm64"], "arm64", mux.INTENT_SHA256)

    def test_semantic_evidence_is_independently_locked_not_selected_by_a_rehashed_delivery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "release-records").mkdir()
            raw = json.dumps(corpus()).encode()
            (root / "release-records/edited-semantic.json").write_bytes(raw)
            reference = {"path": "release-records/edited-semantic.json", "sha256": mux.sha256(raw)}
            with self.assertRaisesRegex(AssertionError, "exact independently reviewed"):
                mux.validate_semantic_qualification(root, reference)

    def package_fixture(self, root):
        app = root / mux.APP
        (app / "hooks").mkdir(parents=True)
        (app / "data").mkdir()
        (app / "data/.gitkeep").write_text("\n")
        (app / "docker-compose.yml").write_text(json.dumps(mux.recipe.recipe_model(images(), SUPERVISOR, CHANNEL)))
        (app / "umbrel-app.yml").write_text(json.dumps(mux.recipe.manifest_model(CHANNEL)))
        shutil.copyfile(ROOT / mux.APP / "icon.png", app / "icon.png")
        shutil.copyfile(ROOT / "scripts/mux-local-ai/pre-start", app / "hooks/pre-start")
        files = {}
        for name in mux.recipe.FILES:
            path = app / name
            mode = 0o755 if name == "hooks/pre-start" else 0o644
            path.chmod(mode)
            files[mux.APP + "/" + name] = {"sha256": mux.sha256(path.read_bytes()), "mode": oct(mode)}
        return {"channel": CHANNEL, "imageRef": images(), "localAIImageRef": SUPERVISOR, "packageFiles": files}

    def test_complete_compose_and_unchanged_artwork_hook_are_required_even_after_receipt_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release = self.package_fixture(root)
            mux.validate_package(root, release)
            hook = root / mux.APP / "hooks/pre-start"
            hook.write_bytes(b"#!/bin/sh\nexit 0\n")
            release["packageFiles"][mux.APP + "/hooks/pre-start"]["sha256"] = mux.sha256(hook.read_bytes())
            with self.assertRaisesRegex(AssertionError, "hook/artwork"):
                mux.validate_package(root, release)

    def test_no_native_socket_or_extra_untested_service_can_be_added(self):
        original = mux.recipe.recipe_model(images(), SUPERVISOR, CHANNEL)
        for mutate in (lambda row: row["services"]["local_ai"].update(ports=["18080:18080"]),
            lambda row: row["services"]["local_ai"].update(volumes=["/var/run/docker.sock:/var/run/docker.sock"]),
            lambda row: row["services"].update(extra={"image": "busybox"}),
            lambda row: row["services"]["server"].update(volumes=["${APP_DATA_DIR}/data:/data"])):
            changed = copy.deepcopy(original)
            mutate(changed)
            with self.assertRaises(ValueError):
                mux.recipe.validate_recipe(changed, images(), SUPERVISOR, CHANNEL)

    def test_current_gate_dispatches_future_record_to_independently_locked_successor(self):
        spec = importlib.util.spec_from_file_location("historical_mux_gate", ROOT / "scripts/mux_umbrel_release.py")
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / mux.RECORD_NAME).write_text("{}\n")
            with patch.object(mux, "validate", return_value={"syntheticUnitFixture": True}) as successor:
                self.assertTrue(old.validate(root)["syntheticUnitFixture"])
                successor.assert_called_once_with(root)
            with self.assertRaises(AssertionError):
                old.validate(root, check_baseline=True)

    def delivery_fixture(self, root):
        (root / "release-records").mkdir()
        def retain(name, row):
            raw = (json.dumps(row, sort_keys=True) + "\n").encode()
            path = "release-records/" + name
            (root / path).write_bytes(raw)
            return {"path": path, "sha256": mux.sha256(raw)}
        for channel in ("DEV", "MAIN"):
            outcome, documents = fresh_intent_fixture(channel)
            for name, row in documents.items():
                retain(name, row)
            if channel == "DEV":
                self.enterContext(patch.dict(mux.FRESH_DEV_FIRST_INTENT_LOCKS,
                    {name:outcome[name]["sha256"] for name in mux.FRESH_DEV_FIRST_INTENT_LOCKS}))
            policy, documents = restart_policy_fixture(channel)
            for name, row in documents.items():
                retain(name, row)
            if channel == "DEV":
                self.enterContext(patch.object(mux,"FRESH_DEV_RESTART_EXPECTATION_FAILURE",
                    policy["originalRestartExpectationFailure"]["sha256"]))
        release = {"channel": CHANNEL, **mux.APPLICATION_SOURCE, **copy.deepcopy(PACKAGE_FIELDS),
            "imageRef": images(), "localAIImageRef": SUPERVISOR, "platforms": {}, "localAIPlatforms": {},
            "packageFiles": {mux.APP+"/docker-compose.yml": {"sha256": channel_scope()["testedPackageRecipeSHA256"], "mode":"0o644"}}}
        proof = {**release, "schemaVersion": 1, "result": "PASS", "anonymousMuxAndCompanionIndicesVerified": True,
            "platforms": {}, "localAIPlatforms": {}, "umbrelQualification": {}}
        proof["semanticQualification"] = retain("synthetic-reviewed-semantic.json", corpus())
        proof["rejectedVariantHistory"] = {}
        for name in mux.REJECTED_EVIDENCE_SHA256:
            rejected = corpus("amd64-v2" if name == "baseline-4b-600s" else "arm64")
            if name == "baseline-4b-600s":
                rejected["cases"][0].update(verdict="fail",seconds=600.006,
                    result={"actualInference":False,"contractValid":False,
                        "error":{"code":"runtime_timeout","reason":"intent_deadline"}})
            rejected.update(completeCorpus=False, interruptedBy="SIGTERM", runtimeBinarySha256="39ff55c3381e7d4cf5b007c78944a2e910233dcc1d32ea1c909942cb6c641b81",
                expectedRuntimeBinarySha256="39ff55c3381e7d4cf5b007c78944a2e910233dcc1d32ea1c909942cb6c641b81")
            rejected["cases"] = rejected["cases"][:2 if name == "baseline-4b-600s" else 6]
            rejected["automaticPasses"] = 1 if name == "baseline-4b-600s" else 3
            if name == "baseline-0.8b":
                rejected.update(modelId="qwen3.5-0.8b", modelSha256="bd258782e35f7f458f8aced1adc053e6e92e89bc735ba3be89d38a06121dc517")
                for row in rejected["cases"][3:]:
                    row["verdict"] = "fail"
            proof["rejectedVariantHistory"][name] = retain(name + "-synthetic-rejected.json", rejected)
        native = corpus("native-amd64-avx2")
        proof["nativeRuntimePerformance"] = {"evidence": retain("synthetic-native-performance.json", native),
            "summary": mux.performance_summary(native, "native-amd64-avx2")}
        for product in ("platforms", "localAIPlatforms"):
            for architecture in ("amd64", "arm64"):
                identity = {"manifestDigest": "sha256:" + "5" * 64, "configDigest": "sha256:" + "6" * 64}
                if product == "localAIPlatforms":
                    component = SYNTHETIC_COMPANION_SOURCES[architecture]
                    identity.update(companionSourceRevision=component["sourceRevision"], companionSourceTree=component["sourceTree"])
                release[product][architecture] = identity
                row = {**identity, "allDistributedLayersAudited": True, "allLayerDigestsVerified": True,
                    "noApplicationPythonSources": True, "noSourceMaps": True,
                    "noApplicationPrivateKeyMaterial": True, "nativeStartupVerified": True}
                if product == "platforms":
                    row.update(protectedExecutableSHA256="7" * 64, operatorAuthenticationVerified=True,
                        httpHealthVersion=mux.recipe.VERSIONS[CHANNEL], freshNativeBaseRootfsVerified=True)
                else:
                    profile = "amd64-v2" if architecture == "amd64" else "arm64"
                    performance = corpus(profile)
                    staged, config = runtime_inputs(profile, performance["runtimeBinarySha256"])
                    configuration = retain(architecture + "-synthetic-config.json", config)
                    row.update(cpuProfile=profile,
                        supervisorSHA256="8" * 64, serviceSHA256="9" * 64, llamaSHA256=performance["runtimeBinarySha256"],
                        intentProfileSHA256=mux.INTENT_SHA256, compiledProfileVerified=True,
                        compiledCheckVerified=True, cpuBuildProofVerified=True,
                        performanceEvidence=retain(architecture + "-synthetic-performance.json", performance),
                        performanceSummary=mux.performance_summary(performance, profile),
                        cpuBuildProof=retain(architecture + "-synthetic-build.json", cpu_build(profile, performance["runtimeBinarySha256"])),
                        runtimeConfiguration=configuration, configSHA256=configuration["sha256"],
                        serviceBuildInputs=retain(architecture + "-synthetic-staging.json", staged),
                        runtimeConfigurationVerified=True, runtimeNoticesVerified=True, runtimeReadOnlyRootfsVerified=True,
                        runtimeNoticesSHA256=mux.OPENBLAS_NOTICES if profile == "amd64-v2" else mux.LLAMA_LICENCE)
                proof[product][architecture] = row
        proof["compiledAmdOperation"] = compiled_operation_fixture(retain,proof["localAIPlatforms"]["amd64"])
        fields = {name: True for name in ("nativeUpdateStopStartPersistenceVerified", "operatorAuthenticationVerified",
            "localAiOnOffRemovalVerified", "socketPeerIdentityVerified", "existingMuxStatePreserved",
            "storageRootContractVerified", "noHostControllerOrDockerSocket")}
        for version in ("1.7.4", "2.0.0"):
            target = 642 if version == "1.7.4" else 643
            proof["umbrelQualification"][version] = retain(version + "-synthetic-smoke.json",
                {**channel_scope(), "syntheticUnitFixture": True, "result": "PASS", "architecture": "amd64",
                 "kind": "normal-umbrel-update-with-memory-guard", "osVersion": version,
                 "targetVmid": target, "configuredMemoryMiB": 8192, **fields,
                 **existing_lab_authority_adaptation(root,target),
                 "runtimeCpuLimit": 2, "runtimeMemoryLimitBytes": 6 * 1024**3, "runtimeMemorySwapLimitBytes": 6 * 1024**3,
                 "localAiOffCleanupVerified": True, "existingPaidIdentityPreserved": True, "hardwareUnchanged": True,
                 "memoryGuardRefusedEnable": True, "runtimeRunningAfterRefusal": False, "onOrInferenceClaimed": False,
                 "memoryAdmission": {"hostTotalBytes": 8 * 1024**3, "hostAvailableBytes": 5 * 1024**3,
                     "hostReserveBytes": int(8 * 1024**3 * 0.15), "modelBudgetBytes": 5 * 1024**3,
                     "requiredHostBytes": 5 * 1024**3 + int(8 * 1024**3 * 0.15), "allowed": False}})
        proof["freshUnlicensedUmbrelQualification"] = retain("fresh649-synthetic-smoke.json", fresh_unlicensed())
        companion = proof["localAIPlatforms"]["arm64"]
        arm = {"syntheticUnitFixture": True, "result": "PASS", "architecture": "arm64",
            "kind": "native-container-package-qualification", **fields, **mux.APPLICATION_SOURCE, **copy.deepcopy(PACKAGE_FIELDS),
            "testedChannel": CHANNEL, "testedVersion": mux.recipe.VERSIONS[CHANNEL],
            "imageRef": images(), "localAIImageRef": SUPERVISOR,
            "applicationPlatform": release["platforms"]["arm64"], "companionPlatform": release["localAIPlatforms"]["arm64"],
            "protectedExecutableSHA256": proof["platforms"]["arm64"]["protectedExecutableSHA256"],
            "packageRecipeSHA256": channel_scope()["testedPackageRecipeSHA256"],
            "runtimeCpuLimit": 2, "runtimeMemoryLimitBytes": 6*1024**3, "runtimeMemorySwapLimitBytes": 6*1024**3,
            "runtimeUser": "1000:1000", "runtimeReadOnlyRootfsVerified": True, "sidecarPublishedPorts": [], "requestTimeoutSeconds":180}
        arm.update({field: companion[field] for field in ("supervisorSHA256", "serviceSHA256", "llamaSHA256", "configSHA256", "intentProfileSHA256",
            "companionSourceRevision", "companionSourceTree")})
        proof["armNativePackageQualification"] = retain("arm-synthetic-smoke.json", arm)
        return release, proof, retain

    def test_complete_synthetic_delivery_is_bound_and_missing_arm_or_compiled_proof_is_denied_even_after_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            release, proof, retain = self.delivery_fixture(root)
            name = "mux-umbrel-" + mux.recipe.VERSIONS[CHANNEL] + "-delivery.json"
            def check(row):
                release["publication"] = retain(name, row)
                with patch.dict(mux.DELIVERY_LOCKS, {CHANNEL: release["publication"]["sha256"]}), \
                     patch.dict(mux.RUNTIME_SHA256, {"amd64-v2": SYNTHETIC_SELECTED_BASELINE}), \
                     patch.dict(mux.COMPANION_SOURCE_PINS, SYNTHETIC_COMPANION_SOURCES), \
                     patch.object(mux, "PACKAGE_PRODUCER_SOURCE", SYNTHETIC_PACKAGE_SOURCE), \
                     patch.object(mux, "PACKAGE_PRODUCER_INPUTS", SYNTHETIC_PACKAGE_INPUTS), \
                     patch.dict(mux.COMPILED_AMD_OPERATION_LOCKS,{key:ref["sha256"]for key,ref in proof["compiledAmdOperation"].items()}), \
                     patch.dict(mux.REJECTED_EVIDENCE_SHA256, {key: ref["sha256"] for key, ref in proof["rejectedVariantHistory"].items()}), \
                     patch.object(mux, "SEMANTIC_EVIDENCE_SHA256", proof["semanticQualification"]["sha256"]):
                    return mux.validate_delivery(root, release)
            check(proof)
            mutations = [lambda row: row["localAIPlatforms"].pop("arm64"),
                lambda row: row["localAIPlatforms"]["arm64"].update(cpuProfile="amd64-v2"),
                lambda row: row["localAIPlatforms"]["amd64"].update(compiledProfileVerified=False),
                lambda row: row["platforms"]["arm64"].update(noApplicationPythonSources=False),
                lambda row: row["platforms"]["amd64"].update(freshNativeBaseRootfsVerified=False),
                lambda row: row["localAIPlatforms"]["amd64"]["performanceSummary"].update(allCasesPassed=False),
                lambda row: row["nativeRuntimePerformance"]["summary"]["coldStart"].update(verdict="pass"),
                lambda row: row.pop("compiledAmdOperation"),
                lambda row: row["rejectedVariantHistory"].pop("baseline-4b-600s"),
                lambda row: row["localAIPlatforms"]["arm64"].update(intentProfileSHA256="0" * 64),
                lambda row: row["localAIPlatforms"]["amd64"].update(companionSourceRevision=mux.APPLICATION_SOURCE["sourceRevision"]),
                lambda row: row["localAIPlatforms"]["arm64"].update(companionSourceTree="0" * 40),
                lambda row: row["localAIPlatforms"]["amd64"].pop("companionSourceRevision"),
                lambda row: row.update(packageProducerSourceRevision=mux.APPLICATION_SOURCE["sourceRevision"]),
                lambda row: row["packageProducerInputs"].update({"packaging/umbrel-local-ai-release/pre-start": "0" * 64}),
                lambda row: row.update(sourceRevision="0" * 40)]
            for mutate in mutations:
                changed = copy.deepcopy(proof)
                mutate(changed)
                with self.subTest(mutation=mutate), self.assertRaises(AssertionError):
                    check(changed)


if __name__ == "__main__":
    unittest.main()
