"""Synthetic admission checks are unit fixtures, never delivery qualification."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dgb_release_unit', ROOT / 'scripts/dgb_umbrel_release.py')
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


class DgbUmbrelReleaseTests(unittest.TestCase):
    def setUp(self):
        self.row = {'imageRef': 'ghcr.io/willitmod/axedgb-app:0.9.182-umbrel-authfix.1@sha256:' + '1'*64}
        self.before = release.predecessor(ROOT, 'docker-compose.yml')

    def test_pending_or_rehashed_editable_record_is_not_admission(self):
        if release.RECORD_SHA256 is None:
            with self.assertRaisesRegex(AssertionError, 'pending'):release.record()
        else:
            release.validate()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            value = json.loads((ROOT / release.RECORD).read_text());value['imageRef'] = self.row['imageRef'];value['status'] = 'qualified'
            (root / release.RECORD).write_text(json.dumps(value))
            with self.assertRaises(AssertionError):release.record(root)

    def test_exact_app_only_model_is_admitted_without_retagging_other_images(self):
        current = release.model(self.before, self.row)
        self.assertEqual(release.admit_model(current, self.row), self.before)
        self.assertEqual(current['services']['init']['image'], self.before['services']['init']['image'])
        self.assertEqual(current['services']['dgbd']['image'], self.before['services']['dgbd']['image'])

    def test_init_core_pool_postgres_and_permission_helpers_are_byte_model_preserved(self):
        for service in ('init', 'dgbd', 'miningcore', 'postgres', 'init_permissions', 'perm_watchdog'):
            for key, value in (('image', 'changed:latest'), ('command', []), ('volumes', []), ('environment', {}), ('stop_grace_period', '1s')):
                current = release.model(self.before, self.row);current['services'][service][key] = value
                with self.subTest(service=service, key=key), self.assertRaises(AssertionError):release.admit_model(current, self.row)

    def test_ports_auth_payout_mounts_and_app_runtime_settings_cannot_change(self):
        for service, key, value in [('app_proxy','environment',{}), ('app','ports',['9999:3000']),
                ('app','environment',{}), ('app','volumes',[]), ('app','user','0:0'), ('app','privileged',True),
                ('app','restart','no'), ('app','depends_on',[]), ('miningcore','ports',['9999:3333'])]:
            current=release.model(self.before,self.row);current['services'][service][key]=value
            with self.subTest(service=service,key=key), self.assertRaises(AssertionError):release.admit_model(current,self.row)

    def test_only_exact_accepted_app_image_not_another_tag_is_admitted(self):
        for value in ('ghcr.io/willitmod/axedgb-app:0.9.181', 'ghcr.io/willitmod/axedgb-app:0.9.189-dev', 'moving:latest'):
            current=release.model(self.before,self.row);current['services']['app']['image']=value
            with self.subTest(image=value), self.assertRaises(AssertionError):release.admit_model(current,self.row)

    def test_initial_whole_catalogue_invariance_is_explicit_not_permanent(self):
        with patch.object(release,'record',return_value=self.row),patch.object(release,'validate_package'),patch.object(release,'validate_publication'),patch.object(release,'validate_baseline')as baseline:
            release.validate();baseline.assert_not_called()
            release.validate(check_baseline=True);baseline.assert_called_once_with(ROOT)

    def test_image_receipt_requires_both_arches_protected_sources_and_honest_scope(self):
        row={**self.row,'version':release.VERSION,'sourceRevision':'2'*40,'sourceTree':'3'*40,
             'platforms':{a:{'manifestDigest':'sha256:'+'4'*64,'configDigest':'sha256:'+'5'*64} for a in ('amd64','arm64')}}
        platform={'manifestDigest':'sha256:'+'4'*64,'configDigest':'sha256:'+'5'*64,'protectedExecutableSHA256':'6'*64,
            'nativeStartupVerified':True,'noApplicationPythonSources':True,'noSourceMaps':True,'allDistributedLayersAudited':True,'httpVersion':release.VERSION}
        original={'schemaVersion':1,'result':'PASS',**{k:row[k] for k in ('version','sourceRevision','sourceTree','imageRef')},
            'anonymousIndexAndBothPlatformsVerified':True,'platforms':{a:copy.deepcopy(platform)for a in ('amd64','arm64')},
            'strictBashAuthRegressionVerified':True,'nativeUmbrelAppManagerInstallQualified':False,'physicalMiningQualified':False,
            'scope':('Native AMD64/ARM64 compiled app runtime and public immutable images verified. '
                'The guarded auth exports are exercised under strict Bash, including the exact legacy MAIN failure. '
                'Native Umbrel app-manager installation follows catalogue publication; full chain sync and physical mining are not qualified.')}
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);path=root/release.PUBLICATION;path.parent.mkdir()
            for case in (None,'missing-arch','source','maps','wrong-version','anonymous','invented-native-install','invented-mining'):
                proof=copy.deepcopy(original)
                if case=='missing-arch':del proof['platforms']['arm64']
                elif case in ('source','maps','wrong-version'):
                    field={'source':'noApplicationPythonSources','maps':'noSourceMaps','wrong-version':'httpVersion'}[case]
                    proof['platforms']['arm64'][field]='0.9.189-dev' if case=='wrong-version' else False
                elif case=='anonymous':proof['anonymousIndexAndBothPlatformsVerified']=False
                elif case=='invented-native-install':proof['nativeUmbrelAppManagerInstallQualified']=True
                elif case=='invented-mining':proof['physicalMiningQualified']=True
                raw=(json.dumps(proof)+'\n').encode();path.write_bytes(raw);row['publication']={'path':release.PUBLICATION,'sha256':release.sha(raw)}
                with self.subTest(case=case):
                    if case is None:release.validate_publication(root,row)
                    else:
                        with self.assertRaises(AssertionError):release.validate_publication(root,row)


if __name__ == '__main__':unittest.main()
