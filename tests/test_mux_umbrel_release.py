"""Adversarial catalogue checks for the new protected Umbrel-only MUX app."""
import copy
import hashlib
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
SPEC = importlib.util.spec_from_file_location("mux_umbrel_release", ROOT / "scripts/mux_umbrel_release.py")
mux = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mux)
CHANNEL = json.loads((ROOT / mux.RECORD_NAME).read_text())["channel"]
HISTORICAL_PACKAGE = ROOT / "tests/fixtures/mux-umbrel-0.9.80"
SYNTHETIC_IMAGE = "ghcr.io/willitmod/5tratmux-app:synthetic-unit-test@sha256:" + "1" * 64


def synthetic_icon_coverage(delivery_channel, observation_channel=None):
    observation_channel = observation_channel or delivery_channel
    return {"desktopIconRenderedVerified": True, "iconObservationChannel": observation_channel,
        "absoluteIconURL": mux.ICON_URLS[observation_channel], "iconObservedVersion": mux.VERSIONS[observation_channel],
        "iconNaturalWidth": 783, "sharedIconSHA256": mux.ICON_SHA256,
        "nativeIconObservationReceiptSHA256": "8" * 64, "storeCardExercised": False,
        "decodedChannelAsset": {"channel": delivery_channel, "absoluteIconURL": mux.ICON_URLS[delivery_channel],
            "sha256": mux.ICON_SHA256, "browserDecodedVerified": True,
            "naturalWidth": 783, "naturalHeight": 783,
            "fetchEvidenceSHA256": mux.ICON_FETCH_EVIDENCE_SHA256,
            "decodeEvidenceSHA256": mux.ICON_DECODE_EVIDENCE_SHA256}}



class MuxUmbrelReleaseTests(unittest.TestCase):
    def test_pending_metadata_cannot_be_admitted_as_a_published_release(self):
        # Exercise the original admission boundary directly. Newer package
        # dispatch must not bypass this deliberately pending-record case.
        with patch.dict(mux.LOCKS, {CHANNEL: None}):
            with self.assertRaisesRegex(AssertionError, "not been finalized"):
                mux.record()

    def test_finalized_historical_record_and_delivery_remain_exact(self):
        # Immutable release evidence is independent of the current package.
        release = mux.record()
        proof = mux.validate_publication(ROOT, release)
        self.assertEqual(release['version'], mux.VERSIONS[CHANNEL])
        self.assertEqual(proof['result'], 'PASS')

    def test_permanent_mux_admission_does_not_freeze_unrelated_app_updates(self):
        release = {"channel": CHANNEL}
        with tempfile.TemporaryDirectory() as directory, patch.object(mux, "record", return_value=release), \
             patch.object(mux, "validate_package_files") as package, \
             patch.object(mux, "validate_publication") as publication, \
             patch.object(mux, "validate_baseline") as baseline:
            root = Path(directory)
            mux.validate(root)
            package.assert_called_once_with(root, release)
            publication.assert_called_once_with(root, release)
            baseline.assert_not_called()
            mux.validate(root, check_baseline=True)
            baseline.assert_called_once_with(root, CHANNEL)

    def test_real_git_baseline_rejects_old_recipe_json_fumbrel_and_added_apps(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = {"willitmod-old/docker-compose.yml": b"services: {}\n",
                         "willitmod-dev-fumbrel/umbrel-app.yml": b"version: 0.1.3\n",
                         "FROZEN-RELEASE.json": b'{"syntheticHistoricalRecord":true}\n'}
            for name, raw in originals.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            def git(*arguments):
                return subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.DEVNULL)
            git("init", "--quiet")
            shutil.copytree(ROOT / mux.APP, root / mux.APP)
            git("add", ".")
            git("-c", "user.name=Disposable Test", "-c", "user.email=unit@example.invalid", "commit", "--quiet", "-m", "Synthetic baseline")
            baseline = git("rev-parse", "HEAD").decode().strip()
            with patch.dict(mux.BASELINES, {CHANNEL: baseline}):
                mux.validate_baseline(root, CHANNEL)
                for name, raw in originals.items():
                    (root / name).write_bytes(raw + b"altered\n")
                    try:
                        with self.subTest(protected=name), self.assertRaises(AssertionError):
                            mux.validate_baseline(root, CHANNEL)
                    finally:
                        (root / name).write_bytes(raw)
                for name in ("willitmod-old/new-extra-file", "willitmod-unreviewed/umbrel-app.yml"):
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"synthetic extra file\n")
                    try:
                        with self.subTest(extra=name), self.assertRaises(AssertionError):
                            mux.validate_baseline(root, CHANNEL)
                    finally:
                        path.unlink()

    def test_exact_runtime_security_model_rejects_bypass_or_extra_services(self):
        original = mux.recipe_model(SYNTHETIC_IMAGE, CHANNEL)
        mux.validate_recipe(original, SYNTHETIC_IMAGE, CHANNEL)
        changes = [("user", "0:0"), ("privileged", True), ("read_only", False),
                   ("init", 1), ("cap_drop", []), ("cap_add", ["SYS_ADMIN"]),
                   ("security_opt", []), ("network_mode", "host"),
                   ("pid", "host"), ("ports", ["21222:21222", "7331:7331"]),
                   ("volumes", ["/var/run/docker.sock:/var/run/docker.sock"]),
                   ("image", "moving:latest"), ("command", ["python", "app.py"]),
                   ("mem_limit", "384m"), ("pids_limit", 0), ("stop_grace_period", "1s")]
        for key, value in changes:
            changed = copy.deepcopy(original)
            changed["services"]["server"][key] = value
            with self.subTest(key=key), self.assertRaises(AssertionError):
                mux.validate_recipe(changed, SYNTHETIC_IMAGE, CHANNEL)
        for changes in ({"MUX_PLATFORM": "native"}, {"MUX_OPERATOR_PASSWORD": "literal-password"},
                        {"MUX_AUTH_TRUSTED_PROXIES": "0.0.0.0/0"}, {"APP_PORT": "21223"},
                        {"STATE_DIR": "/tmp/state"}, {"MUX_HTTP_STRICT_HOST": "0"}):
            changed = copy.deepcopy(original)
            changed["services"]["server"]["environment"].update(changes)
            with self.subTest(environment=changes), self.assertRaises(AssertionError):
                mux.validate_recipe(changed, SYNTHETIC_IMAGE, CHANNEL)
        changed = copy.deepcopy(original)
        changed["services"]["app_proxy"]["network_mode"] = "service:server"
        with self.assertRaises(AssertionError):
            mux.validate_recipe(changed, SYNTHETIC_IMAGE, CHANNEL)

    def test_manifest_keeps_password_storage_and_umbrel_only_contract(self):
        original = yaml.safe_load((HISTORICAL_PACKAGE / "umbrel-app.yml").read_text())
        mux.validate_manifest(original, CHANNEL)
        for field, value in (("version", "0.9.7.9"), ("port", 7331), ("deterministicPassword", False),
                             ("defaultPassword", "shared"), ("storage", {"dataRoot": "/"}),
                             ("dependencies", ["5tratumos"]), ("permissions", ["docker"])):
            changed = copy.deepcopy(original)
            changed[field] = value
            with self.subTest(field=field), self.assertRaises(AssertionError):
                mux.validate_manifest(changed, CHANNEL)

    def test_manifest_requires_channel_specific_absolute_public_icon(self):
        original = yaml.safe_load((HISTORICAL_PACKAGE / "umbrel-app.yml").read_text())
        expected = f"https://raw.githubusercontent.com/WillItMod/5tratStore-{CHANNEL.lower()}/main/{mux.APP}/icon.png"
        self.assertEqual(original["icon"], expected)
        mux.validate_manifest(original, CHANNEL)
        wrong_channel = "dev" if CHANNEL == "MAIN" else "main"
        for icon in ("icon.png", "/icon.png", "icon.svg", "//raw.githubusercontent.com/icon.png",
                     expected.replace("https:", "http:"),
                     expected.replace(f"5tratStore-{CHANNEL.lower()}", f"5tratStore-{wrong_channel}"),
                     expected.replace("icon.png", "icon.svg")):
            changed = copy.deepcopy(original)
            changed["icon"] = icon
            with self.subTest(icon=icon), self.assertRaises(AssertionError):
                mux.validate_manifest(changed, CHANNEL)

    def package_fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copytree(ROOT / mux.APP, root / mux.APP)
        # Retain the predecessor contract even when the current app is 0.9.82.
        # Only these public text files changed; artwork and data placeholder
        # remain the same independently pinned bytes.
        for name in ("docker-compose.yml", "umbrel-app.yml", "hooks/pre-start"):
            shutil.copyfile(HISTORICAL_PACKAGE / name, root / mux.APP / name)
        recipe = root / mux.APP / "docker-compose.yml"
        model = mux.recipe_model(SYNTHETIC_IMAGE, CHANNEL)
        recipe.write_text(yaml.safe_dump(model, sort_keys=False))
        release = {"channel": CHANNEL, "imageRef": SYNTHETIC_IMAGE,
                   "packageFiles": {str(path.relative_to(root)): {"sha256": mux.sha256(path.read_bytes()),
                                    "mode": oct(path.stat().st_mode & 0o777)}
                                    for path in (root / mux.APP).rglob("*") if path.is_file()}}
        return root, release

    def test_package_forbids_native_os_manifests_sources_maps_and_extra_files(self):
        root, release = self.package_fixture()
        mux.validate_package_files(root, release)
        for filename in ("5tratstore-app.yml", "global-app.yml", "app.py", "app.js.map", "exports.sh"):
            path = root / mux.APP / filename
            path.write_text("synthetic forbidden file\n")
            try:
                with self.subTest(filename=filename), self.assertRaises(AssertionError):
                    mux.validate_package_files(root, release)
            finally:
                path.unlink()

    def test_hook_and_artwork_cannot_be_reauthorized_by_editing_record(self):
        for name in ("hooks/pre-start", "icon.png"):
            root, release = self.package_fixture()
            path = root / mux.APP / name
            path.write_bytes(b"synthetic altered hook or icon\n")
            release["packageFiles"][mux.APP + "/" + name]["sha256"] = mux.sha256(path.read_bytes())
            with self.subTest(name=name), self.assertRaises(AssertionError):
                mux.validate_package_files(root, release)

    def test_symlink_or_nonexecutable_hook_is_refused(self):
        root, release = self.package_fixture()
        hook = root / mux.APP / "hooks/pre-start"
        hook.chmod(0o644)
        with self.assertRaises(AssertionError):
            mux.validate_package_files(root, release)
        hook.chmod(0o755)
        icon = root / mux.APP / "icon.png"
        outside = root / "outside.png"
        outside.write_bytes(icon.read_bytes())
        icon.unlink()
        icon.symlink_to(outside)
        with self.assertRaises(AssertionError):
            mux.validate_package_files(root, release)

    def test_release_locks_cannot_be_replaced_by_mutable_receipt_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original = json.loads((ROOT / mux.RECORD_NAME).read_text())
            for field, value in (("imageRef", SYNTHETIC_IMAGE), ("sourceRevision", "f" * 40),
                                 ("sourceTree", "e" * 40), ("status", "qualified")):
                changed = copy.deepcopy(original)
                changed[field] = value
                (root / mux.RECORD_NAME).write_text(json.dumps(changed))
                with self.subTest(field=field), self.assertRaises(AssertionError):
                    mux.record(root)

    def test_shared_artwork_requires_actual_native_rendering_and_exact_decoded_delivery_asset(self):
        other_channel = "DEV" if CHANNEL == "MAIN" else "MAIN"
        original = synthetic_icon_coverage(CHANNEL, other_channel)
        self.assertEqual(mux.validate_icon_coverage(original, CHANNEL), original)
        # The observation stays visibly on its actual channel. Same bytes and a
        # separately decoded delivery URL support the bounded renderer coverage.
        self.assertNotEqual(original["iconObservationChannel"], CHANNEL)
        self.assertNotEqual(original["absoluteIconURL"], original["decodedChannelAsset"]["absoluteIconURL"])
        for case in ("missing-native", "native-false", "native-receipt", "unknown-channel", "wrong-observed-url",
                     "wrong-observed-version", "different-shared-artwork", "different-decoded-artwork",
                     "decode-absent", "wrong-delivery-url", "wrong-decode-evidence", "wrong-geometry", "claimed-store-card"):
            row = copy.deepcopy(original)
            if case == "missing-native": del row["desktopIconRenderedVerified"]
            elif case == "native-false": row["desktopIconRenderedVerified"] = False
            elif case == "native-receipt": row["nativeIconObservationReceiptSHA256"] = "missing"
            elif case == "unknown-channel": row["iconObservationChannel"] = "unobserved"
            elif case == "wrong-observed-url": row["absoluteIconURL"] = mux.ICON_URLS[CHANNEL]
            elif case == "wrong-observed-version": row["iconObservedVersion"] = mux.VERSIONS[CHANNEL]
            elif case == "different-shared-artwork": row["sharedIconSHA256"] = "0" * 64
            elif case == "different-decoded-artwork": row["decodedChannelAsset"]["sha256"] = "0" * 64
            elif case == "decode-absent": row["decodedChannelAsset"]["browserDecodedVerified"] = False
            elif case == "wrong-delivery-url": row["decodedChannelAsset"]["absoluteIconURL"] = mux.ICON_URLS[other_channel]
            elif case == "wrong-decode-evidence": row["decodedChannelAsset"]["decodeEvidenceSHA256"] = "0" * 64
            elif case == "wrong-geometry": row["decodedChannelAsset"]["naturalWidth"] = 0
            else: row["storeCardExercised"] = True
            with self.subTest(case=case), self.assertRaises((AssertionError, KeyError)):
                mux.validate_icon_coverage(row, CHANNEL)

    def test_even_a_rehashed_receipt_cannot_claim_missing_arch_source_protection_or_qualification(self):
        # Synthetic, disposable schema exercise. This never becomes a catalogue
        # receipt and does not contact or claim to qualify any running image.
        version = mux.VERSIONS[CHANNEL]
        row = {"manifestDigest": "sha256:" + "2" * 64, "configDigest": "sha256:" + "3" * 64,
               "protectedExecutableSHA256": "4" * 64, "noApplicationPythonSources": True,
               "noSourceMaps": True, "nativeStartupVerified": True,
               "operatorAuthenticationVerified": True, "httpHealthVersion": version, "wrapperOnlyUpdateVerified": True}
        qualification = {"result": "PASS", "architecture": "amd64",
                         "nativeUpdateStopStartPersistenceVerified": True,
                         **synthetic_icon_coverage(CHANNEL),
                         "receiptSHA256": "5" * 64, "receipt": "synthetic-unit-test.json"}
        original = {"schemaVersion": 1, "result": "PASS", "sourceRevision": mux.SOURCE,
                    "sourceTree": mux.TREE, "imageRef": SYNTHETIC_IMAGE,
                    "anonymousIndexAndBothPlatformsVerified": True,
                    "platforms": {"amd64": copy.deepcopy(row), "arm64": copy.deepcopy(row)},
                    "umbrelQualification": {"1.7.4": copy.deepcopy(qualification), "2.0.0": copy.deepcopy(qualification)}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            name = f"release-records/mux-umbrel-{version}-delivery.json"
            path = root / name
            path.parent.mkdir()
            qualification_raw = b'{"result":"PASS","syntheticUnitFixture":true}\n'
            (root / "release-records/synthetic-unit-test.json").write_bytes(qualification_raw)
            for qualified in original["umbrelQualification"].values():qualified["receiptSHA256"] = mux.sha256(qualification_raw)
            release = {"channel": CHANNEL, "imageRef": SYNTHETIC_IMAGE, "publication": {"path": name},
                       "platforms": {arch: {key: row[key] for key in ("manifestDigest", "configDigest")} for arch in ("amd64", "arm64")}}
            old_record = json.loads((ROOT / mux.PREDECESSOR_NAME).read_text())
            (root / mux.PREDECESSOR_NAME).write_bytes((ROOT / mux.PREDECESSOR_NAME).read_bytes())
            old_delivery = old_record["publication"]["path"]
            (root / old_delivery).write_bytes((ROOT / old_delivery).read_bytes())
            prior_platforms = json.loads((ROOT / old_delivery).read_text())["platforms"]
            for architecture in ("amd64", "arm64"):
                original["platforms"][architecture]["protectedExecutableSHA256"] = prior_platforms[architecture]["protectedExecutableSHA256"]
            mutations = [("sourceRevision", "0" * 40), ("anonymousIndexAndBothPlatformsVerified", False),
                         ("platforms.amd64.noApplicationPythonSources", False),
                         ("platforms.amd64.configDigest", "sha256:" + "0"*64),
                         ("platforms.arm64.manifestDigest", "sha256:" + "0"*64),
                         ("platforms.arm64.noSourceMaps", False),
                         ("platforms.arm64.nativeStartupVerified", False),
                         ("platforms.arm64.wrapperOnlyUpdateVerified", False),
                         ("platforms.amd64.protectedExecutableSHA256", "0" * 64),
                         ("platforms.amd64.operatorAuthenticationVerified", False),
                         ("platforms.amd64.httpHealthVersion", "0.9.78"),
                         ("umbrelQualification.1.7.4.result", "pending"),
                         ("umbrelQualification.1.7.4.desktopIconRenderedVerified", False),
                         ("umbrelQualification.1.7.4.absoluteIconURL", "icon.png"),
                         ("umbrelQualification.1.7.4.iconNaturalWidth", 0),
                         ("umbrelQualification.1.7.4.storeCardExercised", True),
                         ("umbrelQualification.1.7.4.receiptSHA256", "0" * 64)]
            for field, value in [(None, None), *mutations]:
                proof = copy.deepcopy(original)
                if field:
                    keys = (field.split(".") if not field.startswith("umbrelQualification.")
                            else ["umbrelQualification", *field[len("umbrelQualification."):].rsplit(".", 1)])
                    node = proof
                    for key in keys[:-1]:
                        node = node[key]
                    node[keys[-1]] = value
                raw = (json.dumps(proof) + "\n").encode()
                path.write_bytes(raw)
                release["publication"]["sha256"] = mux.sha256(raw)
                with self.subTest(field=field), patch.dict(mux.PUBLICATION_LOCKS, {CHANNEL: mux.sha256(raw)}):
                    if field is None:
                        mux.validate_publication(root, release)
                    else:
                        with self.assertRaises(AssertionError):
                            mux.validate_publication(root, release)


if __name__ == "__main__":
    unittest.main()
