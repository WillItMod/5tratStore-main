FROM debian:bookworm AS builder

# v9.26.5 is an official upstream tag. DigiByte had not yet attached binary
# release assets when this image was built, so compile the exact tagged commit
# rather than taking code from a moving branch.
ARG TARGETARCH
ARG DGB_VERSION="9.26.5"
ARG DGB_RELEASE_TAG="v9.26.5"
ARG DGB_COMMIT="05b50e229db5a3d1fb316c77f3f6c62efa879b96"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
      autoconf \
      automake \
      bsdmainutils \
      build-essential \
      ca-certificates \
      curl \
      git \
      libtool \
      pkg-config \
      python3 \
      xz-utils && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --filter=blob:none https://github.com/DigiByte-Core/digibyte.git /src && \
    cd /src && \
    git checkout --detach "${DGB_COMMIT}" && \
    test "$(git rev-parse HEAD)" = "${DGB_COMMIT}" && \
    git tag --points-at HEAD | grep -Fx "${DGB_RELEASE_TAG}"

WORKDIR /src

RUN set -eu; \
    case "${TARGETARCH:-}" in \
      amd64) host="x86_64-pc-linux-gnu" ;; \
      arm64) host="aarch64-linux-gnu" ;; \
      *) echo "unsupported TARGETARCH=${TARGETARCH:-<unset>}"; exit 1 ;; \
    esac; \
    make -C depends -j"$(nproc)" HOST="${host}" NO_QT=1 NO_QR=1; \
    ./autogen.sh; \
    CONFIG_SITE="$PWD/depends/${host}/share/config.site" \
      ./configure \
        --without-gui \
        --disable-tests \
        --disable-bench \
        --disable-man \
        --enable-reduce-exports; \
    make -j"$(nproc)"; \
    make install DESTDIR=/stage

FROM debian:bookworm-slim

ARG DGB_VERSION="9.26.5"
ARG DGB_COMMIT="05b50e229db5a3d1fb316c77f3f6c62efa879b96"

LABEL org.opencontainers.image.source="https://github.com/DigiByte-Core/digibyte" \
      org.opencontainers.image.version="${DGB_VERSION}" \
      org.opencontainers.image.revision="${DGB_COMMIT}"

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates libstdc++6 libgcc-s1 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /stage/usr/local/bin/digibyted /usr/local/bin/digibyted
COPY --from=builder /stage/usr/local/bin/digibyte-cli /usr/local/bin/digibyte-cli
COPY --from=builder /stage/usr/local/bin/digibyte-tx /usr/local/bin/digibyte-tx
COPY --from=builder /stage/usr/local/bin/digibyte-util /usr/local/bin/digibyte-util
COPY --from=builder /stage/usr/local/bin/digibyte-wallet /usr/local/bin/digibyte-wallet

RUN groupadd -g 1000 umbrel 2>/dev/null || true && \
    useradd -m -u 1000 -g 1000 umbrel 2>/dev/null || true && \
    mkdir -p /data && chown -R 1000:1000 /data

USER 1000:1000

EXPOSE 12024 14022

CMD ["digibyted", "-datadir=/data", "-printtoconsole"]
