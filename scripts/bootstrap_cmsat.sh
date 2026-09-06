#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPS_ROOT=${1:-$ROOT/../PIC3withXors}
CMSAT=$DEPS_ROOT/cryptominisat
PATCH=$ROOT/third_party/cryptominisat-5.14.5-affine-pdr.patch

if [[ ! -d "$DEPS_ROOT/.git" ]]; then
    git clone https://github.com/tcplsa/PIC3withXors.git "$DEPS_ROOT"
fi

if [[ -n "$(git -C "$DEPS_ROOT" status --porcelain)" ]]; then
    echo "Refusing to modify a dirty dependency tree: $DEPS_ROOT" >&2
    exit 1
fi

git -C "$DEPS_ROOT" checkout ded074538a3a7511d758f5974ab58b573a9e3737
if git -C "$DEPS_ROOT" apply --check "$PATCH"; then
    git -C "$DEPS_ROOT" apply "$PATCH"
elif ! git -C "$DEPS_ROOT" apply --reverse --check "$PATCH"; then
    echo "CryptoMiniSat patch does not apply cleanly." >&2
    exit 1
fi

cmake -S "$CMSAT" -B "$CMSAT/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DENABLE_TESTING=OFF \
    -DONLY_SIMPLE=ON \
    -DSTATICCOMPILE=OFF
cmake --build "$CMSAT/build" -j"$(nproc)"
make -C "$ROOT" CMSAT_ROOT="$DEPS_ROOT" -j"$(nproc)"

