"""Representative observed-ingress regressions, not native delivery qualification."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('dgb_gateway_guard', ROOT / 'scripts/dgb_gateway_release.py')
gateway = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gateway)


def observed_native2_resolver(app_host, candidates, host_dns):
    """Model only observed name admission; real gateway retry is separate.

    Source observation SHA is pinned in the closed delivery record. Native 2
    does not query network aliases in this service lookup or host DNS fallback.
    Generated container names are supplied as observations, not inferred here.
    """
    for candidate in candidates:
        if app_host in (candidate.get('service'), candidate.get('container_name'),
                        candidate.get('hostname'), candidate.get('generated_container_name')):
            return ('service', candidate['service'])
    address = host_dns.get(app_host)
    return ('host-dns', address) if address else None


def candidate(service):
    return {'service': 'app', 'container_name': 'observed-dgb_app_1',
            'generated_container_name': 'observed-dgb-app-1',
            'hostname': service.get('hostname'),
            'network_aliases': service['networks']['default']['aliases']}


class DgbGatewayHostnameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.row = gateway.record(ROOT)
        cls.before_raw = gateway.baseline_bytes(ROOT)
        cls.before = yaml.safe_load(cls.before_raw)
        cls.current_raw = (ROOT / gateway.COMPOSE).read_bytes()
        cls.current = yaml.safe_load(cls.current_raw)

    def test_exact_package_successor_and_all_historical_proofs_are_preserved(self):
        gateway.validate(ROOT, check_baseline=True)
        self.assertEqual(gateway.previous_gateway_model(self.current, ROOT), self.before)
        self.assertEqual(gateway.previous_compose_bytes(self.current_raw, ROOT), self.before_raw)
        self.assertFalse(self.row['nativeGatewayRetryQualified'])
        self.assertFalse(self.row['runtimeBuildChanged'])
        for name, service in self.before['services'].items():
            for field in ('image', 'ports', 'networks', 'volumes', 'environment'):
                self.assertEqual(self.current['services'][name].get(field), service.get(field))
        if gateway.CHANNEL == 'DEV':
            self.assertTrue(self.row['hostnameAlreadyPresent'])
            self.assertEqual(self.current_raw, self.before_raw)
        else:
            self.assertFalse(self.row['hostnameAlreadyPresent'])
            self.assertEqual(self.current_raw, self.before_raw.replace(b'  app:\n', b'  app:\n    hostname: axedgb-app\n', 1))

    def test_alias_only_native2_failure_and_declared_hostname_admission(self):
        alias_only = copy.deepcopy(self.current['services']['app'])
        alias_only.pop('hostname')
        self.assertIn('axedgb-app', alias_only['networks']['default']['aliases'])
        self.assertIsNone(observed_native2_resolver('axedgb-app', [candidate(alias_only)], {}))
        declared = candidate(self.current['services']['app'])
        self.assertEqual(observed_native2_resolver('axedgb-app', [declared], {}), ('service', 'app'))
        self.assertEqual(observed_native2_resolver('axedgb-app', [candidate(alias_only)], {'axedgb-app': '192.0.2.1'}), ('host-dns', '192.0.2.1'))

    def test_legacy17_docker_dns_alias_and_both_service_networks_are_unchanged(self):
        for network in ('default', 'umbrel_main_network'):
            self.assertIn('axedgb-app', self.before['services']['app']['networks'][network]['aliases'])
            self.assertEqual(self.current['services']['app']['networks'][network], self.before['services']['app']['networks'][network])
        # Legacy 1.7 proxy DNS can still use its existing shared-network alias.
        docker_dns = {'axedgb-app': '192.0.2.2'}
        self.assertEqual(docker_dns[self.before['services']['app_proxy']['environment']['APP_HOST']],
                         docker_dns[self.current['services']['app_proxy']['environment']['APP_HOST']])

    def test_different_hostname_proxy_target_and_other_mutations_are_rejected(self):
        mutations = [('app', 'hostname', 'other-app'), ('app', 'image', 'other:latest'),
                     ('app', 'networks', {}), ('postgres', 'hostname', 'axedgb-app'),
                     ('miningcore', 'ports', ['9999:3333']), ('init', 'command', ['/bin/sh', '-ec', 'true'])]
        for service, field, value in mutations:
            current = copy.deepcopy(self.current)
            current['services'][service][field] = value
            with self.subTest(service=service, field=field), self.assertRaises(AssertionError):
                gateway.previous_gateway_model(current, ROOT)
        current = copy.deepcopy(self.current)
        current['services']['app_proxy']['environment']['APP_HOST'] = 'other-app'
        with self.assertRaises(AssertionError):
            gateway.previous_gateway_model(current, ROOT)
        with self.assertRaises(AssertionError):
            gateway.previous_compose_bytes(self.current_raw + b'\n', ROOT)

    def test_backend_admission_still_validates_exact_prior_dns_and_sql_repair(self):
        spec = importlib.util.spec_from_file_location('dgb_old_backend_guard', ROOT / 'scripts/dgb_backend_release.py')
        backend = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(backend)
        backend.validate(ROOT)
        before = yaml.safe_load(backend.baseline_bytes(ROOT, gateway.COMPOSE))
        self.assertEqual(backend.previous_backend_model(gateway.APP, self.current, ROOT), before)

    def test_unreviewed_gateway_record_cannot_admit_a_rehashed_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / gateway.RECORD
            path.parent.mkdir()
            path.write_text('{}')
            with self.assertRaisesRegex(AssertionError, 'Unreviewed'):
                gateway.record(root)


if __name__ == '__main__':
    unittest.main()
