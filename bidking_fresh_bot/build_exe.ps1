$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$rapidocrRoot = python -c "import rapidocr_onnxruntime, pathlib; print(pathlib.Path(rapidocr_onnxruntime.__file__).resolve().parent)"
if (-not $rapidocrRoot) {
  throw "Could not locate rapidocr_onnxruntime package."
}

$rapidocrConfig = Join-Path $rapidocrRoot "config.yaml"
$rapidocrModels = Join-Path $rapidocrRoot "models"

python -m pip install -r ..\requirements.txt
python -m PyInstaller `
  --noconfirm `
  --onefile `
  --windowed `
  --name BidKingFreshBot_release `
  --hidden-import bidking_maa_test `
  --hidden-import bidking_maa_test.central_info_parser `
  --hidden-import bidking_maa_test.window_backend `
  --hidden-import rapidocr_onnxruntime `
  --hidden-import rapidocr_onnxruntime.main `
  --hidden-import onnxruntime `
  --hidden-import pyautogui `
  --add-data "config.json;." `
  --add-data "price_config.json;." `
  --add-data "..\manual_bidking_advisor.py;." `
  --add-data "..\bidking_maa_test\__init__.py;bidking_maa_test" `
  --add-data "..\bidking_maa_test\central_info_parser.py;bidking_maa_test" `
  --add-data "..\bidking_maa_test\window_backend.py;bidking_maa_test" `
  --add-data "..\bidking_maa_test\analyze_screenshot.py;bidking_maa_test" `
  --add-data "..\bidking_maa_test\roi_config.json;bidking_maa_test" `
  --add-data "${rapidocrConfig};rapidocr_onnxruntime" `
  --add-data "${rapidocrModels};rapidocr_onnxruntime\models" `
  bidking_gui.py

Write-Host ""
Write-Host "Build complete: dist\BidKingFreshBot_release.exe"
