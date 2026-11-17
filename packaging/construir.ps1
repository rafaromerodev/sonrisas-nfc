# Genera el ejecutable (dist\SonrisasNFC) y, si Inno Setup está instalado, el instalador.
# Uso (desde la raíz del proyecto):  powershell -ExecutionPolicy Bypass -File packaging\construir.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) { py -3 -m venv .venv }
.venv\Scripts\python -m pip install --quiet --upgrade pip
.venv\Scripts\python -m pip install --quiet -e ".[dev]"

.venv\Scripts\python -m pytest
if ($LASTEXITCODE -ne 0) { throw "Los tests han fallado: no se genera el ejecutable." }

.venv\Scripts\pyinstaller --noconfirm --clean packaging\sonrisas_nfc.spec
Write-Host "Ejecutable generado en dist\SonrisasNFC\SonrisasNFC.exe" -ForegroundColor Green

# Carpeta lista para copiar al pendrive: programa + instalador sencillo + instrucciones.
$entrega = "entrega\SonrisasNFC-entrega"
if (Test-Path $entrega) { Remove-Item -Recurse -Force $entrega }
New-Item -ItemType Directory -Force $entrega | Out-Null
Copy-Item -Recurse dist\SonrisasNFC "$entrega\SonrisasNFC"
Copy-Item packaging\INSTALAR.bat, packaging\LEEME.txt $entrega
Write-Host "Carpeta para el pendrive: $entrega" -ForegroundColor Green

$iscc = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $iscc) {
    & $iscc packaging\instalador.iss
    Write-Host "Instalador generado en packaging\Output" -ForegroundColor Green
} else {
    Write-Host "Inno Setup no encontrado: se omite el instalador (https://jrsoftware.org/isinfo.php)." -ForegroundColor Yellow
}
