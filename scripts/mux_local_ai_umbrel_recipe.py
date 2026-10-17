"""Reviewed full Umbrel Local AI recipe, copied from the protected producer."""
import json
import re

APP = "willitmod-dev-5tratmux"


VERSIONS = {"MAIN": "0.9.82", "DEV": "0.9.82-dev"}


ICON_SHA256 = "3eef68f8307de4df7a43386b2dbc3cdaa2b9e97423c93945c18e6be3256ad9e8"


FILES = {"docker-compose.yml", "umbrel-app.yml", "hooks/pre-start", "icon.png", "data/.gitkeep"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def image_refs(mux_image, local_ai_image, channel):
    require(channel in VERSIONS, "Unknown delivery channel")
    mux_tag = "0.9.82-umbrel" + ("-dev" if channel == "DEV" else "")
    require(re.fullmatch(r"ghcr\.io/willitmod/5tratmux-app:" + mux_tag + r"@sha256:[0-9a-f]{64}", mux_image),
            "The intended protected Umbrel MUX image and immutable digest are required")
    # The already-public package carries a separate, exact supervisor tag.
    # Repository visibility does not establish product or runtime identity.
    require(re.fullmatch(r"ghcr\.io/willitmod/5tratmux-app:local-ai-0\.1\.9-umbrel@sha256:[0-9a-f]{64}", local_ai_image),
            "The compiled Umbrel supervisor image and immutable digest are required")


def recipe_model(mux_image, local_ai_image, channel):
    image_refs(mux_image, local_ai_image, channel)
    return {"version": "3.7", "services": {
        "app_proxy": {"environment": {"APP_HOST": APP + "_server_1", "APP_PORT": "21222"}},
        "server": {
            "image": mux_image, "user": "1000:1000", "init": True,
            "restart": "unless-stopped", "read_only": True,
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "pids_limit": 256, "mem_limit": "1536m", "stop_grace_period": "30s",
            "tmpfs": ["/tmp:rw,nosuid,nodev,exec,size=256m,mode=1777"],
            "ports": ["7331:7331/tcp"], "expose": ["21222"],
            "volumes": ["${APP_DATA_DIR}/data/state:/data/state",
                        "${APP_DATA_DIR}/data/local-ai-control:/run/5tratmux-local-ai:ro"],
            "environment": {
                "MUX_PLATFORM": "umbrel", "APP_HOST": "0.0.0.0", "APP_PORT": "21222",
                "STATE_DIR": "/data/state", "MUX_OPERATOR_PASSWORD": "${APP_PASSWORD}",
                "MUX_AUTH_TRUSTED_PROXIES": "${GATEWAY_IP}", "MUX_HTTP_STRICT_HOST": "1",
                "MUX_HTTP_ALLOWED_HOSTS": "${DEVICE_DOMAIN_NAME},${DEVICE_HOSTNAME},localhost",
                "APP_VERSION": VERSIONS[channel], "APP_CHANNEL": channel,
                "LOCAL_AI_SUPERVISOR_SOCKET": "/run/5tratmux-local-ai/control.sock",
            },
        },
        "local_ai": {
            "image": local_ai_image, "user": "1000:1000", "init": True,
            "restart": "unless-stopped", "read_only": True,
            "cap_drop": ["ALL"], "security_opt": ["no-new-privileges:true"],
            "pids_limit": 128, "mem_limit": "6g", "memswap_limit": "6g", "cpus": 2,
            "stop_grace_period": "45s",
            "tmpfs": ["/tmp:rw,nosuid,nodev,exec,size=512m,mode=1777"],
            "volumes": ["${APP_DATA_DIR}/data/local-ai-control:/run/5tratmux-local-ai",
                        "${APP_DATA_DIR}/data/local-ai:/data/local-ai"],
        },
    }}


def validate_recipe(model, mux_image, local_ai_image, channel):
    require(json.dumps(model, sort_keys=True) == json.dumps(recipe_model(mux_image, local_ai_image, channel), sort_keys=True),
            "Unreviewed Umbrel runtime, storage or security model")
    return model


def manifest_model(channel):
    require(channel in VERSIONS, "Unknown delivery channel")
    return {
        "manifestVersion": 1, "id": APP, "name": "5tratMux" + (" DEV" if channel == "DEV" else ""),
        "tagline": "Route miners through one stable Stratum endpoint",
        "icon": f"https://raw.githubusercontent.com/WillItMod/5tratStore-{channel.lower()}/main/{APP}/icon.png",
        "category": "crypto", "version": VERSIONS[channel], "port": 21222,
        "description": "Standalone Stratum routing for Umbrel. Configure a pool endpoint and account, "
            "set the Umbrel LAN address in Connection settings, and connect miners to TCP port 7331. "
            "Manual routing requires active trial or paid licence access. Local AI is available without "
            "a licence on supported hardware and downloads its model when installed from Settings. "
            "Cloud AI remains optional. An 8 GB or larger Umbrel host is recommended; Local AI requires "
            "sufficient available memory and storage. Sign in using the generated app password shown by Umbrel. "
            "Use Umbrel to start, stop and update the app.",
        "developer": "WillItMod", "website": "https://5tratum.com",
        "repo": "https://github.com/WillItMod/5tratMux", "support": "https://github.com/WillItMod/5tratMux/issues",
        "dependencies": [], "permissions": [], "gallery": [], "path": "", "defaultUsername": "",
        "deterministicPassword": True, "storage": {"dataRoot": "data"},
        "releaseNotes": "Adds licence-free managed Local AI on supported Umbrel hardware with a compiled, "
            "isolated supervisor. Install and manage the model in Settings. Local AI starts in Off state; "
            "its model, preferences and existing MUX settings persist across normal app updates and storage moves. "
            "The generated app password, dashboard layout, miner settings, dashboard port 21222 and mining port "
            "7331 are retained. Routing still requires existing trial or paid licence access.",
    }
