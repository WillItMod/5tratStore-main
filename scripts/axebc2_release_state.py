import re
APP_TAG="ghcr.io/willitmod/axebc2-app:0.1.10"
CORE_TAG="ghcr.io/willitmod/bitcoinii-core:31.1.0"
def validate(compose,phase):
    if phase not in {"prefinalization","finalized"}: raise ValueError("invalid release phase")
    a=APP_TAG+"@sha256:APP_PROMOTED_DIGEST_REQUIRED"; c=CORE_TAG+"@sha256:CORE31_PROMOTED_DIGEST_REQUIRED"
    if phase=="prefinalization":
        if compose.count(a)!=1 or compose.count(c)!=2 or compose.count("_DIGEST_REQUIRED")!=3: raise ValueError("prefinalization requires the exact three digest sentinels")
        return
    if "_DIGEST_REQUIRED" in compose: raise ValueError("finalized release contains a digest sentinel")
    apps=re.findall(re.escape(APP_TAG)+r"@(sha256:[0-9a-f]{64})",compose); cores=re.findall(re.escape(CORE_TAG)+r"@(sha256:[0-9a-f]{64})",compose)
    if len(apps)!=1 or len(cores)!=2 or len(set(cores))!=1: raise ValueError("finalized release requires one app pin and two identical Core pins")
