"""The pool successor admits one image delta and preserves the complete package."""
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
SPEC = importlib.util.spec_from_file_location("powpow_pool_stability", ROOT / "scripts/powpow_share_partition_release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)
SYNTHETIC_TAG = "ghcr.io/willitmod/powpow-pool:disposable-share-partition-qa"
SYNTHETIC_IMAGE = SYNTHETIC_TAG + "@sha256:" + "1" * 64


class PowPowSharePartitionTests(unittest.TestCase):
    def test_predecessor_bytes_accept_only_the_exact_successor(self):
        old = release.baseline_bytes(f"{release.APP}/umbrel-app.yml")
        current = release.expected_package_bytes("umbrel-app.yml")
        self.assertEqual(release.previous_package_bytes("umbrel-app.yml", old), old)
        self.assertEqual(release.previous_package_bytes("umbrel-app.yml", current), old)
        with self.assertRaisesRegex(AssertionError, "successor bytes"):
            release.previous_package_bytes("umbrel-app.yml", current + b"\n# unreviewed\n")
        with self.assertRaisesRegex(AssertionError, "successor file"):
            release.previous_package_bytes("exports.sh", b"unreviewed")

    def test_native_schema_qualification_requires_every_case_and_matching_bytes(self):
        native = {"result": "PASS", "bootstrapSHA256": release.BOOTSTRAP_SHA256,
                  "allDisposableObjectsRemoved": True,
                  "cases": {name: True for name in release.REQUIRED_SCHEMA_CASES}}
        proof = {"result": "PASS", "bootstrapSHA256": release.BOOTSTRAP_SHA256,
                 "platforms": {"amd64": copy.deepcopy(native), "arm64": copy.deepcopy(native)}}
        platforms = {arch: {'manifestDigest': 'sha256:' + digit * 64, 'configDigest': 'sha256:' + '3' * 64}
                     for arch, digit in [('amd64', '1'), ('arm64', '2')]}
        for arch, row in proof['platforms'].items():
            row.update(nativeArchitecture=arch, verifiedNativeManifestDigest=platforms[arch]['manifestDigest'])
        self.assertEqual(release.validate_schema_qualification(proof, platforms), proof)
        for arch in proof["platforms"]:
            for change in ("failure", "wrong SQL", "missing case", "failed case", "cleanup", "wrong architecture", "wrong manifest"):
                altered = copy.deepcopy(proof)
                row = altered["platforms"][arch]
                if change == "failure": row["result"] = "FAIL"
                elif change == "wrong SQL": row["bootstrapSHA256"] = "0" * 64
                elif change == "missing case": row["cases"].pop(next(iter(row["cases"])))
                elif change == "failed case": row["cases"][next(iter(row["cases"]))] = False
                elif change == "cleanup": row["allDisposableObjectsRemoved"] = False
                elif change == "wrong architecture": row['nativeArchitecture'] = 'unknown'
                else: row['verifiedNativeManifestDigest'] = 'sha256:' + '0' * 64
                with self.subTest(arch=arch, change=change), self.assertRaises(AssertionError):
                    release.validate_schema_qualification(altered, platforms)

    def successor(self):
        model = release.baseline_model()
        model["services"]["pool"]["image"] = SYNTHETIC_IMAGE
        return model

    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        shutil.copytree(ROOT / release.APP, root / release.APP)
        for name in ("docker-compose.yml", *release.MANIFESTS):
            (root / release.APP / name).write_bytes(release.expected_package_bytes(name, image=SYNTHETIC_IMAGE))
        # Read the real immutable Git predecessor while inspecting disposable files.
        baseline_git = release.git
        patcher = patch.object(release, "git", side_effect=lambda _root, *arguments: baseline_git(ROOT, *arguments))
        patcher.start()
        self.addCleanup(patcher.stop)
        return root

    def test_pending_publication_cannot_be_admitted(self):
        with patch.object(release, "IMAGE_REF", None), self.assertRaisesRegex(AssertionError, "not been finalized"):
            release.record()

    def test_whole_model_restores_only_the_exact_predecessor(self):
        previous = release.baseline_model()
        current = self.successor()
        with patch.object(release, "IMAGE_TAG", SYNTHETIC_TAG), patch.object(release, "IMAGE_REF", SYNTHETIC_IMAGE):
            self.assertEqual(release.previous_model(release.APP, previous), previous)
            self.assertEqual(release.previous_model(release.APP, current), previous)
            self.assertEqual(release.previous_model("other-app", current), current)
        self.assertEqual(release.package_version(release.APP, release.PREVIOUS_VERSION), release.VERSION)
        self.assertEqual(release.package_version(release.APP, release.VERSION), release.VERSION)
        with self.assertRaises(AssertionError):
            release.package_version(release.APP, "99.0.0")

    def test_drift_in_every_service_and_pool_settings_is_rejected(self):
        original = self.successor()
        changes = [
            ("app", "image", "changed:latest"), ("app", "environment", {}),
            ("app", "volumes", []), ("app", "user", "0:0"),
            ("pool", "image", "changed:latest"), ("pool", "ports", ["9556:9555"]),
            ("pool", "volumes", []), ("pool", "environment", {"WAIT_FOR_FULL_SYNC": "0"}),
            ("pool", "command", ["sh"]), ("pool", "restart", "no"),
            ("litecoin", "image", "changed:latest"), ("dogecoin", "image", "changed:latest"),
            ("postgres", "image", "changed:latest"), ("init_permissions", "command", []),
            ("app_proxy", "networks", []),
        ]
        for service, key, value in changes:
            changed = copy.deepcopy(original)
            changed["services"][service][key] = value
            with self.subTest(service=service, key=key), self.assertRaises(AssertionError):
                release.validate_model(changed, image=SYNTHETIC_IMAGE)
        changed = copy.deepcopy(original)
        changed["services"]["unreviewed"] = {"image": "new:latest"}
        with self.assertRaises(AssertionError):
            release.validate_model(changed, image=SYNTHETIC_IMAGE)

    def test_manifest_changes_only_version_and_prepended_note(self):
        for name in release.MANIFESTS:
            old = yaml.safe_load(release.baseline_bytes(f"{release.APP}/{name}"))
            current = yaml.safe_load(release.expected_package_bytes(name))
            self.assertEqual(current.pop("version"), release.VERSION)
            self.assertEqual(old.pop("version"), release.PREVIOUS_VERSION)
            self.assertEqual(current.pop("releaseNotes"), release.NOTE + "\n" + old.pop("releaseNotes"))
            self.assertEqual(current, old)

    def test_package_rejects_extra_bytes_files_modes_and_symlinks(self):
        root = self.fixture()
        release.validate_package(root, image=SYNTHETIC_IMAGE)
        for name in ("docker-compose.yml", "umbrel-app.yml", "global-app.yml", "hooks/pre-start", "exports.sh", "powpow-2-schema.sql.template"):
            path = root / release.APP / name
            original = path.read_bytes()
            path.write_bytes(original + b"\n# unreviewed\n")
            try:
                with self.subTest(name=name), self.assertRaises(AssertionError):
                    release.validate_package(root, image=SYNTHETIC_IMAGE)
            finally:
                path.write_bytes(original)
        extra = root / release.APP / "extra.yml"
        extra.write_text("unreviewed\n")
        with self.assertRaises(AssertionError):
            release.validate_package(root, image=SYNTHETIC_IMAGE)
        extra.unlink()
        hook = root / release.APP / "hooks/pre-start"
        mode = hook.stat().st_mode & 0o777
        hook.chmod(0o600)
        with self.assertRaises(AssertionError):
            release.validate_package(root, image=SYNTHETIC_IMAGE)
        hook.chmod(mode)
        icon = root / release.APP / "icon.png"
        outside = root / "outside.png"
        icon.rename(outside)
        icon.symlink_to(outside)
        with self.assertRaises(AssertionError):
            release.validate_package(root, image=SYNTHETIC_IMAGE)

    def test_release_scope_protects_fumbrel_and_historical_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            protected = {"willitmod-dev-fumbrel/umbrel-app.yml": b"version: 0.1.3\n", "FROZEN-RECORD.json": b'{"immutable":true}\n', "powpow-release-records/older.json": b'{"proof":"retained"}\n'}
            for name, raw in protected.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            git = lambda *arguments: subprocess.check_output(["git", *arguments], cwd=root, stderr=subprocess.DEVNULL)
            git("init", "--quiet")
            git("add", ".")
            git("-c", "user.name=Disposable Test", "-c", "user.email=unit@example.invalid", "commit", "--quiet", "-m", "Synthetic baseline")
            baseline = git("rev-parse", "HEAD").decode().strip()
            with patch.object(release, "BASELINE", baseline):
                release.validate_baseline(root)
                for name, raw in protected.items():
                    (root / name).write_bytes(raw + b"altered\n")
                    try:
                        with self.subTest(name=name), self.assertRaises(AssertionError):
                            release.validate_baseline(root)
                    finally:
                        (root / name).write_bytes(raw)

    def test_editable_evidence_cannot_authorize_a_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / release.RECORD_NAME).write_text(json.dumps({"status": "qualified", "imageRef": SYNTHETIC_IMAGE}))
            with patch.object(release, "IMAGE_TAG", SYNTHETIC_TAG), patch.object(release, "IMAGE_REF", SYNTHETIC_IMAGE), patch.object(release, "RECORD_SHA256", "0" * 64), self.assertRaisesRegex(AssertionError, "Unreviewed"):
                release.record(root)


if __name__ == "__main__":
    unittest.main()
