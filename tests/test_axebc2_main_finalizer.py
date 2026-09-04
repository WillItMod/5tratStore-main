import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/finalize-axebc2-0.1.11-main.sh"
COMPOSE = ROOT / "willitmod-dev-bc2/docker-compose.yml"
APP_DIGEST = "sha256:23a7962e223da5549eba52697c6f4cfa16ab74cba935c68c48148a4c515302b4"
CORE_DIGEST = "sha256:8875917ece57668fe9925d40a256ce8d429a3071511bb555d4ace1fa4370afc6"
OS_BUNDLE_SHA256 = "11a35e68ab169eb0446485992a57b33fae018a92020b7d86bbf9a005571377af"
DEV_STORE_REVISION = "249ab61506dc09c2151d39e2b210f5f18d75ff21"
DEV_COMPOSE_SHA256 = "93ceba92069947f47d650a5fb32205836fe070d83707f36912a2e0e83beb1244"
REQUIRED_TRUE_GATES = (
    "migration_required_marker_absent",
    "migration_started_marker_valid",
    "migration_complete_marker_valid",
    "verifychain_passed",
    "payout_configured",
    "payout_preserved",
    "app_ui_privacy_passed",
    "payout_validation_passed",
    "invalid_payout_rejected_without_mutation",
    "rpc_unavailable_rejected_without_mutation",
    "pending_payout_revalidation_passed",
    "main_payout_banner_hidden",
    "pool_config_directory_writable",
    "ckpool_sharelog_ownership_repaired",
    "telemetry_disabled",
    "p2p_port_unpublished",
    "natpmp_disabled",
    "post_completion_restart_passed",
    "reindex_not_repeated",
    "app_rollback_rejected",
    "os_rollback_rejected",
)


class AxeBC2MainFinalizerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="axebc2-finalizer-")
        self.root = Path(self.temp.name)
        (self.root / "scripts").mkdir()
        (self.root / "willitmod-dev-bc2").mkdir()
        shutil.copy2(SCRIPT, self.root / "scripts" / SCRIPT.name)
        fixture = COMPOSE.read_text(encoding="utf-8")
        fixture = re.sub(r"(ghcr\.io/willitmod/axebc2-app:0\.1\.11@sha256:)(?:[0-9a-f]{64}|APP_PROMOTED_DIGEST_REQUIRED)", r"\1APP_PROMOTED_DIGEST_REQUIRED", fixture)
        (self.root / "willitmod-dev-bc2/docker-compose.yml").write_text(fixture, encoding="utf-8")
        self.assertEqual(fixture.count("APP_PROMOTED_DIGEST_REQUIRED"), 1)
        self.assertEqual(fixture.count(CORE_DIGEST), 2)
        self.original = (self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes()
        self.evidence = self.root / "evidence.json"
        self.evidence.write_text(json.dumps({
            "schema": 1,
            "result": "passed",
            "app_image": "ghcr.io/willitmod/axebc2-app-umbrel-dev:0.1.11-candidate.ecf6e2c8cfd0",
            "app_digest": APP_DIGEST,
            "app_candidate_run": 33895447789,
            "core_image": "ghcr.io/willitmod/bitcoinii-core:31.1.0-rc.cdf44542dde2",
            "core_digest": CORE_DIGEST,
            "core_source_revision": "cdf44542dde255648008249d187fafc15f3a2f09",
            "core_candidate_run": 33675068951,
            "app_version": "0.1.11-dev",
            "tested_os_version": "v0.7.12-dev",
            "tested_os_bundle_sha256": OS_BUNDLE_SHA256,
            "source_revision": "ecf6e2c8cfd0e42ea53d3cc146b18cd6d4c4b563",
            "dev_store_revision": DEV_STORE_REVISION,
            "dev_compose_sha256": DEV_COMPOSE_SHA256,
            "tested_on": "10.10.10.235",
            "tested_at": "2026-09-02T20:00:00Z",
            "acceptance": {
                "observed_at": "2026-09-02T20:00:00Z", "chain": "main", "core_version": 310100,
                "migration_required_marker_absent": True, "migration_started_marker_valid": True, "migration_complete_marker_valid": True,
                "checkpoint_height": 57752, "checkpoint_hash": "000000000000000013ceffe797280c57f75a5b9f1d9e70c3503584058c322576",
                "chainwork": "0000000000000000000000000000000000000000000000959028194ff1139272",
                "ibd": False, "verification_progress": 1.0, "blocks": 60000, "headers": 60000,
                "best_block_hash": "f" * 64, "explorer_common_height": 60000, "explorer_common_hash": "f" * 64,
                "outbound_core31_peers": 3, "competing_valid_tips": 0, "verifychain_level": 4, "verifychain_passed": True,
                "payout_configured": True, "payout_preserved": True, "pool_stratum_result": "passed",
                "app_ui_privacy_passed": True, "payout_validation_passed": True,
                "invalid_payout_rejected_without_mutation": True,
                "rpc_unavailable_rejected_without_mutation": True,
                "pending_payout_revalidation_passed": True,
                "main_payout_banner_hidden": True,
                "pool_config_directory_writable": True,
                "ckpool_sharelog_ownership_repaired": True,
                "telemetry_disabled": True,
                "p2p_port_unpublished": True, "natpmp_disabled": True,
                "post_completion_restart_passed": True, "reindex_not_repeated": True,
                "app_rollback_rejected": True, "os_rollback_rejected": True,
            },
        }), encoding="utf-8")
        self.log = self.root / "docker.log"
        self.fake_docker = self.root / "docker"
        self.fake_docker.write_text("""#!/bin/sh
set -eu
printf '%s\\n' "$*" >>"$FAKE_DOCKER_LOG"
host="$2"; config="$4"
[ "$1" = --host ] && [ "$3" = --config ] && [ -n "$host" ] && [ -f "$config/config.json" ]
[ "$(cat "$config/config.json")" = '{"auths":{}}' ]
shift 4
if [ "$1 $2" = 'buildx imagetools' ]; then
  case "$4" in
    ghcr.io/willitmod/axebc2-app:0.1.11) printf 'Name: x\\nDigest: %s\\n' "$APP_DIGEST" ;;
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
            "DOCKER_HOST": "unix:///tmp/test-colima.sock",
            "CURL_BIN": str(self.fake_curl),
            "FAKE_CURL_LOG": str(self.curl_log),
            "CURL_DIGEST_MODE": curl_mode,
            "FAKE_DOCKER_LOG": str(self.log),
            "APP_DIGEST": APP_DIGEST,
            "CORE_DIGEST": CORE_DIGEST,
        })
        return subprocess.run(
            [str(self.root / "scripts" / SCRIPT.name), APP_DIGEST, str(self.evidence)],
            text=True, capture_output=True, env=env, check=False,
        )

    def test_exact_dev_evidence_and_anonymous_multiarch_checks_then_finalize(self):
        result = self.run_finalizer()
        self.assertEqual(result.returncode, 0, result.stderr)
        compose = (self.root / "willitmod-dev-bc2/docker-compose.yml").read_text(encoding="utf-8")
        self.assertNotIn("_DIGEST_REQUIRED", compose)
        self.assertEqual(compose.count("ghcr.io/willitmod/bitcoinii-core:31.1.0@" + CORE_DIGEST), 2)
        self.assertIn("ghcr.io/willitmod/axebc2-app:0.1.11@" + APP_DIGEST, compose)
        calls = self.log.read_text(encoding="utf-8")
        self.assertEqual(calls.count("--platform linux/amd64"), 2)
        self.assertEqual(calls.count("--platform linux/arm64"), 2)
        self.assertNotIn("-dev", calls)
        self.assertNotIn("buildx", calls)
        self.assertTrue(all("--host unix:///tmp/test-colima.sock --config" in line for line in calls.splitlines()))

    def test_bad_explicit_docker_host_fails_before_registry_or_mutation(self):
        env = os.environ.copy()
        env.update({"DOCKER_BIN":str(self.fake_docker),"DOCKER_HOST":"bad-host","CURL_BIN":str(self.fake_curl),"FAKE_DOCKER_LOG":str(self.log),"FAKE_CURL_LOG":str(self.curl_log),"APP_DIGEST":APP_DIGEST,"CORE_DIGEST":CORE_DIGEST})
        result=subprocess.run([str(self.root/"scripts"/SCRIPT.name),APP_DIGEST,str(self.evidence)],env=env,text=True,capture_output=True,check=False)
        self.assertNotEqual(result.returncode,0); self.assertFalse(self.log.exists()); self.assertFalse(self.curl_log.exists())
        self.assertEqual((self.root/"willitmod-dev-bc2/docker-compose.yml").read_bytes(),self.original)

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
        doc["app_image"] = "ghcr.io/willitmod/axebc2-app:0.1.11-dev"
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

    def test_dev_recipe_provenance_and_config_writability_fail_closed(self):
        baseline = json.loads(self.evidence.read_text(encoding="utf-8"))
        cases = (
            (None, "dev_store_revision", "d" * 40),
            (None, "dev_store_revision", None),
            (None, "dev_compose_sha256", "e" * 64),
            (None, "dev_compose_sha256", None),
        )
        for section, field, value in cases:
            doc = json.loads(json.dumps(baseline))
            target = doc if section is None else doc[section]
            if value is None:
                target.pop(field)
            else:
                target[field] = value
            self.evidence.write_text(json.dumps(doc), encoding="utf-8")
            result = self.run_finalizer()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.curl_log.exists())
            self.assertFalse(self.log.exists())
            self.assertEqual(
                (self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(),
                self.original,
            )

    def test_every_boolean_acceptance_gate_is_required_true(self):
        baseline = json.loads(self.evidence.read_text(encoding="utf-8"))
        for field in REQUIRED_TRUE_GATES:
            for remove in (False, True):
                doc = json.loads(json.dumps(baseline))
                if remove:
                    doc["acceptance"].pop(field)
                else:
                    doc["acceptance"][field] = False
                self.evidence.write_text(json.dumps(doc), encoding="utf-8")
                result = self.run_finalizer()
                self.assertNotEqual(result.returncode, 0, field)
                self.assertFalse(self.curl_log.exists(), field)
                self.assertFalse(self.log.exists(), field)
                self.assertEqual(
                    (self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(),
                    self.original,
                    field,
                )

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

    def test_network_restart_and_os_evidence_fail_closed(self):
        baseline = json.loads(self.evidence.read_text(encoding="utf-8"))
        cases = (("chain", "test"), ("migration_started_marker_valid", False),
                 ("competing_valid_tips", 1), ("p2p_port_unpublished", False),
                 ("natpmp_disabled", False), ("post_completion_restart_passed", False),
                 ("reindex_not_repeated", False))
        for field, value in cases:
            doc = json.loads(json.dumps(baseline)); doc["acceptance"][field] = value
            self.evidence.write_text(json.dumps(doc), encoding="utf-8")
            result = self.run_finalizer(); self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.log.exists())
        doc = json.loads(json.dumps(baseline)); doc["tested_os_version"] = "v0.7.11-dev"
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        self.assertNotEqual(self.run_finalizer().returncode, 0); self.assertFalse(self.log.exists())
        doc = json.loads(json.dumps(baseline)); doc["tested_os_bundle_sha256"] = OS_BUNDLE_SHA256[:-1] + "e"
        self.evidence.write_text(json.dumps(doc), encoding="utf-8")
        self.assertNotEqual(self.run_finalizer().returncode, 0); self.assertFalse(self.log.exists())
        self.assertEqual((self.root / "willitmod-dev-bc2/docker-compose.yml").read_bytes(), self.original)


if __name__ == "__main__":
    unittest.main()
