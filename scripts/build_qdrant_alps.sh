#!/usr/bin/env bash
#
# Build the Qdrant server binary from source on CSCS Alps (GH200, aarch64,
# 64KB pages). Required because the upstream prebuilt aarch64 binary bundles
# jemalloc compiled for 4KB pages and crashes on first allocation here:
#
#     <jemalloc>: Unsupported system page size
#     terminate called without an active exception
#
# Setting JEMALLOC_SYS_WITH_LG_PAGE=16 (= log2(65536)) makes the build
# rebuild jemalloc to match the system page size.
#
# Usage:
#   build_qdrant_alps.sh                 # default: v1.17.1
#   build_qdrant_alps.sh v1.18.0         # override Qdrant version tag
#
# Output binary: $BENCH_DIR/qdrant-src/target/release/qdrant
#
set -euo pipefail

QDRANT_VERSION="${1:-v1.17.1}"
PROTOC_VERSION="34.1"
BENCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
JOBS="${JOBS:-64}"

echo "==> Build target: Qdrant ${QDRANT_VERSION}, $(uname -m), pagesize=$(getconf PAGESIZE)"
echo "==> BENCH_DIR=${BENCH_DIR}"

# ---------------------------------------------------------------------------
# 1. Rust toolchain
# ---------------------------------------------------------------------------
if [ ! -x "${HOME}/.cargo/bin/cargo" ]; then
    echo "==> Installing rustup (no PATH modification)"
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs |
        sh -s -- -y --default-toolchain stable --profile minimal --no-modify-path
fi
. "${HOME}/.cargo/env"
echo "==> rustc:  $(rustc --version)"
echo "==> cargo:  $(cargo --version)"

# ---------------------------------------------------------------------------
# 2. protoc (Protocol Buffers compiler — qdrant gRPC codegen needs it)
# ---------------------------------------------------------------------------
PROTOC="${BENCH_DIR}/protoc/bin/protoc"
if [ ! -x "${PROTOC}" ]; then
    echo "==> Installing protoc ${PROTOC_VERSION}"
    mkdir -p "${BENCH_DIR}/protoc"
    cd "${BENCH_DIR}/protoc"
    curl -fsSL -o protoc.zip \
        "https://github.com/protocolbuffers/protobuf/releases/download/v${PROTOC_VERSION}/protoc-${PROTOC_VERSION}-linux-aarch_64.zip"
    unzip -oq protoc.zip
    rm protoc.zip
fi
echo "==> protoc: $(${PROTOC} --version)"

# ---------------------------------------------------------------------------
# 3. Qdrant source
# ---------------------------------------------------------------------------
SRC_DIR="${BENCH_DIR}/qdrant-src"
if [ ! -d "${SRC_DIR}" ]; then
    echo "==> Cloning qdrant ${QDRANT_VERSION}"
    git clone --depth 1 --branch "${QDRANT_VERSION}" \
        https://github.com/qdrant/qdrant.git "${SRC_DIR}"
else
    CURRENT_TAG="$(git -C "${SRC_DIR}" describe --tags --exact-match 2>/dev/null || echo unknown)"
    if [ "${CURRENT_TAG}" != "${QDRANT_VERSION}" ]; then
        echo "WARNING: ${SRC_DIR} is at tag '${CURRENT_TAG}', requested '${QDRANT_VERSION}'."
        echo "         Refusing to overwrite. rm -rf ${SRC_DIR} to rebuild a different tag."
        exit 1
    fi
fi

# ---------------------------------------------------------------------------
# 4. Build
# ---------------------------------------------------------------------------
echo "==> Building (LG_PAGE=16, -j ${JOBS})  — first build takes ~20 min"
cd "${SRC_DIR}"
PROTOC="${PROTOC}" \
JEMALLOC_SYS_WITH_LG_PAGE=16 \
    cargo build --release --bin qdrant -j "${JOBS}"

BIN="${SRC_DIR}/target/release/qdrant"
echo "==> Built: ${BIN}"
echo "==> Version: $("${BIN}" --version)"
echo
echo "Run the server (loopback only) with:"
echo "  QDRANT__SERVICE__HOST=127.0.0.1 \\"
echo "  QDRANT__STORAGE__STORAGE_PATH=${BENCH_DIR}/qdrant-data \\"
echo "  ${BIN}"
