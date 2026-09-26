# Cynqra installer for Windows. Double click INSTALL.bat, or run:  powershell -ExecutionPolicy Bypass -File install.ps1 [model]
# Installs Ollama if needed, picks the model for this PC (or the one you name), downloads it,
# writes poc\local_config.json and runs the doctor. Safe to run again.
param([string]$Model = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$Url = "http://127.0.0.1:11434"
function Say($t) { Write-Host "`n== $t" -ForegroundColor Cyan }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User") }
function Ollama-Up { try { Invoke-RestMethod "$Url/api/version" -TimeoutSec 3 | Out-Null; $true } catch { $false } }

Say "1 of 5  Python 3.10 or newer"
$PyExe = $null; $PyArgs = @()
function Test-Py($exe, $pre) {
  try { & $exe @pre -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null; return ($LASTEXITCODE -eq 0) } catch { return $false }
}
if (Test-Py "py" @("-3")) { $PyExe = "py"; $PyArgs = @("-3") }
elseif (Test-Py "python" @()) { $PyExe = "python"; $PyArgs = @() }
else {
  Write-Host "Python 3.10+ is missing. Installing it with winget..."
  winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements
  Refresh-Path
  $PyExe = "py"; $PyArgs = @("-3")
}
& $PyExe @PyArgs --version

Say "2 of 5  Ollama, which runs the open model on this PC"
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    Refresh-Path
  } else {
    Write-Host "Download Ollama from https://ollama.com/download/windows, install it, then run INSTALL.bat again."
    Start-Process "https://ollama.com/download/windows"; exit 1
  }
}
ollama --version

Say "3 of 5  Starting Ollama"
if (-not (Ollama-Up)) {
  Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden
  for ($i = 0; $i -lt 30 -and -not (Ollama-Up); $i++) { Start-Sleep 1 }
}
if (-not (Ollama-Up)) { Write-Host "Ollama did not start. Open the Ollama app from the Start menu, then run INSTALL.bat again."; exit 1 }

Say "4 of 5  Choosing and downloading the model (several GB the first time)"
$SetupArgs = @("poc\cynqra_cli.py", "setup", "--print-model")
if ($Model) { $SetupArgs += @("--model", $Model) }
$Chosen = (& $PyExe @PyArgs @SetupArgs | Select-Object -Last 1).Trim()
Write-Host "Model: $Chosen  (settings in poc\local_config.json)"
ollama pull $Chosen

Say "5 of 5  Checking everything"
& $PyExe @PyArgs poc\cynqra_cli.py doctor
Write-Host "`nNext: double click CYNQRA.bat, or run:  py -3 poc\cynqra_cli.py run"
