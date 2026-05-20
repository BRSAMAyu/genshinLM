$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root
python -m pip install -r requirements.txt
if (Test-Path ".\desktop\package.json") {
  Push-Location ".\desktop"
  npm install
  Pop-Location
}
python .\scripts\doctor.py

