"""The MAIN DigiByte Core release changes only the node image (9.26.5 to 9.26.6)."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dgb_core_release_unit', ROOT / 'scripts/dgb_core_release.py')
core = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(core)


class DgbCoreReleaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = core.record(ROOT)
        cls.raw = (ROOT / core.COMPOSE).read_bytes()
        cls.current = yaml.safe_load(cls.raw)
        cls.before = yaml.safe_load(core.baseline_bytes(ROOT, core.COMPOSE))

    def test_exact_core_only_package_and_history_are_admitted(self):
        core.validate(ROOT)
        self.assertEqual(core.previous_compose_bytes(self.raw, ROOT), core.baseline_bytes(ROOT, core.COMPOSE))
        self.assertEqual(core.previous_model(self.current, ROOT), self.before)
        self.assertEqual(self.current['services']['dgbd']['image'], core.NEW_CORE)
        self.assertEqual(self.current['services']['app']['environment']['DGB_IMAGE'], core.NEW_CORE)
        for name, service in self.before['services'].items():
            if name != 'dgbd':
                self.assertEqual(self.current['services'][name].get('image'), service.get('image'))
        manifest = yaml.safe_load((ROOT / core.MANIFEST).read_text())
        self.assertEqual(manifest['version'], '0.9.183')
        for value in ('9.26.6', '24,490,000', 'Only the node image changes', 'no reindex'):
            self.assertIn(value, manifest['releaseNotes'])

    def test_supervisor_and_runtime_settings_are_unchanged(self):
        evidence = self.row['imageEvidence']
        self.assertEqual(evidence['supervisorSHA256'], evidence['previousSupervisorSHA256'])
        node = self.current['services']['dgbd']
        self.assertEqual(node['stop_grace_period'], '15m30s')
        self.assertEqual(node['user'], '1000:1000')
        self.assertEqual(node['entrypoint'], ['/bin/sh', '/dgb-entrypoint.sh'])

    def test_other_changes_are_rejected(self):
        dev2 = 'ghcr.io/willitmod/axedgb-core:9.26.6-dev.2@sha256:fb46ff018e701accf6630b65c4b33a7d9d24b5fa248c31122d2daa2503677039'
        mutations = [('dgbd', 'image', dev2), ('dgbd', 'volumes', []), ('dgbd', 'stop_grace_period', '1s'),
                     ('dgbd', 'ports', ['1:1']), ('app', 'image', 'changed:latest'), ('init', 'image', 'changed:latest'),
                     ('miningcore', 'image', 'changed:latest'), ('postgres', 'image', 'changed:latest')]
        for service, field, value in mutations:
            changed = copy.deepcopy(self.current)
            changed['services'][service][field] = value
            with self.subTest(service=service, field=field), self.assertRaises(AssertionError):
                core.previous_model(changed, ROOT)
        changed = copy.deepcopy(self.current)
        changed['services']['app']['environment']['DGB_IMAGE'] = core.OLD_CORE
        with self.assertRaises(AssertionError):
            core.previous_model(changed, ROOT)
        with self.assertRaises(AssertionError):
            core.previous_compose_bytes(self.raw + b'\n', ROOT)

    def test_unreviewed_record_is_not_admission(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / core.RECORD
            path.parent.mkdir()
            value = json.loads((ROOT / core.RECORD).read_text())
            value['coreImage'] = value['previousCoreImage']
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(AssertionError, 'Unreviewed'):
                core.record(root)

    def test_public_record_contains_no_host_evidence(self):
        raw = (ROOT / core.RECORD).read_text()
        for private in ('/Users/', '/home/forge', '10.10.10.', 'PAYOUT_ADDRESS', 'APP_PASSWORD'):
            self.assertNotIn(private, raw)


if __name__ == '__main__':
    unittest.main()
