#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'macOS上で実行してください。'; exit 1
fi
"${NICT_PYTHON:-python3}" -m venv .venv-build
.venv-build/bin/python -m pip install -r requirements-build.txt
.venv-build/bin/python scripts/build_icons.py
.venv-build/bin/python -m PyInstaller --clean --noconfirm --windowed --name NICTAnalogClock --osx-bundle-identifier jp.nictanalogclock.app --collect-all tzdata --icon assets/app-icon.icns --add-data "assets/app-icon.png:assets" main.py
.venv-build/bin/python scripts/verify_packaged_icon.py
echo '作成先: dist/NICTAnalogClock.app（未署名）'
