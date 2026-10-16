"""Negative admission fixtures; these do not claim native delivery qualification."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import yaml

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('dgb_backend_guard',ROOT/'scripts/dgb_backend_release.py')
release=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(release)


class DgbBackendAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row=release.record(ROOT)
        cls.before=yaml.safe_load(release.baseline_bytes(ROOT,release.APP+'/docker-compose.yml'))
        cls.current=yaml.safe_load((ROOT/release.APP/'docker-compose.yml').read_text())

    def test_exact_prepared_successor_and_original_images_are_admitted(self):
        release.validate(ROOT)
        release.admit_model(self.current,self.before,self.row)
        for name,service in self.before['services'].items():
            if 'image' in service:self.assertEqual(self.current['services'][name]['image'],service['image'])
            if 'ports' in service:self.assertEqual(self.current['services'][name]['ports'],service['ports'])
        self.assertFalse(self.row['runtimeBuildChanged']);self.assertFalse(self.row['nativeUmbrelRetryQualified'])

    def test_unreviewed_aliases_external_networks_generic_consumers_and_sql_edits_are_rejected(self):
        cases=[('postgres','networks',{'default':{'aliases':['postgres']}}),('postgres','networks',{'umbrel_main_network':{'aliases':['axedgb-postgres']}}),('app','environment',{}),('init','environment',{}),('init','command',['/bin/sh','-ec','true']),('app','image','new:latest'),('postgres','volumes',[]),('miningcore','ports',['9999:3333']),('dgbd','user','0:0'),('app_proxy','environment',{})]
        for service,key,value in cases:
            with self.subTest(service=service,key=key):
                current=copy.deepcopy(self.current);current['services'][service][key]=value
                with self.assertRaises(AssertionError):release.admit_model(current,self.before,self.row)

    def test_rehashed_record_does_not_authorize_another_candidate(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);value=copy.deepcopy(self.row);value['runtimeImages']['app']='other:latest';(root/release.RECORD).write_text(json.dumps(value))
            with self.assertRaisesRegex(AssertionError,'Unreviewed'):release.record(root)

    def test_current_whole_catalogue_baseline_check_is_explicit(self):
        with patch.object(release,'validate_package',return_value=self.row),patch.object(release,'validate_baseline')as baseline:
            release.validate(ROOT);baseline.assert_not_called()
            release.validate(ROOT,check_baseline=True);baseline.assert_called_once_with(ROOT)

    def test_real_baseline_validator_detects_other_app_and_historical_record_edits(self):
        original=release.git
        for protected in ('willitmod-dev-bch/docker-compose.yml','DGB-UMBREL-AUTH-RELEASE-2026-10-16.json'):
            def changed(root,*args):
                if args[:2]==('diff','--name-only'):return (protected+'\n').encode()
                return original(root,*args)
            with self.subTest(protected=protected),patch.object(release,'git',side_effect=changed):
                with self.assertRaisesRegex(AssertionError,'Other app or historical'):release.validate_baseline(ROOT)

    def test_fixture_receipt_requires_real_outcomes_preserved_rows_and_no_invented_live_install(self):
        original=json.loads((ROOT/self.row['nativePostgresqlFixtures']['path']).read_text())
        for case in ('wrong-source','changed-data','foreign-write','failed-test','invented-live-install'):
            with self.subTest(case=case),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);proof=copy.deepcopy(original)
                if case=='wrong-source':proof['sqlBlockSHA256']='0'*64
                elif case=='changed-data':proof['cases'][1]['afterSHA256']='0'*64
                elif case=='foreign-write':proof['foreignSourceWriteStatements']=1
                elif case=='failed-test':proof['cases'][0]['exitCode']=1
                else:proof['nativeUmbrelRetryQualified']=True
                path=root/self.row['nativePostgresqlFixtures']['path'];path.parent.mkdir();raw=(json.dumps(proof)+'\n').encode();path.write_bytes(raw)
                row=copy.deepcopy(self.row);row['nativePostgresqlFixtures']['sha256']=release.sha(raw)
                with self.assertRaises(AssertionError):release.validate_native_fixtures(root,row)


if __name__=='__main__':unittest.main()
