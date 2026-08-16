#!/usr/bin/env bash
set -euo pipefail

# Keep build artefacts beneath native/macos and out of runtime/source state.
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
export CLANK_BUILD_REVISION="$(git -C "$ROOT" rev-parse HEAD)"
exec "${PYTHON:-python3}" -m PyInstaller --noconfirm --clean \
  --distpath "$ROOT/native/macos/dist" \
  --workpath "$ROOT/native/macos/build" \
  "$ROOT/native/macos/SmartphoneClank.spec"
