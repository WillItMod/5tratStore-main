APP_TAG="ghcr.io/willitmod/axebc2-app:0.1.15"
APP_DIGEST="sha256:0a7110d55a538ce9d5352b8617a89cd83a548151b5eed2486b13495c06a5c65d"
CORE_TAG="ghcr.io/willitmod/bitcoinii-core:31.1.0"
CORE_DIGEST="sha256:8875917ece57668fe9925d40a256ce8d429a3071511bb555d4ace1fa4370afc6"
def validate(compose,phase):
    if phase not in {"prefinalization","finalized"}: raise ValueError("invalid release phase")
    a=APP_TAG+"@sha256:APP_PROMOTED_DIGEST_REQUIRED"; c=CORE_TAG+"@"+CORE_DIGEST
    if phase=="prefinalization":
        if compose.count(a)!=1 or compose.count(c)!=2 or compose.count("_DIGEST_REQUIRED")!=1: raise ValueError("prefinalization requires one app sentinel and two exact Core pins")
        return
    if "_DIGEST_REQUIRED" in compose: raise ValueError("finalized release contains a digest sentinel")
    if compose.count(APP_TAG+"@"+APP_DIGEST)!=1 or compose.count(c)!=2: raise ValueError("finalized release requires the exact app pin and two exact Core pins")


# These are the complete Compose models from canonical DEV 94801dcd23fda52be1eb193637a13d73243b04f1.
# Historical finalization constants above remain bound to their original release.
PROMOTED_COMPOSE_SHA256 = "6bfc22540f6d75ed418787db54e96a1b9ab0fddb64810b12a9a511f77b3458ce"
PROMOTED_TEMPLATE_SHA256 = "9dd05b7a36d5a8c10ab825af2bd84453edd14b11189c2f32e89b160bffec735a"
PROMOTED_SOURCE_SHA256 = {
    "data/init/init.sh": "0a7fc21333ca8c7d4b3a43f1073313bf23b19fb5fd980fcae846bd9602e70b02",
    "hooks/umbrel-init": "6c3eede0f925f3c3e456e57521d741d4fd0541ad088a5ad5a2e5e855aae73844",
    "hooks/umbrel-ckpool": "b278e5875b841b9e825a07c80066f92c365713f97726bfaa4d62361d2b6969ab",
    "data/templates/bitcoinII.conf.template": "9aa2e70894a4e9353d83f34c8de91fd272efa1db6e4ba918be4f8c4c8ced442a",
    "data/templates/ckpool.conf.template": "1ec048667f98c3bad4b5a27b8b3f590f71eab43dd6d3e7dd58eed98ccddb46d2",
}


def validate_promoted_compose(model, template=False):
    """Permit only the reviewed channel display changes to the tested package."""
    import copy
    import hashlib
    import json

    current = copy.deepcopy(model)
    environment = current["services"]["app"]["environment"]
    if environment.get("APP_CHANNEL") != "MAIN" or environment.get("APP_VERSION_SUFFIX") != "":
        raise ValueError("promoted BC2 must declare MAIN with an empty version suffix")
    environment["APP_CHANNEL"] = "BETA"
    environment["APP_VERSION_SUFFIX"] = "-dev"
    digest = hashlib.sha256(json.dumps(current, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    expected = PROMOTED_TEMPLATE_SHA256 if template else PROMOTED_COMPOSE_SHA256
    if digest != expected:
        raise ValueError("promoted BC2 runtime differs from exact canonical DEV948 beyond channel labels")


def validate_promoted_sources(app):
    """Bind native/Umbrel provenance and migration guards to their tested bytes."""
    import hashlib

    for relative, expected in PROMOTED_SOURCE_SHA256.items():
        if hashlib.sha256((app / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("promoted BC2 changed the accepted source: " + relative)
