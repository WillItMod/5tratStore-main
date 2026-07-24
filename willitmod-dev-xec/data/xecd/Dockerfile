FROM debian:bookworm-slim

ARG BITCOINABC_VERSION=0.33.4
ARG TARGETARCH

RUN set -eux; \
  apt-get update; \
  apt-get install -y --no-install-recommends ca-certificates curl; \
  rm -rf /var/lib/apt/lists/*

RUN set -eux; \
  case "${TARGETARCH}" in \
    amd64) abc_arch="x86_64-linux-gnu" ;; \
    arm64) abc_arch="aarch64-linux-gnu" ;; \
    *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  url="https://github.com/Bitcoin-ABC/bitcoin-abc/releases/download/v${BITCOINABC_VERSION}/bitcoin-abc-${BITCOINABC_VERSION}-${abc_arch}.tar.gz"; \
  echo "Downloading ${url}"; \
  curl -fsSL "${url}" -o /tmp/bitcoin-abc.tgz; \
  tar -xzf /tmp/bitcoin-abc.tgz -C /opt; \
  rm -f /tmp/bitcoin-abc.tgz; \
  ln -sf "/opt/bitcoin-abc-${BITCOINABC_VERSION}/bin/bitcoind" /usr/local/bin/bitcoind; \
  ln -sf "/opt/bitcoin-abc-${BITCOINABC_VERSION}/bin/bitcoin-cli" /usr/local/bin/bitcoin-cli; \
  ln -sf "/opt/bitcoin-abc-${BITCOINABC_VERSION}/bin/bitcoin-tx" /usr/local/bin/bitcoin-tx

# RPC / P2P / ZMQ ports are configured via /data/bitcoin.conf (templated by the app).
EXPOSE 28337 28338 28339

CMD ["bitcoind", "-datadir=/data", "-conf=/data/bitcoin.conf", "-printtoconsole"]
