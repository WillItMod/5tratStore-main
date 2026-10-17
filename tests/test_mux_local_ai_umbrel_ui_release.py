"""Synthetic UI-only admission attacks; these tests do not qualify a runtime."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mux_local_ai_umbrel_ui_release as ui


class UiOnlySuccessorTests(unittest.TestCase):
    def fixture(self, root):
        def retain(name, data):
            raw = (json.dumps(data, sort_keys=True) + "\n").encode()
            file = root / "release-records" / name
            file.parent.mkdir(exist_ok=True)
            file.write_bytes(raw)
            return {"path": "release-records/" + name, "sha256": ui.sha256(raw)}
        self.retain = retain
        old = {"imageRef": ui.previous.APPLICATION_IMAGE_REFS["MAIN"], "channel": "MAIN",
            "localAIImageRef": "ghcr.io/willitmod/5tratmux-app:local-ai-0.1.9-umbrel@sha256:" + "6" * 64}
        row = {"version": "0.9.83", "channel": "MAIN", "imageRef": "ghcr.io/willitmod/5tratmux-app:0.9.83-umbrel@sha256:" + "1" * 64,
            "uiSource": ui.UI_SOURCE, "staticFiles": {name: "2" * 64 for name in ui.OVERLAY_PATHS}}
        config = {"architecture": "arm64", "os": "linux", "config": {
            "Env": ["APP_VERSION=0.9.82", "APP_CHANNEL=MAIN"], "Labels": {"org.opencontainers.image.version": "0.9.82"},
            "User": "1000:1000", "Entrypoint": ["/app/mux"], "ExposedPorts": {"21222/tcp": {}}},
            "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "3" * 64]},
            "history": [{"created_by": "synthetic qualified parent"}]}
        base_config = retain("base-config.json", config)
        newer = copy.deepcopy(config)
        newer["config"]["Env"][0] = "APP_VERSION=0.9.83"
        newer["config"]["Labels"].update({"org.opencontainers.image.version": "0.9.83", ui.CONFIG_LABEL: ui.UI_SOURCE["sourceRevision"]})
        newer["rootfs"]["diff_ids"].append("sha256:" + "4" * 64)
        newer["history"].append({"created_by": "synthetic two-file overlay"})
        new_config = retain("config.json", newer)
        layer = {"mediaType": "application/vnd.oci.image.layer.v1.tar", "digest": "sha256:" + "5" * 64, "size": 10}
        base = {"config": {"digest": "sha256:" + base_config["sha256"]}, "layers": [layer]}
        base_manifest = retain("base-manifest.json", base)
        current = copy.deepcopy(base)
        current["config"]["digest"] = "sha256:" + new_config["sha256"]
        current["layers"][0]["mediaType"] = "application/vnd.docker.image.rootfs.diff.tar"
        current["layers"].append({**layer, "digest": "sha256:" + "7" * 64})
        manifest = retain("manifest.json", current)
        old["platforms"] = {"arm64": {"manifestDigest": "sha256:" + base_manifest["sha256"], "configDigest": "sha256:" + base_config["sha256"]}}
        row["platforms"] = {"arm64": {"manifestDigest": "sha256:" + manifest["sha256"], "configDigest": "sha256:" + new_config["sha256"]}}
        evidence = {"baseManifest": base_manifest, "manifest": manifest, "baseConfiguration": base_config, "configuration": new_config}
        verification = {"platforms": {"arm64": {"baseManifestDigest": old["platforms"]["arm64"]["manifestDigest"],
            "baseConfigDigest": old["platforms"]["arm64"]["configDigest"], **row["platforms"]["arm64"],
            "overlayLayerDigest": current["layers"][-1]["digest"], **{k: True for k in ("baseLayerPrefixUnchanged",
                "baseRootfsPrefixUnchanged", "onlyTwoWebFilesChanged", "onlyVersionAndUiSourceConfigChanges",
                "userEntrypointPortsVolumesUnchanged", "overlayDiffIDVerified", "layerMediaTypeOnlyOciDockerAliasConversion")}}},
            "overlayFiles": {name: {"sha256": digest, "size": 10, "mode": "0o644", "uid": 0, "gid": 0}
                for name, digest in row["staticFiles"].items()}}
        return row, old, evidence, verification

    def test_pending_editable_record_cannot_self_authorize(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / ui.RECORD_NAME).write_text(json.dumps({"channel": "MAIN"}))
            with patch.dict(ui.ADMISSION_LOCKS, {"MAIN": None}), self.assertRaisesRegex(AssertionError, "not been independently"):
                ui.record(root)

    def test_exact_two_file_overlay_and_same_encoding_media_alias_are_accepted(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            row, old, evidence, verification = self.fixture(root)
            ui.validate_overlay(root, evidence, row, old, "arm64", verification)

    def test_rehashed_config_cannot_change_auth_ports_binary_or_runtime(self):
        for mutate in (lambda x: x["config"].update(User="0:0"),
                lambda x: x["config"].update(Entrypoint=["/app/other"]),
                lambda x: x["config"]["Env"].append("MUX_LICENSING_URL=override"),
                lambda x: x["config"]["ExposedPorts"].update({"18080/tcp": {}}),
                lambda x: x.update(architecture="amd64"),
                lambda x: x["rootfs"]["diff_ids"].__setitem__(0, "sha256:" + "0" * 64)):
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                row, old, evidence, verification = self.fixture(root)
                config = ui.referenced(root, evidence["configuration"])
                mutate(config)
                evidence["configuration"] = self.retain("config-rehashed.json", config)
                row["platforms"]["arm64"]["configDigest"] = "sha256:" + evidence["configuration"]["sha256"]
                verification["platforms"]["arm64"]["configDigest"] = row["platforms"]["arm64"]["configDigest"]
                manifest = ui.referenced(root, evidence["manifest"])
                manifest["config"]["digest"] = row["platforms"]["arm64"]["configDigest"]
                evidence["manifest"] = self.retain("manifest-rehashed.json", manifest)
                row["platforms"]["arm64"]["manifestDigest"] = "sha256:" + evidence["manifest"]["sha256"]
                verification["platforms"]["arm64"]["manifestDigest"] = row["platforms"]["arm64"]["manifestDigest"]
                with self.assertRaises(AssertionError):
                    ui.validate_overlay(root, evidence, row, old, "arm64", verification)

    def test_extra_web_or_binary_file_wrong_ownership_and_unverified_diffid_are_rejected(self):
        for mutate in (lambda x: x["overlayFiles"].update({"app/mux": {}}),
                lambda x: x["overlayFiles"]["app/static/index.html"].update(uid=1000),
                lambda x: x["overlayFiles"]["app/static/index.html"].update(mode="0o755"),
                lambda x: x["platforms"]["arm64"].update(overlayDiffIDVerified=False)):
            with self.subTest(mutation=mutate), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                row, old, evidence, verification = self.fixture(root)
                mutate(verification)
                with self.assertRaises(AssertionError):
                    ui.validate_overlay(root, evidence, row, old, "arm64", verification)

    def test_media_alias_does_not_allow_encoding_digest_or_size_changes(self):
        layer = {"mediaType": "application/vnd.oci.image.layer.v1.tar", "digest": "sha256:" + "1" * 64, "size": 10}
        self.assertNotEqual(ui.canonical_layer(layer), ui.canonical_layer({**layer, "mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip"}))
        for change in ({"digest": "sha256:" + "2" * 64}, {"size": 11}):
            self.assertNotEqual(ui.canonical_layer(layer), ui.canonical_layer({**layer, **change}))

    def test_historical_runtime_evidence_validation_is_reused_without_execution(self):
        with patch.object(ui.previous, "record", return_value={"syntheticUnitFixture": True}) as record, \
             patch.object(ui.previous, "validate_delivery") as delivery:
            self.assertTrue(ui.predecessor(ROOT)["syntheticUnitFixture"])
            record.assert_called_once_with(ROOT)
            delivery.assert_called_once_with(ROOT, {"syntheticUnitFixture": True})

    def test_package_only_allows_image_version_and_manifest_notes_changes(self):
        import shutil
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            old = ui.previous.record(ROOT)
            row = {"channel": old["channel"], "version": ui.VERSIONS[old["channel"]],
                "imageRef": "ghcr.io/willitmod/5tratmux-app:0.9.83-umbrel@sha256:" + "1" * 64}
            app = root / ui.APP
            shutil.copytree(ROOT / ui.APP, app)
            model = ui.previous.recipe.recipe_model(old["imageRef"], old["localAIImageRef"], old["channel"])
            model["services"]["server"]["image"] = row["imageRef"]
            model["services"]["server"]["environment"]["APP_VERSION"] = row["version"]
            manifest = ui.previous.recipe.manifest_model(old["channel"])
            manifest.update(version=row["version"], releaseNotes="Synthetic UI-only correction")
            (app / "umbrel-app.yml").write_text(json.dumps(manifest))
            def retain_package():
                (app / "docker-compose.yml").write_text(json.dumps(model))
                row["packageFiles"] = {ui.APP + "/" + name: {
                    "sha256": ui.sha256((app / name).read_bytes()), "mode": oct((app / name).stat().st_mode & 0o777)}
                    for name in ui.previous.recipe.FILES}
            retain_package()
            ui.validate_package(root, row, old)
            for change in (lambda x: x["services"]["local_ai"].update(mem_limit="8g"),
                    lambda x: x["services"]["server"]["volumes"].append("/var/run/docker.sock:/var/run/docker.sock")):
                model = ui.previous.recipe.recipe_model(old["imageRef"], old["localAIImageRef"], old["channel"])
                model["services"]["server"]["image"] = row["imageRef"]
                model["services"]["server"]["environment"]["APP_VERSION"] = row["version"]
                change(model)
                retain_package()
                with self.assertRaisesRegex(AssertionError, "Only the APP image"):
                    ui.validate_package(root, row, old)

    def test_newest_record_dispatches_to_own_gate(self):
        import mux_umbrel_release as central
        with tempfile.TemporaryDirectory() as temp, patch.object(ui, "validate", return_value={"syntheticUnitFixture": True}) as successor:
            root = Path(temp)
            (root / ui.RECORD_NAME).write_text("{}\n")
            self.assertTrue(central.validate(root)["syntheticUnitFixture"])
            successor.assert_called_once_with(root)
            with self.assertRaises(AssertionError):
                central.validate(root, check_baseline=True)


if __name__ == "__main__":
    unittest.main()
