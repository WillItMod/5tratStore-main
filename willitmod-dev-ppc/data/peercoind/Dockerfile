FROM debian:bookworm-slim

ARG PEERCOIN_VERSION=0.15.1ppc
ARG PEERCOIN_LINUX_BUILD=1af7509666a7
ARG TARGETARCH

RUN set -eux; \
  apt-get update; \
  apt-get install -y --no-install-recommends ca-certificates curl tini; \
  rm -rf /var/lib/apt/lists/*

RUN set -eux; \
  case "${TARGETARCH}" in \
    amd64) pc_arch="x86_64-linux-gnu" ;; \
    arm64) pc_arch="aarch64-linux-gnu" ;; \
    *) echo "Unsupported TARGETARCH=${TARGETARCH}" >&2; exit 1 ;; \
  esac; \
  url="https://github.com/peercoin/peercoin/releases/download/v${PEERCOIN_VERSION}/peercoin-${PEERCOIN_LINUX_BUILD}-${pc_arch}.tar.gz"; \
  echo "Downloading ${url}"; \
  curl -fsSL "${url}" -o /tmp/peercoin.tgz; \
  tar -xzf /tmp/peercoin.tgz -C /opt; \
  rm -f /tmp/peercoin.tgz; \
  peercoind_path="$(find /opt -maxdepth 4 -type f -name peercoind | head -n 1)"; \
  peercoin_cli_path="$(find /opt -maxdepth 4 -type f -name peercoin-cli | head -n 1)"; \
  peercoin_tx_path="$(find /opt -maxdepth 4 -type f -name peercoin-tx | head -n 1)"; \
  test -n "${peercoind_path}"; \
  test -n "${peercoin_cli_path}"; \
  test -n "${peercoin_tx_path}"; \
  ln -sf "${peercoind_path}" /usr/local/bin/peercoind; \
  ln -sf "${peercoin_cli_path}" /usr/local/bin/peercoin-cli; \
  ln -sf "${peercoin_tx_path}" /usr/local/bin/peercoin-tx

COPY peercoind-wrapper.sh /usr/local/bin/peercoind-wrapper.sh
RUN chmod 0755 /usr/local/bin/peercoind-wrapper.sh

EXPOSE 9902 9901 28336

ENTRYPOINT ["tini", "--", "/usr/local/bin/peercoind-wrapper.sh"]
CMD ["-datadir=/data", "-conf=/data/peercoin.conf"]
