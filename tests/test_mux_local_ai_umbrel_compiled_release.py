"""Admission regressions; existing runtime receipts qualify the actual images."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mux_local_ai_umbrel_compiled_release as gate


class CompiledSuccessorTests(unittest.TestCase):
    def test_unfinalized_record_cannot_authorize_itself(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / gate.RECORD_NAME).write_text(json.dumps({"channel": "MAIN"}))
            with patch.dict(gate.ADMISSION_LOCKS, {"MAIN": None}):
                with self.assertRaisesRegex(AssertionError, "not been independently finalized"):
                    gate.record(root)

    def test_evidence_refuses_escape_symlinks_and_changed_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            records = root / "release-records"
            records.mkdir()
            raw = b'{"verified": true}\n'
            (records / "actual.json").write_bytes(raw)
            reference = {"path": "release-records/actual.json", "sha256": gate.sha256(raw)}
            self.assertEqual(gate.referenced(root, reference), {"verified": True})
            for path in ("../actual.json", "/tmp/actual.json", "release-records/../actual.json"):
                with self.subTest(path=path), self.assertRaises(AssertionError):
                    gate.referenced(root, {**reference, "path": path})
            (records / "link.json").symlink_to(records / "actual.json")
            with self.assertRaises(AssertionError):
                gate.referenced(root, {**reference, "path": "release-records/link.json"})
            (records / "actual.json").write_text("{}\n")
            with self.assertRaisesRegex(AssertionError, "bytes changed"):
                gate.referenced(root, reference)

    def test_predecessor_qualification_is_read_without_reexecuting_models(self):
        old = {"channel": "MAIN"}
        with patch.object(gate.previous, "record", return_value=(old, {})), \
                patch.object(gate.previous, "validate_delivery") as delivery:
            self.assertEqual(gate.predecessor(ROOT), old)
            delivery.assert_called_once_with(ROOT, old, {})

    def test_newest_record_uses_compiled_gate(self):
        import mux_umbrel_release as dispatcher
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / gate.RECORD_NAME).write_text("{}\n")
            with patch.object(gate, "validate", return_value={"version": "0.9.85"}) as validate:
                self.assertEqual(dispatcher.validate(root), {"version": "0.9.85"})
                validate.assert_called_once_with(root)
                with self.assertRaises(AssertionError):
                    dispatcher.validate(root, check_baseline=True)

    def test_package_changes_cannot_expand_runtime_or_replace_companion(self):
        old, _ = gate.previous.record(ROOT)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            app = root / gate.APP
            shutil.copytree(ROOT / gate.APP, app)
            row = {"channel": old["channel"], "version": gate.VERSIONS[old["channel"]],
                   "imageRef": "ghcr.io/willitmod/5tratmux-app:0.9.85-umbrel@sha256:" + "1" * 64}
            recipe = gate.previous.previous.recipe.recipe_model(
                gate.previous.previous.APPLICATION_IMAGE_REFS[old["channel"]],
                old["localAIImageRef"], old["channel"])
            recipe["services"]["server"]["image"] = row["imageRef"]
            recipe["services"]["server"]["environment"]["APP_VERSION"] = row["version"]
            manifest = gate.previous.previous.recipe.manifest_model(old["channel"])
            manifest.update(version=row["version"], releaseNotes="Compiled application update")
            (app / "umbrel-app.yml").write_text(json.dumps(manifest))

            def retain(model):
                (app / "docker-compose.yml").write_text(json.dumps(model))
                row["packageFiles"] = {gate.APP + "/" + name: {
                    "sha256": gate.sha256((app / name).read_bytes()),
                    "mode": oct((app / name).stat().st_mode & 0o777)}
                    for name in gate.previous.previous.recipe.FILES}

            retain(recipe)
            gate.validate_package(root, row, old)
            for mutate in (
                lambda x: x["services"]["server"].update(privileged=True),
                lambda x: x["services"]["server"]["volumes"].append("/var/run/docker.sock:/var/run/docker.sock"),
                lambda x: x["services"]["server"]["environment"].update(MUX_OPERATOR_PASSWORD="fixed-password"),
                lambda x: x["services"]["local_ai"].update(image="unreviewed:latest"),
                lambda x: x["services"]["local_ai"].update(mem_limit="8g"),
            ):
                changed = copy.deepcopy(recipe)
                mutate(changed)
                retain(changed)
                with self.assertRaisesRegex(AssertionError, "Only the APP image"):
                    gate.validate_package(root, row, old)


if __name__ == "__main__":
    unittest.main()
