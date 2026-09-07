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
