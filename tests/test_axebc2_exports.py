import os
from pathlib import Path
import subprocess
import tempfile
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "willitmod-dev-bc2/exports.sh"


class AxeBC2ExportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axebc2-exports-")
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "docker.log"
        docker = self.bin / "docker"
        docker.write_text(
            textwrap.dedent(
                """\
                #!/usr/bin/env bash
                printf '%s\n' "$*" >>"${FAKE_DOCKER_LOG}"
                container="${!#}"
                case "${FAKE_DOCKER_MODE:-missing}:$container" in
                  later:auth) exit 1 ;;
                  later:umbrel-auth)
                    printf '%s\n' 'OTHER=value' 'JWT_SECRET=discovered-real-secret'
                    ;;
                  later:umbrel_auth) exit 97 ;;
                  missing:*) exit 1 ;;
                  *) exit 98 ;;
                esac
                """
            ),
            encoding="utf-8",
        )
        docker.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_source(self, mode, supplied=None, strict=True):
        options = "set -euo pipefail" if strict else "set +e; set +u; set +o pipefail"
        script = textwrap.dedent(
            f"""\
            {options}
            before_flags="$-"
            before_pipefail="$(set -o | awk '$1 == "pipefail" {{print $2}}')"
            source "$1"
            after_flags="$-"
            after_pipefail="$(set -o | awk '$1 == "pipefail" {{print $2}}')"
            [[ "$before_flags" == "$after_flags" ]] || exit 91
            [[ "$before_pipefail" == "$after_pipefail" ]] || exit 92
            printf '%s\n' "${{JWT_SECRET+x}}" "${{JWT_SECRET-}}" "$after_pipefail"
            """
        )
        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{self.bin}:{env['PATH']}",
                "FAKE_DOCKER_LOG": str(self.log),
                "FAKE_DOCKER_MODE": mode,
            }
        )
        if supplied is None:
            env.pop("JWT_SECRET", None)
        else:
            env["JWT_SECRET"] = supplied
        return subprocess.run(
            ["bash", "-c", script, "axebc2-exports-test", str(EXPORTS)],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_missing_legacy_auth_is_safe_under_strict_caller_without_fake_secret(self):
        result = self.run_source("missing")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["", "", "on"])
        self.assertEqual(len(self.log.read_text(encoding="utf-8").splitlines()), 3)

    def test_later_legacy_candidate_supplies_real_secret(self):
        result = self.run_source("later")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["x", "discovered-real-secret", "on"])
        calls = self.log.read_text(encoding="utf-8").splitlines()
        self.assertEqual(len(calls), 2)
        self.assertTrue(calls[0].endswith(" auth"), calls)
        self.assertTrue(calls[1].endswith(" umbrel-auth"), calls)

    def test_supplied_secret_is_preserved_without_docker_probe(self):
        result = self.run_source("missing", supplied="supplied-real-secret")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["x", "supplied-real-secret", "on"])
        self.assertFalse(self.log.exists())

    def test_non_strict_caller_options_are_also_preserved(self):
        result = self.run_source("missing", strict=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["", "", "off"])


if __name__ == "__main__":
    unittest.main()
