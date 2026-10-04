@echo off
setlocal
cd /d "%~dp0"

set "UPX_DIR=C:\JohnsonProgram\SetDisplayMode\init\upx"
if exist "%UPX_DIR%\upx.exe" (
  echo Using UPX from "%UPX_DIR%"
  python -m PyInstaller --noconfirm --upx-dir "%UPX_DIR%" ^
    --distpath "%~dp0dist" ^
    --workpath "%~dp0build" ^
    WindowsDirectoryMigrator.spec
) else (
  echo UPX not found at "%UPX_DIR%"; building without UPX.
  python -m PyInstaller --noconfirm ^
    --distpath "%~dp0dist" ^
    --workpath "%~dp0build" ^
    WindowsDirectoryMigrator.spec
)

if errorlevel 1 (
  echo PyInstaller failed. Install it with: python -m pip install pyinstaller
  exit /b 1
)

echo Built: "%~dp0dist\WindowsDirectoryMigrator.exe"
