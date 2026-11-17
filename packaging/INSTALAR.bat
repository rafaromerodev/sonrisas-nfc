@echo off
rem Instala o actualiza Sonrisas NFC para el usuario actual de Windows (no requiere administrador).
rem Solo copia el programa: los datos estan en %LOCALAPPDATA%\SonrisasCanarias\NFC y no se tocan.
setlocal
set "ORIGEN=%~dp0SonrisasNFC"
set "DESTINO=%LOCALAPPDATA%\Programs\SonrisasNFC"

if not exist "%ORIGEN%\SonrisasNFC.exe" (
    echo No se encuentra la carpeta SonrisasNFC junto a este archivo.
    pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq SonrisasNFC.exe" 2>nul | find /I "SonrisasNFC.exe" >nul
if not errorlevel 1 (
    echo Sonrisas NFC esta abierto. Cierrelo y vuelva a ejecutar este instalador.
    pause
    exit /b 1
)

echo Instalando Sonrisas NFC en:
echo   %DESTINO%
robocopy "%ORIGEN%" "%DESTINO%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo ERROR: no se pudieron copiar los archivos.
    pause
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = New-Object -ComObject WScript.Shell;" ^
  "foreach ($d in @([Environment]::GetFolderPath('Desktop'), [Environment]::GetFolderPath('Programs'))) {" ^
  "  $l = $s.CreateShortcut((Join-Path $d 'Sonrisas NFC.lnk'));" ^
  "  $l.TargetPath = '%DESTINO%\SonrisasNFC.exe'; $l.WorkingDirectory = '%DESTINO%';" ^
  "  $l.IconLocation = '%DESTINO%\SonrisasNFC.exe,0'; $l.Save() }"

echo.
echo Instalacion completada. Acceso directo "Sonrisas NFC" creado en el escritorio.
if /I "%~1"=="/sinabrir" goto :eof
start "" "%DESTINO%\SonrisasNFC.exe"
timeout /t 5 >nul
