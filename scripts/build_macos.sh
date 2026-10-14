#!/usr/bin/env bash
# Build the portable macOS app bundle with PyInstaller.
set -euo pipefail
cd "$(dirname "$0")/.."
python -m pip install ".[dev]"
pyinstaller --noconfirm --clean Lannotex.spec
cp LICENSES/THIRD_PARTY_NOTICES.md dist/Lannotex/THIRD_PARTY_NOTICES.md
echo "Built dist/Lannotex/Lannotex.app"
