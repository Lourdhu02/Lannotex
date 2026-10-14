$ErrorActionPreference = 'Stop'
python -m pip install .[dev]
pyinstaller --noconfirm --clean Lannotex.spec
Copy-Item LICENSES\THIRD_PARTY_NOTICES.md dist\Lannotex\THIRD_PARTY_NOTICES.md
Write-Host "Built dist\Lannotex\Lannotex.exe"
