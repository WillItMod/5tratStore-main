"""MAIN retains its own complete reviewed baseline outside explicit release changes."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
import yaml
ROOT=Path(__file__).resolve().parents[1]

class MainRollupContractTests(unittest.TestCase):
    def test_only_reviewed_fields_change_and_every_main_baseline_is_preserved(self):
        release=json.loads((ROOT/'MAIN-NODE-ROLLUP-2026-09-28.json').read_text())
        self.assertEqual(release['baselineCommit'],'7bf351859c5a29c99fbd6bcf7ade79c3f54f39d0')
        for name,record in release['apps'].items():
            with self.subTest(app=name):
                current=yaml.safe_load((ROOT/name/'docker-compose.yml').read_text())
                original=copy.deepcopy(current)
                allowed={('services','app','image'),('services','app','stop_signal')}
                allowed.update(('services','app','environment',key) for key in ('MUX_IDENTITY_URL','APP_CHANNEL','APP_VERSION_SUFFIX','APP_VERSION','APP_RELEASE_PHASE'))
                if name=='willitmod-dev-axebch2':allowed.add(('services','init_permissions','command'))
                if name=='willitmod-dev-ppc':allowed.update({('services','init','command'),('services','pool','init')})
                if name=='willitmod-dev-powpow':allowed.add(('services','pool','image'))
                for change in record['approvedRuntimeChanges']:
                    path=change['path'];self.assertIn(tuple(path),allowed)
                    node=original
                    for key in path[:-1]:node=node[key]
                    self.assertEqual(node[path[-1]],change['after'])
                    if change['existed']:node[path[-1]]=change['before']
                    else:del node[path[-1]]
                digest=hashlib.sha256(json.dumps(original,sort_keys=True,separators=(',',':')).encode()).hexdigest()
                self.assertEqual(digest,record['baselineComposeSha256'])
                app=current['services']['app'];env=app['environment']
                self.assertEqual(env['APP_CHANNEL'],'MAIN')
                self.assertEqual(env.get('APP_VERSION_SUFFIX',''),'')
                self.assertEqual(app.get('stop_signal'),None if name=='willitmod-dev-bc2' else 'SIGINT')
                self.assertNotIn('-dev',record['version'])
                if 'APP_VERSION' in env:self.assertEqual(env['APP_VERSION'],record['version'])
                if name=='willitmod-dev-axebch2':self.assertEqual(env['APP_RELEASE_PHASE'],'STABLE')
                self.assertEqual((ROOT/name/'global-app.yml').read_bytes(),(ROOT/name/'umbrel-app.yml').read_bytes())
    def test_main_specific_network_core_and_user_choices_are_retained(self):
        document=lambda name:yaml.safe_load((ROOT/name/'docker-compose.yml').read_text())['services']
        frac=document('willitmod-dev-fracattack')
        self.assertEqual(frac['app']['ports'],['21225:3000/tcp'])
        powpow=document('willitmod-dev-powpow')
        for name in ('litecoin','dogecoin'):
            self.assertNotIn('user',powpow[name]);self.assertNotIn('-dev',powpow[name]['image'])
        bc2=document('willitmod-dev-bc2')
        self.assertIn(':31.1.0@sha256:',bc2['btc2d']['image'])
        bch2=document('willitmod-dev-axebch2')
        self.assertTrue(bch2['bch2']['image'].endswith(':0.1.33'))
        self.assertTrue(bch2['ckpool']['image'].endswith(':0.1.33'))

if __name__=='__main__':unittest.main()
