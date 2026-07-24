FROM mcr.microsoft.com/dotnet/sdk:6.0-jammy AS builder

WORKDIR /src

RUN find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
      -exec sed -i 's|http://ports.ubuntu.com/ubuntu-ports|https://mirrors.mit.edu/ubuntu-ports|g' {} + && \
    apt-get -o Acquire::Retries=5 -o Acquire::https::Timeout=30 update && \
    apt-get -y install --no-install-recommends \
      build-essential \
      libssl-dev \
      pkg-config \
      libboost-all-dev \
      libsodium-dev \
      libzmq5 \
      libzmq3-dev \
      ca-certificates \
      curl && \
    rm -rf /var/lib/apt/lists/*

# Miningcore source is provided as the Docker build context by the GitHub Actions workflow.
COPY . .

# Build a DGB-focused libmultihash that supports DGB's 5 algos (sha256, scrypt, groestl, skein, qubit).
# Note: sha256d is implemented in managed code, but we include sha256csm_export for completeness.
RUN set -eux; \
    mkdir -p /tmp/axedgb-multihash; \
    printf '%s\n' \
      '#include <stdint.h>' \
      'void scrypt_N_R_1_256(const char* input, char* output, uint32_t N, uint32_t R, uint32_t input_len);' \
      'void sha256csm_hash(const char* input, char* output, uint32_t input_len);' \
      'void groestl_hash(const char* input, char* output, uint32_t input_len);' \
      'void skein_hash(const char* input, char* output, uint32_t input_len);' \
      'void qubit_hash(const char* input, char* output, uint32_t input_len);' \
      '__attribute__((visibility("default"))) void scrypt_export(const char* input, char* output, uint32_t N, uint32_t R, uint32_t input_len)' \
      '{' \
      '  scrypt_N_R_1_256(input, output, N, R, input_len);' \
      '}' \
      '__attribute__((visibility("default"))) void sha256csm_export(const char* input, char* output, uint32_t input_len)' \
      '{' \
      '  sha256csm_hash(input, output, input_len);' \
      '}' \
      '__attribute__((visibility("default"))) void groestl_export(const char* input, char* output, uint32_t input_len)' \
      '{' \
      '  groestl_hash(input, output, input_len);' \
      '}' \
      '__attribute__((visibility("default"))) void skein_export(const char* input, char* output, uint32_t input_len)' \
      '{' \
      '  skein_hash(input, output, input_len);' \
      '}' \
      '__attribute__((visibility("default"))) void qubit_export(const char* input, char* output, uint32_t input_len)' \
      '{' \
      '  qubit_hash(input, output, input_len);' \
      '}' \
      > /tmp/axedgb-multihash/exports_min.c; \
    gcc -shared -fPIC -O2 -std=gnu11 \
      -o /tmp/axedgb-multihash/libmultihash.so \
      /tmp/axedgb-multihash/exports_min.c \
      /src/src/Native/libmultihash/scryptn.c \
      /src/src/Native/libmultihash/sha256csm.c \
      /src/src/Native/libmultihash/groestl.c \
      /src/src/Native/libmultihash/skein.c \
      /src/src/Native/libmultihash/qubit.c \
      /src/src/Native/libmultihash/sha3/sph_cubehash.c \
      /src/src/Native/libmultihash/sha3/sph_luffa.c \
      /src/src/Native/libmultihash/sha3/sph_shavite.c \
      /src/src/Native/libmultihash/sha3/sph_simd.c \
      /src/src/Native/libmultihash/sha3/sph_echo.c \
      /src/src/Native/libmultihash/sha3/sph_groestl.c \
      /src/src/Native/libmultihash/sha3/sph_skein.c \
      /src/src/Native/libmultihash/sha3/sph_sha2.c

# Publish Miningcore binaries.
WORKDIR /src/src/Miningcore
RUN dotnet publish -c Release --framework net6.0 -o /out -p:IsLinux=false

# Copy native library next to the published binary.
RUN cp /tmp/axedgb-multihash/libmultihash.so /out/libmultihash.so

FROM mcr.microsoft.com/dotnet/aspnet:6.0-jammy

WORKDIR /app

RUN find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
      -exec sed -i 's|http://ports.ubuntu.com/ubuntu-ports|https://mirrors.mit.edu/ubuntu-ports|g' {} + && \
    apt-get -o Acquire::Retries=5 -o Acquire::https::Timeout=30 update && \
    apt-get -y install --no-install-recommends \
  libzmq5 \
  ca-certificates \
  curl \
  && (apt-get -y install --no-install-recommends libsodium23 || apt-get -y install --no-install-recommends libsodium-dev) \
  && rm -rf /var/lib/apt/lists/*

COPY --from=builder /out/ ./

# Miningcore P/Invoke uses DllImport("libmultihash") which resolves to liblibmultihash.so on Linux.
RUN ln -sf /app/libmultihash.so /app/liblibmultihash.so

ENV LD_LIBRARY_PATH=/app

EXPOSE 4000-4090
CMD ["./Miningcore", "-c", "config.json"]
