$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Windows上で実行してください。' }
py -3 -m venv .venv-build
if ($LASTEXITCODE -ne 0) { throw 'venv作成失敗' }
& .\.venv-build\Scripts\python.exe -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw '依存関係インストール失敗' }
& .\.venv-build\Scripts\python.exe -m PyInstaller --clean --noconfirm --onefile --windowed --name NICTAnalogClock --collect-all tzdata main.py
if ($LASTEXITCODE -ne 0) { throw 'ビルド失敗' }
Write-Host '作成先: dist\NICTAnalogClock.exe（未署名）'
