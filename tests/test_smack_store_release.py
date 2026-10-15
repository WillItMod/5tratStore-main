"""Current Smack package is admitted before, never instead of, old guards."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("smack_store_release", ROOT / "scripts/smack_store_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
APP = release.APP


def historical(path):
    return subprocess.check_output(["git", "show", release.record()["baselineCommit"] + ":" + path], cwd=ROOT)


class SmackStoreReleaseTests(unittest.TestCase):
    def test_six_exact_fields_reverse_to_the_complete_real_prior_model(self):
        r = release.record()
        current = yaml.safe_load((ROOT / APP / "docker-compose.yml").read_bytes())
        prior = yaml.safe_load(historical(APP + "/docker-compose.yml"))
        self.assertEqual(release.previous_store_model(APP, current), prior)
        self.assertEqual(release.previous_store_model(APP, prior), prior)
        self.assertEqual(release.digest(current), r["runtimeContract"]["afterModelSHA256"])
        self.assertEqual(len(r["runtimeContract"]["changes"]), 6)
        self.assertEqual(release.package_version(APP, r["previousVersion"]), r["version"])
        with self.assertRaises(AssertionError):
            release.package_version(APP, "unreviewed-old-version")

    def test_other_services_wallet_mounts_permissions_ports_and_platform_fail_closed(self):
        current = yaml.safe_load((ROOT / APP / "docker-compose.yml").read_bytes())
        for service, key, value in (("node-a", "image", "changed"), ("ckpool", "image", "changed"),
                                    ("swap", "image", "changed"), ("init_permissions", "command", []),
                                    ("app", "volumes", []), ("app", "ports", ["123:3000"]),
                                    ("app", "healthcheck", {}), ("app", "stop_signal", "SIGKILL")):
            changed = copy.deepcopy(current)
            changed["services"][service][key] = value
            with self.subTest(service=service, key=key), self.assertRaises(AssertionError):
                release.previous_store_model(APP, changed)
        for key in ("APP_VERSION", "APP_REVISION", "APP_PLATFORM", "FIVETRAT_RELEASE_TAG", "APP_IMAGE"):
            changed = copy.deepcopy(current)
            changed["services"]["app"]["environment"][key] = "unreviewed"
            with self.subTest(key=key), self.assertRaises(AssertionError):
                release.previous_store_model(APP, changed)
        other = {"services": {"app": {"image": "unchanged"}}}
        self.assertEqual(release.previous_store_model("other-app", other), other)

    def test_editable_record_cannot_authorize_a_new_delta_or_hash(self):
        for field, value in (("imageRef", "moving:latest"), ("version", "99.0.0"),
                             ("runtimeContract", {"changes": []}), ("packageFiles", {})):
            changed = copy.deepcopy(release.record())
            changed[field] = value
            with tempfile.TemporaryDirectory() as raw:
                root = Path(raw)
                (root / "SMACK-STORE-UPDATE-2026-10-15.json").write_text(json.dumps(changed, indent=2) + "\n")
                with self.subTest(field=field), self.assertRaises(AssertionError):
                    release.record(root)

    def test_current_files_export_and_exact_publication_receipt_are_admitted(self):
        r = release.validate_files()
        receipt = json.loads((ROOT / r["publication"]["path"]).read_bytes())
        self.assertEqual(receipt["nativePreAndActualPublishedPostProofs"], "PASS both architectures")
        self.assertTrue(receipt["nativeNormalSIGINTExit0BothPreAndPost"])
        self.assertFalse(receipt["newAliases"])
        self.assertIn("does not generate", receipt["attestation"])
        proof = json.loads((ROOT / r["platformDelivery"]["path"]).read_bytes())
        self.assertEqual(proof["result"], "PASS")
        self.assertEqual(proof["packageBinding"][r["channel"].lower()]["currentComposeSHA256"],
                         r["packageFiles"][APP + "/docker-compose.yml"]["sha256"])
        self.assertEqual(proof["actualExportLoaderCases"], ["1.7.4-strict:UMBREL", "1.7.4-loose:UMBREL",
                                                          "2.0.0-strict:UMBREL", "2.0.0-loose:UMBREL"])
        for path, identity in r["packageFiles"].items():
            if path.endswith(("docker-compose.yml", "umbrel-app.yml", "5tratstore-app.yml", "exports.sh")):
                continue
            self.assertEqual((ROOT / path).read_bytes(), historical(path))
        for name in r["frozenRecords"]:
            self.assertEqual((ROOT / name).read_bytes(), historical(name))
        self.assertEqual((ROOT / APP / "exports.sh").read_bytes(), release.EXPORT)

    def test_manifests_preserve_all_fields_notes_and_published_ports(self):
        r = release.record()
        for filename in ("umbrel-app.yml", "5tratstore-app.yml"):
            path = APP + "/" + filename
            current = yaml.safe_load((ROOT / path).read_bytes())
            old = yaml.safe_load(historical(path))
            self.assertEqual(current.pop("version"), r["version"])
            self.assertEqual(old.pop("version"), r["previousVersion"])
            self.assertEqual(current.pop("releaseNotes"), r["releaseNotePrefix"] + "\n" + old.pop("releaseNotes"))
            self.assertEqual(current, old)
        self.assertEqual((ROOT / APP / "umbrel-app.yml").read_bytes(), (ROOT / APP / "5tratstore-app.yml").read_bytes())

    def test_current_metadata_validator_uses_new_package_without_losing_old_proofs(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/validate-5tratsmack-metadata.py")],
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(release.record()["version"], result.stdout)
        self.assertIn(release.SOURCE, result.stdout)


if __name__ == "__main__":
    unittest.main()
