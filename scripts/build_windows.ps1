$ErrorActionPreference = 'Stop'
python -m pip install .[dev]
pyinstaller --noconfirm --clean --windowed --name LabelReview --paths src run_labelreview.py
Copy-Item LICENSES\THIRD_PARTY_NOTICES.md dist\LabelReview\THIRD_PARTY_NOTICES.md
Write-Host "Built dist\LabelReview\LabelReview.exe"
