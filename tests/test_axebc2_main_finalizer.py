import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/finalize-axebc2-0.1.10-main.sh"
COMPOSE = ROOT / "willitmod-dev-bc2/docker-compose.yml"
APP_DIGEST = "sha256:" + "a" * 64
CORE_DIGEST = "sha256:" + "b" * 64


class AxeBC2MainFinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axebc2-finalizer-")
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "willitmod-dev-bc2").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / SCRIPT.name)
        shutil.copy2(COMPOSE, self.root / "willitmod-dev-bc2/docker-compose.yml")
        self.original = (self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes()
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text(json.dumps({
            "schema": 1,
            "result": "passed",
            "app_image": "ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.10-candidate.6e4ef58218e8",
            "app_digest": APP_DIGEST,
            "core_image": "ghcr.io/willitmod/bitcoinii-core:31.1.0-rc.cdf44542dde2",
            "core_digest": CORE_DIGEST,
            "core_source_revision": "cdf44542dde255648008249d187fafc15f3a2f09",
            "core_candidate_run": 33675068951,
            "app_version": "0.1.10-dev",
            "source_revision": "6e4ef58218e8cd5a4d1113196f9872a7f501f52e",
            "tested_on": "10.10.10.235",
            "tested_at": "2026-09-02T20:00:00Z",
            "acceptance": {
                "observed_at": "2026-09-02T20:00:00Z", "core_version": 310100,
                "migration_required_marker_absent": True, "migration_complete_marker_valid": True,
                "checkpoint_height": 57752, "checkpoint_hash": "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576",
                "chainwork": "0000000000000000000000000000000000000000000000959028194ff1139272",
                "ibd": False, "verification_progress": 1.0, "blocks": 60000, "headers": 60000,
                "best_block_hash": "f" * 64, "explorer_common_height": 60000, "explorer_common_hash": "f" * 64,
                "outbound_core31_peers": 3, "verifychain_level": 4, "verifychain_passed": True,
                "payout_configured": True, "payout_preserved": True, "pool_stratum_result": "passed",
                "app_ui_privacy_passed": True, "telemetry_disabled": True,
                "app_rollback_rejected": True, "os_rollback_rejected": True,
            },
        }), encoding="utf-8")
        self.log = self.root / "docker.log"
        self.fake_docker = self.root / "docker"
        self.fake_docker.write_text("""#!/bin/sh
set -eu
printf '%s\\n' "$*" >>"$FAKE_DOCKER_LOG"
config="$2"
[ "$1" = --config ] && [ -f "$config/config.json" ]
[ "$(cat "$config/config.json")" = '{"auths":{}}' ]
shift 2
if [ "$1 $2" = 'buildx imagetools' ]; then
  case "$4" in
    ghcr.io/willitmod/axebc2-app:0.1.10) printf 'Name: x\\nDigest: %s\\n' "$APP_DIGEST" ;;
    ghcr.io/willitmod/bitcoinii-core:31.1.0) printf 'Name: x\\nDigest: %s\\n' "$CORE_DIGEST" ;;
    *) exit 2 ;;
  esac
elif [ "$1 $2" = 'manifest inspect' ]; then
  printf '%s\\n' '{"manifests":[{"platform":{"os":"linux","architecture":"amd64"}},{"platform":{"os":"linux","architecture":"arm64"}}]}'
elif [ "$1" = pull ]; then
  exit 0
else
  exit 3
fi
""", encoding="utf-8")
        self.fake_docker.chmod(0o755)
        self.curl_log = self.root / "curl.log"
        self.fake_curl = self.root / "curl"
        self.fake_curl.write_text("""#!/bin/sh
set -eu
printf '%s\\n' "$*" >>"$FAKE_CURL_LOG"
for arg in "$@"; do url="$arg"; done
case "$url" in
 *'/token?'*) printf '%s\\n' '{"token":"anonymous-test-token"}' ;;
 *)
  case "${CURL_DIGEST_MODE:-correct}" in
   correct) case "$url" in *axebc2-app*) digest="$APP_DIGEST";; *) digest="$CORE_DIGEST";; esac ;;
   wrong) digest="sha256:$(printf '%064d' 0)" ;;
   missing) printf 'HTTP/2 200\\r\\n\\r\\n'; exit 0 ;;
   malformed) digest='sha256:not-a-digest' ;;
  esac
  printf 'HTTP/2 200\\r\\ndocker-content-digest: %s\\r\\n\\r\\n' "$digest"
 ;;
esac
""", encoding="utf-8")
        self.fake_curl.chmod(0o755)

    def tearDown(self):
        self.temp.cleanup()

    def run_finalizer(self, curl_mode="correct"):
        env = os.environ.copy()
        env.update({
            "DOCKER_BIN": str(self.fake_docker),
            "CURL_BIN": str(self.fake_curl),
            "FAKE_CURL_LOG": str(self.curl_log),
            "CURL_DIGEST_MODE": curl_mode,
            "FAKE_DOCKER_LOG": str(self.log),
            "APP_DIGEST": APP_DIGEST,
            "CORE_DIGEST": CORE_DIGEST,
        })
        return subprocess.run(
            [str(self.root / "scripts" / SCRIPT.name), APP_DIGEST, CORE_DIGEST, str(self.evidence)],
            text=True, capture_output=True, env=env, check=False,
        )

    def test_exact_dev_evidence_and_anonymous_multiarch_checks_then_finalize(self):
        result = self.run_finalizer()
        self.assertEqual(result.returncode, 0, result.stderr)
        compose = (self.root / "willitmod-dev-bc2/docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("_DIGEST_REQUIRED", compose)
        self.assertEqual(compose.count("ghcr.io/willitmod/bitcoinii-core:31.1.0@" + CORE_DIGEST), 2)
        self.assertIn("ghcr.io/willitmod/axebc2-app:0.1.10@" + APP_DIGEST, compose)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("--platform linux/amd64"), 2)
        self.assertEqual(calls.count("--platform linux/arm64"), 2)
        self.assertNotIn("-dev", calls)
        self.assertNotIn("buildx", calls)
        self.assertTrue(all("--config" in line for line in calls.splitlines()))

    def test_bad_registry_digest_headers_fail_without_docker_or_mutation(self):
        for mode in ("wrong", "missing", "malformed"):
            if self.log.exists(): self.log.unlink()
            result = self.run_finalizer(curl_mode=mode)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())
            self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)

    def test_mismatched_dev_digest_fails_before_registry_or_compose_mutation(self):
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        doc["core_digest"] = "sha256:" + "d" * 64
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_finalizer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)

    def test_wrong_core_source_revision_fails_before_registry_or_compose_mutation(self):
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        doc["core_source_revision"] = "d" * 40
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_finalizer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)

    def test_wrong_app_candidate_ref_fails_before_registry_or_compose_mutation(self):
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        doc["app_image"] = "ghcr.io/willitmod/axebc2-app:0.1.10-dev"
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_finalizer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)

    def test_wrong_app_source_revision_fails_before_registry_or_compose_mutation(self):
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        doc["source_revision"] = "e" * 40
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_finalizer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)

    def test_incomplete_structured_acceptance_fails_before_registry_or_mutation(self):
        doc = json.loads(self.evidence.read_text(encoding="utf-8"))
        doc["acceptance"]["outbound_core31_peers"] = 2
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        result = self.run_finalizer()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)

    def test_wrong_core_versions_and_progress_fail_before_registry_or_mutation(self):
        baseline = json.loads(self.evidence.read_text(encoding="utf-8"))
        for field, value in (("core_version", 310000), ("core_version", 320000), ("verification_progress", 0.999998)):
            doc = json.loads(json.dumps(baseline))
            doc["acceptance"][field] = value
            self.evidence.write_text(json.dumps(doc), encoding="utf-8")
            result = self.run_finalizer()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())
            self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
