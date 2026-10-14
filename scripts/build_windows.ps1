$ErrorActionPreference = 'Stop'
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path '.venv-build\Scripts\python.exe')) {
    python -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create isolated build environment' }
}
$buildPython = Join-Path $PWD '.venv-build\Scripts\python.exe'
& $buildPython -m pip install -r requirements-windows-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed' }
& $buildPython -m pip install --no-build-isolation --no-deps .
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed' }
& $buildPython -m PyInstaller --noconfirm --clean Lannotex.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
Copy-Item LICENSES\THIRD_PARTY_NOTICES.md dist\Lannotex\THIRD_PARTY_NOTICES.md
Copy-Item README.md dist\Lannotex\README.md
Copy-Item docs dist\Lannotex\docs -Recurse -Force
& $buildPython scripts\collect_notices.py dist\Lannotex\licenses
if ($LASTEXITCODE -ne 0) { throw 'License collection failed' }
& $buildPython scripts\verify_executable.py dist\Lannotex\Lannotex.exe
if ($LASTEXITCODE -ne 0) { throw 'Packaged application verification failed' }
Write-Host "Built dist\Lannotex\Lannotex.exe"
