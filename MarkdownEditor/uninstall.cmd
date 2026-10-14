@echo off
setlocal EnableExtensions
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

echo [1/5] Remove .md context menu...
reg delete "HKCU\Software\Classes\.md\shell\MDViewer" /f >nul 2>&1

echo [2/5] Restore .md default association...
reg delete "HKCU\Software\Classes\MDViewer.md" /f >nul 2>&1
if exist "%HERE%\.mdinstall.bak" (
  set /p OLDVAL=<"%HERE%\.mdinstall.bak"
  if defined OLDVAL (
    if not "%OLDVAL%"=="" reg add "HKCU\Software\Classes\.md" /ve /t REG_SZ /d "%OLDVAL%" /f >nul
  ) else (
    reg delete "HKCU\Software\Classes\.md" /ve /f >nul 2>&1
  )
) else (
  reg delete "HKCU\Software\Classes\.md" /ve /f >nul 2>&1
)
del /f /q "%HERE%\.mdinstall.bak" >nul 2>&1

echo [3/5] Remove Desktop / Start Menu shortcuts...
del /f /q "%USERPROFILE%\Desktop\Markdown Editor.lnk" >nul 2>&1
del /f /q "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Markdown Editor.lnk" >nul 2>&1

echo [4/5] Restore Windows 11 default context menu...
reg delete "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}" /f >nul 2>&1

echo [5/5] Stop running md_server backend...
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*md_server.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }" >nul 2>&1

echo.
echo Uninstall complete.
pause
endlocal
