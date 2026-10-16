"""Negative admission checks use synthetic local fixtures, never release proof."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("health_release_tests", ROOT / "scripts/health_release.py")
health = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(health)
CHANNEL = health.channel()


def synthetic_release():
    release = {"schemaVersion": 1, "status": "qualified", "channel": CHANNEL,
               "baselineCommit": health.BASELINES[CHANNEL], "apps": {}}
    for app_id in health.APPS:
        short = "axebch2-app" if app_id == health.APPS[1] else "axebch-app-umbrel-dev"
        release["apps"][app_id] = {"version": health.version(app_id, CHANNEL),
            "sourceRevision": health.SOURCES[app_id][0], "sourceTree": health.SOURCES[app_id][1],
            "imageRef": f"ghcr.io/willitmod/{short}:synthetic-unit-test@sha256:" + "1" * 64}
        row = release["apps"][app_id]
        row["retentionRequirement"] = {"appId": "axebch2" if app_id == health.APPS[1] else "axebch",
            "appService": "app", "appSourceRevision": row["sourceRevision"], "appImage": row["imageRef"],
            "platforms": {arch: {"appConfigDigest": "sha256:" + "5"*64, "appManifestDigest": "sha256:" + "4"*64}
                          for arch in ("amd64", "arm64")}}
    return release


class HealthReleaseTests(unittest.TestCase):
    def setUp(self):
        self.release = synthetic_release()

    def current(self, app_id):
        return health.model(app_id, health.predecessor(ROOT, app_id), self.release["apps"][app_id], CHANNEL)

    def reject_runtime(self, cases):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                for service, key, value in cases(app_id):
                    current = self.current(app_id)
                    current["services"][service][key] = value
                    with self.subTest(app=app_id, service=service, key=key), self.assertRaises(AssertionError):
                        health.previous_model(app_id, current)

    def test_pending_publication_is_not_admitted(self):
        if health.LOCKS[CHANNEL] is None:
            with self.assertRaisesRegex(AssertionError, "awaits actual"):
                health.record()
        else:
            health.validate()

    def test_exact_application_delta_restores_whole_predecessor(self):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                before = health.predecessor(ROOT, app_id)
                self.assertEqual(health.previous_model(app_id, self.current(app_id)), before)
                self.assertEqual(health.previous_model(app_id, before), before)

    def test_node_image_environment_and_volume_changes_are_refused(self):
        self.reject_runtime(lambda app: [("bch2" if app == health.APPS[1] else "bchn", key, value)
            for key, value in (("image", "changed:latest"), ("volumes", []), ("environment", {}), ("stop_grace_period", "1s"))])

    def test_pool_image_command_payout_and_volume_changes_are_refused(self):
        self.reject_runtime(lambda app: [("ckpool", key, value) for key, value in
            (("image", "changed:latest"), ("command", []), ("volumes", []), ("environment", {"PAYOUT_ADDRESS": "changed"}))])

    def test_all_published_ports_remain_exact(self):
        self.reject_runtime(lambda app: [(service, "ports", ["9999:3000"])
            for service in ("app", "ckpool", "bch2" if app == health.APPS[1] else "bchn")])

    def test_authentication_mounts_identity_and_lifecycle_are_not_relaxed(self):
        self.reject_runtime(lambda app: [("app", key, value) for key, value in
            (("user", "0:0"), ("volumes", []), ("group_add", ["0"]), ("privileged", True),
             ("networks", {}), ("depends_on", []), ("stop_signal", "SIGTERM"), ("restart", "no"))])

    def test_init_and_proxy_configuration_cannot_change(self):
        self.reject_runtime(lambda app: [("init_permissions" if app == health.APPS[1] else "init", "command", []),
                                        ("app_proxy", "environment", {"APP_HOST": "elsewhere", "APP_PORT": 3001})])

    def test_health_probe_cannot_reintroduce_about_slow_timeout_or_status_only_check(self):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                for field, value in (("test", ["CMD-SHELL", health.PROBE.replace("/api/health", "/api/about")]),
                                     ("test", ["CMD-SHELL", health.PROBE.replace("timeout=3", "timeout=12")]),
                                     ("test", ["CMD-SHELL", "exit 0"]), ("disable", True),
                                     ("interval", "1s"), ("timeout", "30s"), ("retries", 1), ("start_period", "0s")):
                    current = self.current(app_id)
                    current["services"]["app"]["healthcheck"][field] = value
                    with self.subTest(app=app_id, field=field), self.assertRaises(AssertionError):
                        health.previous_model(app_id, current)

    def test_unreviewed_application_image_revision_version_or_channel_is_refused(self):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                for field, value in (("image", "moving:latest"), ("APP_REVISION", "4" * 40),
                                     ("APP_VERSION", "99.0.0"), ("APP_CHANNEL", "UNREVIEWED")):
                    current = self.current(app_id)
                    target = current["services"]["app"]
                    (target if field == "image" else target["environment"])[field] = value
                    with self.subTest(app=app_id, field=field), self.assertRaises(AssertionError):
                        health.previous_model(app_id, current)

    def test_retention_gate_cannot_be_removed_downgraded_or_rebound(self):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                for case in ("removed", "v1", "skip-services", "source", "image", "app", "service", "config", "manifest", "missing-arch", "extra-field"):
                    current = self.current(app_id)
                    gate = current[health.RETENTION_EXTENSION]
                    if case == "removed": del current[health.RETENTION_EXTENSION]
                    elif case == "v1": gate["version"] = 1
                    elif case == "skip-services": gate["services"] = {"bch2": {"skipUpdateStop": True}}
                    elif case in ("source", "image", "app", "service"):
                        key = {"source": "appSourceRevision", "image": "appImage", "app": "appId", "service": "appService"}[case]
                        gate["requiresRetention"][key] = "unreviewed"
                    elif case in ("config", "manifest"):
                        key = "appConfigDigest" if case == "config" else "appManifestDigest"
                        gate["requiresRetention"]["platforms"]["amd64"][key] = "sha256:" + "0"*64
                    elif case == "missing-arch": del gate["requiresRetention"]["platforms"]["arm64"]
                    else: gate["requiresRetention"]["minOS"] = "0.8.36"
                    with self.subTest(app=app_id, case=case), self.assertRaises(AssertionError):
                        health.previous_model(app_id, current)

    def test_retention_requirement_requires_exact_reviewed_shape_and_both_published_architectures(self):
        for app_id in health.APPS:
            for case in ("extra-key", "source", "image", "wrong-repository", "missing-arch", "extra-arch", "extra-platform-key", "pending-config", "missing-manifest"):
                row = copy.deepcopy(self.release["apps"][app_id]);gate = row["retentionRequirement"]
                if case == "extra-key": gate["minOS"] = "0.8.36"
                elif case == "source": gate["appSourceRevision"] = "0"*40
                elif case == "image": gate["appImage"] = "changed:latest"
                elif case == "wrong-repository":
                    gate["appImage"] = row["imageRef"] = "ghcr.io/willitmod/another-app:test@sha256:" + "1"*64
                elif case == "missing-arch": del gate["platforms"]["arm64"]
                elif case == "extra-arch": gate["platforms"]["arm/v7"] = copy.deepcopy(gate["platforms"]["arm64"])
                elif case == "extra-platform-key": gate["platforms"]["amd64"]["skip"] = True
                elif case == "pending-config": gate["platforms"]["arm64"]["appConfigDigest"] = None
                else: del gate["platforms"]["amd64"]["appManifestDigest"]
                with self.subTest(app=app_id, case=case), self.assertRaises((AssertionError, KeyError)):
                    health.validate_retention_requirement(app_id, row)

    def test_manifest_allows_only_new_version_and_prepended_health_note(self):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                before = health.predecessor(ROOT, app_id, "umbrel-app.yml")
                current = copy.deepcopy(before)
                current.update(version=health.version(app_id, CHANNEL), releaseNotes=health.NOTE + "\n" + before["releaseNotes"])
                self.assertEqual(health.previous_manifest(app_id, current), before)
                for key, value in (("port", 9999), ("dependencies", ["unreviewed"]), ("icon", "icon.png"),
                                   ("releaseNotes", "replacement"), ("version", "0.9.2.7"), ("deterministicPassword", True)):
                    changed = copy.deepcopy(current)
                    changed[key] = value
                    with self.subTest(app=app_id, field=key), self.assertRaises(AssertionError):
                        health.previous_manifest(app_id, changed)

    def test_only_reviewed_version_successors_are_accepted(self):
        with patch.object(health, "record", return_value=self.release):
            for app_id in health.APPS:
                before = health.BEFORE_VERSIONS[app_id] + ("-dev" if CHANNEL == "DEV" else "")
                now = health.version(app_id, CHANNEL)
                self.assertEqual(health.package_version(app_id, before), now)
                self.assertEqual(health.package_version(app_id, now), now)
                with self.assertRaises(AssertionError):
                    health.package_version(app_id, "arbitrary-old-version")

    def test_unrelated_apps_are_copied_without_mutation_or_version_change(self):
        original = {"services": {"app": {"image": "unchanged"}}}
        restored = health.previous_model("other-app", original)
        self.assertEqual(restored, original)
        self.assertIsNot(restored, original)
        self.assertEqual(health.package_version("other-app", "unchanged"), "unchanged")

    def test_editable_record_cannot_authorize_an_image_or_qualification(self):
        original = json.loads((ROOT / health.RECORD_NAME).read_text())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for field, value in (("status", "qualified"), ("baselineCommit", "f" * 40)):
                changed = copy.deepcopy(original)
                changed[field] = value
                (root / health.RECORD_NAME).write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaises(AssertionError):
                    health.record(root)

    def test_permanent_checks_do_not_freeze_unrelated_future_app_updates(self):
        with patch.object(health, "record", return_value=self.release), \
             patch.object(health, "validate_package"), patch.object(health, "validate_publication"), \
             patch.object(health, "validate_baseline") as baseline:
            health.validate()
            baseline.assert_not_called()
            health.validate(check_baseline=True)
            baseline.assert_called_once_with(ROOT, CHANNEL)

    def test_real_git_admission_protects_old_apps_records_and_inventory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = {"willitmod-old/docker-compose.yml": b"services: {}\n", "FROZEN.json": b"{}\n",
                         "release-records/old.json": b"{}\n", "willitmod-dev-fumbrel/umbrel-app.yml": b"version: 0.1.3\n"}
            for app in (*health.APPS, health.MUX):
                originals[app + "/umbrel-app.yml"] = b"version: 0.0.1\n"
            for name, raw in originals.items():
                p = root / name;p.parent.mkdir(parents=True, exist_ok=True);p.write_bytes(raw)
            def git(*args):
                return subprocess.check_output(["git", *args], cwd=root, stderr=subprocess.DEVNULL)
            git("init", "--quiet");git("add", ".")
            git("-c", "user.name=Disposable Unit Test", "-c", "user.email=unit@example.invalid", "commit", "--quiet", "-m", "Synthetic predecessor")
            baseline = git("rev-parse", "HEAD").decode().strip()
            with patch.dict(health.BASELINES, {CHANNEL: baseline}):
                health.validate_baseline(root, CHANNEL)
                for name in ("willitmod-old/docker-compose.yml", "FROZEN.json", "release-records/old.json", "willitmod-dev-fumbrel/umbrel-app.yml"):
                    p=root/name;p.write_bytes(originals[name]+b"changed\n")
                    try:
                        with self.subTest(name=name), self.assertRaises(AssertionError):health.validate_baseline(root,CHANNEL)
                    finally:p.write_bytes(originals[name])
                p=root/health.APPS[0]/"new-file";p.write_text("unreviewed")
                with self.assertRaises(AssertionError):health.validate_baseline(root,CHANNEL)

    def test_synthetic_publication_requires_both_architectures_and_all_three_platforms(self):
        app_id = health.APPS[0]
        row = copy.deepcopy(self.release["apps"][app_id])
        platform = {"manifestDigest": "sha256:" + "4"*64, "configDigest": "sha256:" + "5"*64,
                    "protectedExecutableSHA256": "6"*64, "noApplicationPythonSources": True, "noSourceMaps": True,
                    "nativeStartupVerified": True, "healthIndependentOfNodeRpcVerified": True,
                    "httpHealthVersion": row["version"]}
        qualification = {"result": "PASS", "receipt": "synthetic-unit-test.json", "receiptSHA256": "7"*64,
                         "healthUnderBlockedRpcVerified": True, "clientDisconnectVerified": True,
                         "unchangedPortsVerified": True, "persistentStatePreserved": True,
                         "osVersion": health.OS_MINIMUM_VERSION, "retentionAdmissionVerified": True,
                         "oldOsRejectedBeforeMutationVerified": True, "oldOsRejectionScope": health.OLD_OS_REJECTION_SCOPE,
                         "nativeManagerObservationChannel": "MAIN", "nativeManagerObservedVersion": health.VERSIONS[app_id],
                         "sharedImageRef": row["imageRef"], "sharedConfigDigest": platform["configDigest"]}
        original = {"schemaVersion": 1, "result": "PASS", "appId": app_id,
                    **{key: row[key] for key in ("version", "sourceRevision", "sourceTree", "imageRef")},
                    "anonymousIndexAndBothPlatformsVerified": True,
                    "platforms": {arch: copy.deepcopy(platform) for arch in ("amd64", "arm64")},
                    "qualification": {system: copy.deepcopy(qualification) for system in ("umbrel1.7.4", "umbrel2.0.0", "5tratumOS")}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory);name=f"release-records/bch-{row['version']}-health-delivery.json"
            (root/name).parent.mkdir();row["publication"]={"path": name}
            receipt_path = root / "release-records/synthetic-unit-test.json"
            receipt_raw = b'{"result":"PASS","syntheticUnitFixture":true}\n'
            receipt_path.write_bytes(receipt_raw)
            for q in original["qualification"].values():q["receiptSHA256"] = health.sha256(receipt_raw)
            cases=[None, "anonymous", "missing-arch", "python-source", "map", "node-dependent", "wrong-version", "missing-os", "disconnect", "ports", "persistence", "retention-config", "retention-manifest", "old-os", "retention-absent", "old-os-mutation", "rejection-scope", "native-manager-channel", "native-manager-version", "different-shared-image", "different-shared-config", "receipt-tamper"]
            for case in cases:
                proof=copy.deepcopy(original)
                receipt_path.write_bytes(receipt_raw)
                if case=="anonymous":proof['anonymousIndexAndBothPlatformsVerified']=False
                elif case=="missing-arch":del proof['platforms']['arm64']
                elif case in ("python-source","map","node-dependent","wrong-version"):
                    key={"python-source":"noApplicationPythonSources","map":"noSourceMaps","node-dependent":"healthIndependentOfNodeRpcVerified","wrong-version":"httpHealthVersion"}[case]
                    proof['platforms']['arm64'][key]="0.0.0" if case=="wrong-version" else False
                elif case=="missing-os":del proof['qualification']['5tratumOS']
                elif case in ("retention-config", "retention-manifest"):
                    key = "configDigest" if case == "retention-config" else "manifestDigest"
                    proof['platforms']['amd64'][key] = "sha256:" + "0"*64
                elif case == "receipt-tamper": receipt_path.write_text('{"result":"PASS","altered":true}')
                elif case in ("native-manager-channel", "native-manager-version", "different-shared-image", "different-shared-config"):
                    key = {"native-manager-channel":"nativeManagerObservationChannel", "native-manager-version":"nativeManagerObservedVersion", "different-shared-image":"sharedImageRef", "different-shared-config":"sharedConfigDigest"}[case]
                    proof['qualification']['5tratumOS'][key] = "unobserved"
                elif case == "rejection-scope": proof['qualification']['5tratumOS']['oldOsRejectionScope'] = "No host writes on any old OS"
                elif case in ("old-os", "retention-absent", "old-os-mutation"):
                    key = {"old-os": "osVersion", "retention-absent": "retentionAdmissionVerified", "old-os-mutation": "oldOsRejectedBeforeMutationVerified"}[case]
                    proof['qualification']['5tratumOS'][key] = "0.8.35" if case == "old-os" else False
                elif case in ("disconnect","ports","persistence"):
                    key={"disconnect":"clientDisconnectVerified","ports":"unchangedPortsVerified","persistence":"persistentStatePreserved"}[case]
                    proof['qualification']['umbrel1.7.4'][key]=False
                raw=(json.dumps(proof)+'\n').encode();(root/name).write_bytes(raw);row['publication']['sha256']=health.sha256(raw)
                with self.subTest(case=case):
                    if case is None:health.validate_publication(root,app_id,row)
                    else:
                        with self.assertRaises(AssertionError):health.validate_publication(root,app_id,row)


if __name__ == "__main__":
    unittest.main()
