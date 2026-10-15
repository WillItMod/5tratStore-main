# Retain the actual tested Python/runtime/UI/auth/dependency blobs. Only the
# reviewed engine and immutable recipe bundle are added in this release.
FROM ghcr.io/willitmod/fumbrel:0.1.2-dev@sha256:4d7d0183604372ee340ab51c6f612cc63f832e5e357c3fb2ac77b77106816d10
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.source="https://github.com/WillItMod/5tratStore-dev" \
      org.opencontainers.image.revision="${SOURCE_COMMIT}" \
      org.opencontainers.image.version="0.1.3-dev" \
      org.opencontainers.image.base.digest="sha256:4d7d0183604372ee340ab51c6f612cc63f832e5e357c3fb2ac77b77106816d10"
COPY --chown=0:0 --chmod=0644 engine.py catalog.json /app/
