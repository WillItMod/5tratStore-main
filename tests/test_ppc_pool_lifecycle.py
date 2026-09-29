"""PPC recipe signal regression; optional exact-image fixture has no live data.

PPC_POOL_TEST_IMAGE=sha256:<qualified local image id> python3 -m unittest
    discover -s tests -p test_ppc_pool_lifecycle.py -v

The optional fixture uses network none, no ports, no production configuration,
no persistent volume, and removes only its own random container ID afterward.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import unittest
import uuid

import yaml

ROOT=Path(__file__).resolve().parents[1]
RECIPE=ROOT/'willitmod-dev-ppc/docker-compose.yml'

class PoolRecipeTests(unittest.TestCase):
    def test_node_pool_has_init_without_changing_stop_policy_image_or_data(self):
        pool=yaml.safe_load(RECIPE.read_text())['services']['pool']
        self.assertIs(pool['init'],True)
        self.assertEqual(pool['image'],'ghcr.io/willitmod/axeppc-pool:0.2.30')
        self.assertEqual(pool['stop_grace_period'],'30s')
        self.assertNotIn('stop_signal',pool)
        self.assertNotIn('entrypoint',pool)
        self.assertNotIn('command',pool)
        self.assertEqual(pool['user'],'1000:1000')
        self.assertEqual(set(pool['depends_on']),{'ppcd','redis','init'})
        self.assertEqual(pool['volumes'],[
            '${APP_DATA_DIR}/data/pool/cps/config.json:/app/config.json:ro',
            '${APP_DATA_DIR}/data/pool/cps/pool_configs:/app/pool_configs:ro',
            '${APP_DATA_DIR}/data/pool/cps/coins/peercoin.json:/app/coins/peercoin.json:ro'])

@unittest.skipUnless(os.environ.get('PPC_POOL_TEST_IMAGE'),'Exact-image Docker fixture is an explicit integration gate')
class PoolSignalIntegrationTests(unittest.TestCase):
    def test_exact_upstream_process_stops_from_recipe_init_without_forced_kill(self):
        image=os.environ['PPC_POOL_TEST_IMAGE']
        self.assertRegex(image,r'^(sha256:[a-f0-9]{64}|[a-zA-Z0-9][a-zA-Z0-9./:_-]*@sha256:[a-f0-9]{64})$')
        pool=yaml.safe_load(RECIPE.read_text())['services']['pool']
        def run(args):return subprocess.check_output(args,text=True).strip()
        def inspect(cid):return json.loads(run(['docker','inspect',cid]))[0]
        with tempfile.TemporaryDirectory(prefix='ppc-signal-') as temporary:
            base=Path(temporary);base.chmod(0o755)
            (base/'pool_configs').mkdir();(base/'coins').mkdir()
            (base/'config.json').write_text(json.dumps({'logLevel':'debug','logColors':False,
                'defaultPoolConfigs':{},'clustering':{'enabled':False},'website':{'enabled':False},
                'profitSwitch':{'enabled':False},'cliHost':'127.0.0.1','cliPort':17117}))
            args=['docker','run','-d','--pull','never','--network','none','--read-only','--memory','256m',
                  '--memory-swap','256m','--pids-limit','32','--cpus','0.5','--name','ppc-signal-test-'+uuid.uuid4().hex[:12],
                  '--mount','type=bind,src='+str(base)+',dst=/fixture,readonly','--workdir','/fixture']
            if pool.get('init') is True:args.append('--init')
            script="require('/app/init.js'); console.log(JSON.stringify({fixtureReady:true,pid:process.pid}));"
            cid=run(args+[image,'node','-e',script])
            try:
                for _ in range(50):
                    logs=run(['docker','logs',cid])
                    if 'fixtureReady' in logs:break
                    self.assertTrue(inspect(cid)['State']['Running'],'fixture exited before ready')
                    time.sleep(.1)
                else:self.fail('fixture never ready')
                ready=json.loads(next(line for line in logs.splitlines() if 'fixtureReady' in line))
                self.assertGreater(ready['pid'],1)
                started=time.monotonic();run(['docker','kill','--signal','SIGTERM',cid])
                while time.monotonic()-started<5 and inspect(cid)['State']['Running']:time.sleep(.1)
                result=inspect(cid)
                self.assertFalse(result['State']['Running'],'Node ignored TERM and would require forced kill')
                self.assertEqual(result['State']['ExitCode'],143)
                self.assertFalse(result['State']['OOMKilled'])
                self.assertEqual(result['RestartCount'],0)
                self.assertTrue(result['HostConfig']['Init'])
            finally:
                # Failed disposable regressions still clean only their exact ID;
                # this is never evidence that a production SIGKILL is acceptable.
                if inspect(cid)['State']['Running']:run(['docker','kill','--signal','SIGKILL',cid])
                run(['docker','rm',cid])
