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


def materialize_compose(compose: dict, host_port: int) -> dict:
    """Relevant store materialization contract from bin/5tratumos."""
    services = compose.get("services") or {}

    def env_to_dict(env):
        if isinstance(env, dict):
            return {str(key).strip(): "" if value is None else str(value) for key, value in env.items() if str(key).strip()}
        if isinstance(env, list):
            return dict(str(item).split("=", 1) for item in env if "=" in str(item))
        return {}

    proxy = services.get("app_proxy") if isinstance(services.get("app_proxy"), dict) else None
    proxy_env = env_to_dict(proxy.get("environment") if proxy else None)
    app_host = str(proxy_env.get("APP_HOST") or "").strip()
    app_port = int(str(proxy_env.get("APP_PORT") or host_port))
    services.pop("app_proxy", None)

    for name, service in list(services.items()):
        if not isinstance(service, dict):
            continue
        dependencies = service.get("depends_on")
        if isinstance(dependencies, list):
            service["depends_on"] = [item for item in dependencies if item != "app_proxy"]
        elif isinstance(dependencies, dict):
            dependencies.pop("app_proxy", None)
        restart = str(service.get("restart") or "").strip().lower()
        if name != "init" and (not restart or restart.startswith("on-failure")):
            service["restart"] = "unless-stopped"

    ui_service = app_host if app_host in services else "app" if "app" in services else None
    if ui_service and host_port:
        ports = services[ui_service].get("ports") or []
        if not any(str(item).split("/", 1)[0].split(":")[0] == str(host_port) for item in ports):
            ports.append(f"{host_port}:{app_port}")
        services[ui_service]["ports"] = ports

    compose["services"] = services
    compose.pop("version", None)
    networks = compose.get("networks")
    dropped = set()
    if isinstance(networks, dict):
        for name, config in list(networks.items()):
            configured_name = str(config.get("name") or "") if isinstance(config, dict) else ""
            if str(name).endswith("_main_network") or configured_name.endswith("_main_network"):
                networks.pop(name)
                dropped.add(str(name))
        if not networks:
            compose.pop("networks", None)
    for service in services.values():
        service_networks = service.get("networks") if isinstance(service, dict) else None
        if isinstance(service_networks, list):
            remaining = [name for name in service_networks if str(name) not in dropped]
            if remaining:
                service["networks"] = remaining
            else:
                service.pop("networks", None)
        elif isinstance(service_networks, dict):
            for name in dropped:
                service_networks.pop(name, None)
            if not service_networks:
                service.pop("networks", None)
    return compose
