"""Version normalization is additive and cannot relax prior runtime contracts."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import yaml
import app_version_normalization as normalization
from test_mux_umbrel_release import mux as mux_release

health_release = normalization.health_release

ROOT = Path(__file__).resolve().parents[1]
APP = normalization.APP


class AppVersionNormalizationTests(unittest.TestCase):
    def test_bch2_exact_version_only_delta_restores_the_frozen_whole_model(self):
        row = normalization.contract()["apps"][APP]
        current = yaml.safe_load((ROOT / APP / "docker-compose.yml").read_text())
        old = yaml.safe_load(normalization.source_bytes(APP + "/docker-compose.yml", normalization.contract()["baselineCommit"]))
        self.assertEqual(normalization.previous_app_version_model(APP, current), old)
        self.assertEqual(normalization.digest(health_release.previous_model(APP, current, ROOT)), row["afterModelSHA256"])
        self.assertEqual(normalization.previous_app_version_model(APP, old), old)
        self.assertEqual(normalization.package_version(APP, row["beforeVersion"]), health_release.version(APP, normalization.RECORD["channel"]))
        self.assertEqual(normalization.package_version(APP, row["version"]), health_release.version(APP, normalization.RECORD["channel"]))
        with self.assertRaises(AssertionError):
            normalization.package_version(APP, "arbitrary-old-version")

    def test_bch2_images_mounts_ports_policy_and_missing_version_are_rejected(self):
        current = yaml.safe_load((ROOT / APP / "docker-compose.yml").read_text())
        for service, key, value in (("app", "image", "moving:latest"), ("app", "volumes", []),
                                    ("app", "ports", ["123:3000"]), ("app", "user", "0:0"),
                                    ("app", "group_add", ["0"]), ("bch2", "stop_grace_period", "1s"),
                                    ("ckpool", "image", "changed:latest"), ("init_permissions", "command", [])):
            changed = copy.deepcopy(current)
            changed["services"][service][key] = value
            with self.subTest(service=service, key=key), self.assertRaises(AssertionError):
                normalization.previous_app_version_model(APP, changed)
        changed = copy.deepcopy(current)
        del changed["services"]["app"]["environment"]["APP_VERSION"]
        with self.assertRaises(AssertionError):
            normalization.previous_app_version_model(APP, changed)

    def test_editable_record_cannot_authorize_extra_fields_or_unreviewed_hashes(self):
        current = yaml.safe_load((ROOT / APP / "docker-compose.yml").read_text())
        for field, value in (("afterModelSHA256", "0" * 64), ("version", "99.0.0"),
                             ("changes", [{"path": ["services", "app", "image"], "before": "old", "after": "new"}])):
            record = copy.deepcopy(normalization.RECORD)
            record["apps"][APP][field] = value
            with self.subTest(field=field), patch.object(normalization, "RECORD", record), self.assertRaises(AssertionError):
                normalization.previous_app_version_model(APP, current)
        other = {"services": {"app": {"image": "unchanged"}}}
        self.assertEqual(normalization.previous_app_version_model("other-app", other), other)
        self.assertEqual(normalization.package_version("other-app", "unchanged"), "unchanged")

    def test_bch2_manifests_change_only_version_and_the_prepended_note(self):
        row = normalization.contract()["apps"][APP]
        for filename in normalization.MANIFESTS:
            path = ROOT / APP / filename
            if not path.exists():
                continue
            current = health_release.previous_manifest(APP, yaml.safe_load(path.read_text()), filename, ROOT)
            old = yaml.safe_load(normalization.source_bytes(APP + "/" + filename, normalization.contract()["baselineCommit"]))
            self.assertEqual(current.pop("version"), row["version"])
            self.assertEqual(old.pop("version"), row["beforeVersion"])
            self.assertEqual(current.pop("releaseNotes"), normalization.RECORD["releaseNotePrefix"] + "\n" + old.pop("releaseNotes"))
            self.assertEqual(current, old)

    def test_btc_exact_single_application_image_delta_preserves_environment_and_other_services(self):
        app = normalization.BTC_IDS[normalization.RECORD["channel"]]
        row = normalization.contract()["apps"][app]
        current = yaml.safe_load((ROOT / app / "docker-compose.yml").read_text())
        old = yaml.safe_load(normalization.source_bytes(app + "/docker-compose.yml", normalization.contract()["baselineCommit"]))
        self.assertEqual(normalization.previous_app_version_model(app, current), old)
        self.assertEqual(current["services"]["app"]["image"], normalization.BTC_IMAGE)
        self.assertEqual(current["services"]["app"]["environment"], old["services"]["app"]["environment"])
        self.assertEqual(normalization.package_version(app, row["beforeVersion"]), row["version"])
        for service, key, value in (("app", "image", normalization.BTC_OLD), ("app", "volumes", []),
                                    ("app", "environment", {}), ("app", "ports", ["123:3000"]),
                                    ("ckpool", "image", "changed:latest"), ("init", "command", [])):
            changed = copy.deepcopy(current)
            changed["services"][service][key] = value
            if service == "app" and key == "image":
                # The exact historical model is idempotently accepted; changing
                # its environment at the same time must still be refused.
                changed["services"]["app"]["environment"]["APP_VERSION_SUFFIX"] = "unreviewed"
            with self.subTest(service=service, key=key), self.assertRaises(AssertionError):
                normalization.previous_app_version_model(app, changed)

    def test_btc_manifest_only_version_and_note_and_exact_publication_binding(self):
        app = normalization.BTC_IDS[normalization.RECORD["channel"]]
        row = normalization.contract()["apps"][app]
        for filename in normalization.MANIFESTS:
            path = ROOT / app / filename
            if not path.exists():
                continue
            current = yaml.safe_load(path.read_text())
            old = yaml.safe_load(normalization.source_bytes(app + "/" + filename, normalization.contract()["baselineCommit"]))
            self.assertEqual(current.pop("version"), row["version"])
            self.assertEqual(old.pop("version"), row["beforeVersion"])
            self.assertEqual(current.pop("releaseNotes"), row["releaseNotePrefix"] + "\n" + old.pop("releaseNotes"))
            self.assertEqual(current, old)
        publication = normalization.RECORD["btcPublication"]
        self.assertEqual(publication["versionLiteral"], "0.7.83")
        self.assertEqual(publication["imageRef"], normalization.BTC_IMAGE)
        self.assertEqual(publication["workflowRun"], 38750325672)
        self.assertEqual(set(publication["images"]), {"amd64", "arm64"})
        raw = (ROOT / publication["publicationRecord"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), publication["publicationRecordSHA256"])
        actual = json.loads(raw)
        self.assertEqual(actual["image"], publication["imageRef"])
        self.assertEqual(actual["app_py_sha256"], publication["applicationSourceSHA256"])
        self.assertEqual((actual["source_commit"], actual["source_tree"]),
                         (publication["sourceRevision"], publication["sourceTree"]))
        self.assertEqual(actual["runtime_core_version"], publication["versionLiteral"])
        self.assertEqual({row["platform"]["architecture"]: {"manifestDigest": row["manifest"], "configDigest": row["config"]}
                          for row in actual["architectures"]}, publication["images"])
        self.assertTrue(actual["anonymous_registry_metadata_verified"])
        self.assertTrue(actual["native_actual_published_runtime_proofs"])
        changed = copy.deepcopy(normalization.RECORD)
        changed["btcPublication"]["applicationSourceSHA256"] = "0" * 64
        with patch.object(normalization, "RECORD", changed), self.assertRaises(AssertionError):
            normalization.contract()

    def test_all_owned_app_manifests_have_three_core_components(self):
        self.assertEqual(normalization.manifest_version_audit(), [], "PENDING app version normalization")

    def test_version_shape_keeps_dev_revision_but_rejects_four_component_cores(self):
        for version in ("0.2.1", "0.2.1-dev", "0.2.1-dev.2", "4.0.30-dev.4"):
            self.assertIsNotNone(normalization.VERSION.fullmatch(version))
        for version in ("0.2.0.12", "0.7.82.17-dev.1", "0.2", "0.2.1-dev.2.1", "0.2.01", "0.2.1-beta"):
            self.assertIsNone(normalization.VERSION.fullmatch(version))

    def test_all_published_ports_remain_exactly_at_the_channel_baseline(self):
        expected = normalization.contract()
        old = normalization.published_ports(expected["baselineCommit"])
        self.assertEqual(normalization.digest(old), expected["publishedPortsSHA256"])
        current = normalization.published_ports()
        # Admit only the exact new Umbrel-only MUX listener inventory. Every
        # preexisting app retains the frozen channel baseline without filters.
        self.assertEqual(current.pop(mux_release.APP), mux_release.PORTS)
        self.assertEqual(current, old)

    def test_every_preexisting_release_record_remains_byte_exact(self):
        revision = normalization.contract()["baselineCommit"]
        names = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", revision], cwd=ROOT, text=True).splitlines()
        records = [name for name in names if name.endswith(".json") and
                   ("/" not in name or name.startswith("release-records/"))]
        self.assertTrue(records)
        for name in records:
            with self.subTest(record=name):
                self.assertEqual((ROOT / name).read_bytes(), normalization.source_bytes(name, revision))


if __name__ == "__main__":
    unittest.main()
