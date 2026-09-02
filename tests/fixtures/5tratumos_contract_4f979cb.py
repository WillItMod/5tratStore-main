"""Pinned excerpt of the 5tratumOS app-ID and rollback-policy contract.

Source: WillItMod/5tratum_Build commit
4f979cb9541622c1fdccdf43b8a885bbf845ba38. The integration test prefers a
local platform checkout and uses this fixture in isolated store CI.
"""

import json
from pathlib import Path
import re


_STORE_ID_PREFIXES = ("willitmod-dev-", "willitmod-")
_CANONICAL_STORE_APP_IDS = {"5tratsmack"}
_VERSION_RE = re.compile(
    r"^v?(?P<base>[0-9]+(?:\.[0-9]+){1,3})(?:[-+][0-9A-Za-z][0-9A-Za-z.-]*)?$"
)


class RollbackPolicyError(ValueError):
    pass


def map_store_id_to_app_id(store_id: str, channel: str) -> str:
    raw = (store_id or "").strip().lower()
    ch = (channel or "").strip().lower()
    if ch == "global" or ch.startswith("custom"):
        raw = raw.replace(" ", "-")
        raw = re.sub(r"[^a-z0-9_-]+", "", raw)
        return raw or "app"
    for prefix in _STORE_ID_PREFIXES:
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    raw = raw.replace("_", "").replace("-", "")
    if raw in _CANONICAL_STORE_APP_IDS:
        return raw
    if not raw.startswith("axe"):
        raw = f"axe{raw}"
    return raw


def _base_version(value):
    match = _VERSION_RE.fullmatch(str(value or "").strip())
    if not match:
        raise RollbackPolicyError("invalid version")
    parts = tuple(int(part) for part in match.group("base").split("."))
    return parts + (0,) * (4 - len(parts))


def check_rollback_policy(policy_path: Path, app_id: str, target_version: str) -> dict:
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    if policy.get("schema") != 1 or policy.get("app_id") != app_id:
        raise RollbackPolicyError("rollback policy app contract mismatch")
    _base_version(policy.get("minimum_5tratumos_version"))
    minimum = str(policy.get("minimum_base_version") or "")
    if _base_version(target_version) < _base_version(minimum):
        raise RollbackPolicyError("rollback denied")
    return {"enforced": True, "app_id": app_id, "minimum_base_version": minimum}
