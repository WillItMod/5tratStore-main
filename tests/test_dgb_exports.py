"""Exercise sourced AxeDGB auth exports under Umbrel's strict Bash caller."""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / 'willitmod-dev-dgb/exports.sh'
BASELINE = '119e24b66a9badb820911d2e0ef384b1a118c537'
SCRIPT = r'''
if [[ "$TEST_STRICT" == yes ]]; then
  set -euo pipefail
else
  set +e +u
  set +o pipefail
fi
docker() {
  [[ "$1" == inspect ]] || return 89
  printf '%s\n' "${!#}" >> "$TEST_PROBES"
  [[ "${!#}" == "$TEST_AUTH_CONTAINER" ]] || return 1
  printf '%s\n' 'OTHER=value' "JWT_SECRET=$TEST_AUTH_SECRET"
}
before_options="$-"
before_pipefail="$(set -o | awk '$1 == "pipefail" {print $2}')"
source "$1"
[[ "$before_options" == "$-" ]] || exit 91
[[ "$before_pipefail" == "$(set -o | awk '$1 == "pipefail" {print $2}')" ]] || exit 92
printf '%s\n' "${JWT_SECRET-unset}"
'''


class DgbExportsTests(unittest.TestCase):
    def run_exports(self, *, container='none', supplied=None, strict=True, source=EXPORTS):
        import tempfile
        with tempfile.TemporaryDirectory() as temp:
            probes = Path(temp) / 'probes'
            env = dict(os.environ, TEST_STRICT='yes' if strict else 'no',
                       TEST_PROBES=str(probes), TEST_AUTH_CONTAINER=container,
                       TEST_AUTH_SECRET='real-fixture-secret=with+characters')
            env.pop('JWT_SECRET', None)
            if supplied is not None:
                env['JWT_SECRET'] = supplied
            result = subprocess.run(['/bin/bash', '-c', SCRIPT, 'dgb-exports-test', str(source)],
                                    env=env, text=True, capture_output=True)
            return result, probes.read_text().splitlines() if probes.exists() else []

    def test_umbrel2_without_legacy_auth_does_not_abort_or_invent_credentials(self):
        result, probes = self.run_exports()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'unset\n')
        self.assertEqual(probes, ['auth', 'umbrel-auth', 'umbrel_auth'])

    def test_real_legacy_secret_is_found_with_each_supported_container_name(self):
        for container in ['auth', 'umbrel-auth', 'umbrel_auth']:
            with self.subTest(container=container):
                result, probes = self.run_exports(container=container)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, 'real-fixture-secret=with+characters\n')
                self.assertEqual(probes[-1], container)

    def test_existing_secret_is_preserved_without_any_docker_probe(self):
        result, probes = self.run_exports(supplied='existing-fixture-secret')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'existing-fixture-secret\n')
        self.assertEqual(probes, [])

    def test_non_strict_callers_keep_their_shell_options(self):
        result, _ = self.run_exports(strict=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'unset\n')

    def test_absent_docker_is_an_optional_probe(self):
        env = dict(os.environ, PATH='/nonexistent')
        env.pop('JWT_SECRET', None)
        script = 'set -euo pipefail; before="$-"; source "$1"; [[ "$before" == "$-" ]]; printf "%s" "${JWT_SECRET-unset}"'
        result = subprocess.run(['/bin/bash', '-c', script, 'dgb-no-docker', str(EXPORTS)],
                                env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'unset')

    def test_previous_published_main_reproduces_exit_one_without_auth(self):
        import tempfile
        previous = subprocess.check_output(['git', 'show', f'{BASELINE}:willitmod-dev-dgb/exports.sh'], cwd=ROOT)
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'exports.sh'
            source.write_bytes(previous)
            result, _ = self.run_exports(source=source)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, '')


if __name__ == '__main__':
    unittest.main()
