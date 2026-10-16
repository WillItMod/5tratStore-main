"""Run the actual extracted Compose SQL initializer against controlled client results."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / 'willitmod-dev-dgb'

FAKE_PSQL = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
with open(os.environ['DB_CALL_LOG'],'a') as f: f.write(json.dumps(args)+'\n')
case=os.environ['DB_CASE']
if '-c' not in args:
    sys.stdin.read()
    sys.exit(0)
sql=args[args.index('-c')+1]
if sql.startswith('SELECT'):
    if case=='auth-failure' or (case=='second-query-failure' and 'information_schema.tables' in sql) or (case=='type-query-failure' and 'SELECT data_type' in sql):
        print('controlled query failure',file=sys.stderr);sys.exit(2)
    if 'pg_catalog.pg_class' in sql: print('bad' if case=='invalid-count' else 0 if case=='empty' else 16)
    elif 'information_schema.tables' in sql: print(0 if case=='empty' else 7 if case=='partial' else 8)
    elif 'actualdifficulty' in sql: print(0 if case=='column-write-failure' else 1)
    elif "column_name='worker'" in sql: print(1)
    elif 'SELECT data_type' in sql: print('jsonb' if case=='unsupported-type' else 'integer' if case=='type-write-failure' else 'text')
    elif 'COUNT(*) FROM poolstats' in sql: print(0 if case=='empty' else 1)
    else: print('unhandled query',file=sys.stderr);sys.exit(90)
elif case in ('column-write-failure','type-write-failure'):
    print('controlled write failure',file=sys.stderr);sys.exit(2)
'''


class DgbDatabaseSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose=yaml.safe_load((APP/'docker-compose.yml').read_text())
        cls.command=cls.compose['services']['init']['command'][-1].replace('$$','$')
        begin=cls.command.index('# DGB_DATABASE_SETUP_BEGIN')
        end=cls.command.index('# DGB_DATABASE_SETUP_END')+len('# DGB_DATABASE_SETUP_END')
        cls.sql=cls.command[begin:end]
        status_start=cls.command.index('init_status() {')
        status_end=cls.command.index('        for tool in') if '        for tool in' in cls.command else cls.command.index('for tool in')
        cls.status=cls.command[status_start:status_end]

    def run_case(self, case):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);data=root/'data';(data/'ui/state').mkdir(parents=True);(data/'templates').mkdir()
            shutil.copyfile(APP/'data/templates/miningcore-createdb.sql',data/'templates/miningcore-createdb.sql')
            bin_path=root/'bin';bin_path.mkdir()
            python=shutil.which('python3')
            (bin_path/'psql').write_text(FAKE_PSQL.replace('#!/usr/bin/env python3','#!'+python))
            (bin_path/'pg_isready').write_text('#!/bin/sh\nexit '+('1' if case=='readiness-timeout' else '0')+'\n')
            (bin_path/'sleep').write_text('#!/bin/sh\nexit 0\n')
            for path in bin_path.iterdir():path.chmod(0o755)
            program=('set -eu\ninit_phase="Preparing Miningcore database"\n'+self.status+'\n'+self.sql+'\ninit_phase="Setup complete"\ninit_status ready\n').replace('/data/',str(data)+'/')
            result=subprocess.run(['sh','-ec',program],env={**os.environ,'PATH':str(bin_path)+':'+os.environ['PATH'],'DB_HOST':'axedgb-postgres','DB_USER':'miningcore','DB_PASSWORD':'fixture-private','DB_NAME':'miningcore','DB_CASE':case,'DB_CALL_LOG':str(root/'calls')},text=True,capture_output=True)
            calls=[json.loads(line)for line in (root/'calls').read_text().splitlines()] if (root/'calls').exists() else []
            state=json.loads((data/'ui/state/init_status.json').read_text())
            writes=[a for a in calls if '-c' not in a or not a[a.index('-c')+1].startswith('SELECT')]
            return result,calls,writes,state

    def test_query_failures_invalid_output_partial_schema_and_unsupported_types_stop_without_writes(self):
        for case in ('auth-failure','second-query-failure','invalid-count','partial','type-query-failure','unsupported-type'):
            with self.subTest(case=case):
                result,calls,writes,state=self.run_case(case)
                self.assertNotEqual(result.returncode,0);self.assertEqual(writes,[]);self.assertEqual(state['state'],'failed')
                self.assertIn('ERROR',result.stderr)

    def test_complete_existing_schema_is_read_only_and_ready(self):
        result,calls,writes,state=self.run_case('complete')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(writes,[]);self.assertEqual(state['state'],'ready')
        self.assertGreaterEqual(len(calls),13)

    def test_only_verified_empty_schema_imports_in_one_transaction(self):
        result,calls,writes,state=self.run_case('empty')
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(state['state'],'ready')
        imports=[a for a in writes if '-c' not in a]
        self.assertEqual(len(imports),1);self.assertIn('--single-transaction',imports[0])
        self.assertEqual(len(writes),2)
        self.assertIn('INSERT INTO poolstats',writes[1][writes[1].index('-c')+1])

    def test_failed_migrations_stop_and_never_drop_or_rebuild_tables(self):
        for case in ('column-write-failure','type-write-failure'):
            with self.subTest(case=case):
                result,calls,writes,state=self.run_case(case)
                self.assertNotEqual(result.returncode,0);self.assertEqual(state['state'],'failed');self.assertEqual(len(writes),1)
                self.assertIn('ALTER TABLE',writes[0][writes[0].index('-c')+1])
                self.assertNotIn('DROP TABLE',json.dumps(calls))

    def test_readiness_timeout_stops_before_any_sql(self):
        result,calls,writes,state=self.run_case('readiness-timeout')
        self.assertNotEqual(result.returncode,0);self.assertEqual(calls,[]);self.assertEqual(state['state'],'failed')

    def test_all_queries_and_writes_disable_startup_files_prompting_and_continue_on_error(self):
        result,calls,writes,state=self.run_case('empty')
        self.assertEqual(result.returncode,0,result.stderr)
        for args in calls:
            self.assertIn('-X',args);self.assertIn('-w',args);self.assertIn('ON_ERROR_STOP=1',args)
        self.assertNotIn('DROP TABLE',self.sql);self.assertNotIn('|| true',self.sql)
        subprocess.run(['sh','-n'],input=self.command,text=True,check=True)

class DgbBackendConfigurationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose=yaml.safe_load((APP/'docker-compose.yml').read_text())
        cls.command=cls.compose['services']['init']['command'][-1].replace('$$','$')

    def section(self, name):
        start=self.command.index('# '+name+'_BEGIN')
        end=self.command.index('# '+name+'_END')+len('# '+name+'_END')
        return self.command[start:end]

    def test_backend_aliases_and_all_consumers_are_unique_on_private_default_network(self):
        services=self.compose['services']
        aliases={'postgres':'axedgb-postgres','dgbd':'axedgb-core','miningcore':'axedgb-miningcore'}
        for service,alias in aliases.items():
            self.assertEqual(services[service]['networks'],{'default':{'aliases':[alias]}})
        for service,key,expected in [('init','DB_HOST',aliases['postgres']),('init','DGB_RPC_HOST',aliases['dgbd']),('app','PGHOST',aliases['postgres']),('app','DGB_RPC_HOST',aliases['dgbd']),('app','MININGCORE_API_URL','http://axedgb-miningcore:4000')]:
            self.assertEqual(services[service]['environment'][key],expected)
        template=(APP/'data/templates/miningcore.json.template').read_text()
        self.assertEqual(template.count('"host": "${DGB_RPC_HOST}"'),2)
        self.assertIn('"host": "${DB_HOST}"',template)

    def run_migration(self, value, *, fail_write=False):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);config=root/'miningcore.json';original=json.dumps(value,indent=4)+'\n';config.write_text(original);config.chmod(0o600)
            tools=root/'bin';tools.mkdir();(tools/'chown').write_text('#!/bin/sh\nexit 0\n');(tools/'chown').chmod(0o755)
            if fail_write:
                jq=shutil.which('jq');(tools/'jq').write_text('#!/bin/sh\nif [ "$1" = --arg ]; then exit 4; fi\nexec '+jq+' "$@"\n');(tools/'jq').chmod(0o755)
            result=subprocess.run(['sh','-ec','miningcore_conf="$CONFIG_FILE"\n'+self.section('DGB_BACKEND_HOST_MIGRATION')],env={**os.environ,'PATH':str(tools)+':'+os.environ['PATH'],'CONFIG_FILE':str(config),'DB_HOST':'axedgb-postgres','DGB_RPC_HOST':'axedgb-core'},text=True,capture_output=True)
            first=config.read_text();mode=config.stat().st_mode&0o777
            if result.returncode==0:
                repeated=subprocess.run(['sh','-ec','miningcore_conf="$CONFIG_FILE"\n'+self.section('DGB_BACKEND_HOST_MIGRATION')],env={**os.environ,'PATH':str(tools)+':'+os.environ['PATH'],'CONFIG_FILE':str(config),'DB_HOST':'axedgb-postgres','DGB_RPC_HOST':'axedgb-core'},text=True,capture_output=True)
                self.assertEqual(repeated.returncode,0,repeated.stderr);self.assertEqual(config.read_text(),first)
            return result,original,first,mode,(root/'miningcore.json.hosts.tmp').exists()

    def test_generic_only_config_migration_is_atomic_idempotent_and_preserves_private_settings(self):
        value={'persistence':{'postgres':{'host':'postgres','password':'fixture-secret','database':'custom-dgb'}},'pools':[{'id':'dgb-sha256-1','address':'user-payout','ports':{'3333':{'difficulty':8192}},'daemons':[{'host':'dgbd','user':'custom-rpc','password':'fixture-rpc','port':14022},{'host':'remote.example','port':5001}]},{'id':'custom','daemons':[{'host':'custom-core'}]}]}
        result,original,updated,mode,leftover=self.run_migration(value)
        self.assertEqual(result.returncode,0,result.stderr);expected=json.loads(original);expected['persistence']['postgres']['host']='axedgb-postgres';expected['pools'][0]['daemons'][0]['host']='axedgb-core'
        self.assertEqual(json.loads(updated),expected);self.assertEqual(mode,0o600);self.assertFalse(leftover)

    def test_explicit_custom_destinations_are_byte_preserved(self):
        value={'persistence':{'postgres':{'host':'custom-db'}},'pools':[{'daemons':[{'host':'custom-core'}]}]}
        result,original,updated,mode,leftover=self.run_migration(value)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(updated,original);self.assertEqual(mode,0o600);self.assertFalse(leftover)

    def test_failed_config_transform_keeps_original_bytes_and_removes_temporary_file(self):
        value={'persistence':{'postgres':{'host':'postgres'}},'pools':[{'daemons':[{'host':'dgbd'}]}]}
        result,original,updated,mode,leftover=self.run_migration(value,fail_write=True)
        self.assertNotEqual(result.returncode,0);self.assertEqual(updated,original);self.assertEqual(mode,0o600);self.assertFalse(leftover)

    def test_rpc_capacity_preserves_mainnet_values_and_inserts_missing_keys_before_sections(self):
        cases=[('rpcworkqueue=512\nrpcthreads=8\n[test]\nrpcworkqueue=17\nrpcthreads=3\n','512','8',True),('rpcworkqueue=512\n[test]\nrpcthreads=3\n','512','32',False),('[test]\nrpcworkqueue=17\nrpcthreads=3\n','1024','32',False)]
        for original,queue,threads,unchanged in cases:
            with self.subTest(original=original),tempfile.TemporaryDirectory()as directory:
                root=Path(directory);config=root/'digibyte.conf';config.write_text(original);config.chmod(0o600)
                command=self.section('DGB_RPC_CAPACITY').replace('/data/node/',str(root)+'/')
                result=subprocess.run(['sh','-ec',command],text=True,capture_output=True)
                self.assertEqual(result.returncode,0,result.stderr);updated=config.read_text();main=updated.split('[test]')[0]
                self.assertIn('rpcworkqueue='+queue+'\n',main);self.assertIn('rpcthreads='+threads+'\n',main)
                self.assertEqual(updated.split('[test]')[1],original.split('[test]')[1]);self.assertEqual(config.stat().st_mode&0o777,0o600)
                if unchanged:self.assertEqual(updated,original)
        restore=self.command.index('if [ -f "$conf" ]; then chown 1000:1000 "$conf"; fi')
        self.assertGreater(restore,self.command.index('conf.txindex.tmp'))


if __name__=='__main__':unittest.main()
