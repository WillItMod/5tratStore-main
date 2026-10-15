# 5tratSmack runtime components

The DEV store package distributes compiled runtime images while the private
application repository remains private.

- **5TRAT Core** — MIT License. The complete copyright and permission notice is
  included in the runtime image at
  `/usr/share/licenses/5trat-core/COPYING`.
- **ckpool-solo** — GNU General Public License version 3. The exact
  corresponding source and build material for each public image tag is
  distributed as `5tratsmack-ckpool-<version>-source.tar.gz` alongside the
  release, with a SHA-256 checksum. The licence is also present in the runtime
  image at `/usr/share/licenses/ckpool/COPYING`.
- **Komodo DeFi Framework (KDF)** — distributed under the upstream
  `LEGAL/LICENSE-COPYRIGHT-NOTICE`. A pinned copy of that notice is included in
  every KDF runtime image at `/opt/kdf/LICENSE-COPYRIGHT-NOTICE`.
- **Alpine Linux, Debian, Python, cryptography, Segno, miniupnpc, and other
  runtime dependencies** — retain their respective upstream licences and
  notices.
- **5tratSmack application, artwork, orchestration and original integration
  code** — Copyright Hurricane Cloud Solutions LTD, trading as 5tratum. All
  rights not granted by an accompanying licence are reserved.

The public release page must contain the matching ckpool source archive before
the public ckpool image or DEV store entry is announced.
