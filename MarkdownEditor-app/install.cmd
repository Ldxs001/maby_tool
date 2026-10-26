@echo off
REM SPDX-License-Identifier: AGPL-3.0-or-later
REM Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
setlocal EnableExtensions
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

set "PYW=%HERE%\python\pythonw.exe"
if not exist "%PYW%" (
  echo [ERROR] Portable python not found:
  echo   %PYW%
  echo Make sure the python\ subfolder exists with pythonw.exe in it.
  pause
  exit /b 1
)

REM The launcher shim exe (FileDescription = "Markdown Editor"). The Win11
REM Open With picker shows the command exe's description, so pythonw.exe shows up
REM as "Python". Our own exe fixes the name for good.
REM
REM The exe is pre-built at packaging time and shipped inside the payload, so
REM the uninstall entry always has a real target and no compiler runs on the
REM user's machine. csc.exe below is only a fallback for a payload built by an
REM older version that did not ship the pre-built exe.
set "CSC=%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if not exist "%CSC%" set "CSC=%WINDIR%\Microsoft.NET\Framework\v4.0.30319\csc.exe"
if exist "%HERE%\MarkdownEditor.exe" (
  echo   MarkdownEditor.exe: using pre-built copy from package.
) else (
  if exist "%CSC%" (
    if exist "%HERE%\md-editor.ico" (
      "%CSC%" /nologo /target:winexe /win32icon:"%HERE%\md-editor.ico" /out:"%HERE%\MarkdownEditor.exe" "%HERE%\MarkdownEditor.cs"
    ) else (
      "%CSC%" /nologo /target:winexe /out:"%HERE%\MarkdownEditor.exe" "%HERE%\MarkdownEditor.cs"
    )
  ) else (
    echo [WARN] MarkdownEditor.exe missing and csc.exe not found
  )
)

REM The uninstaller GUI (icon = pixel MD with red X badge). Pre-built at
REM packaging time for the same reason: "Apps and features" points its
REM UninstallString at this file, so it must exist even on a machine without
REM a compiler.
REM Fallback compile (top-level lines on purpose: %VAR% inside a parenthesized
REM block expands at parse time, so the option variable would stay empty there).
if exist "%HERE%\UninstallMDEditor.exe" (
  echo   UninstallMDEditor.exe: using pre-built copy from package.
  goto uninstaller_ready
)
if not exist "%CSC%" (
  echo [WARN] UninstallMDEditor.exe missing and csc.exe not found
  goto uninstaller_ready
)
set "UNOPT="
if exist "%HERE%\uninstall-md.ico" set "UNOPT=/win32icon:"%HERE%\uninstall-md.ico""
if exist "%HERE%\app.manifest" set "UNOPT=%UNOPT% /win32manifest:"%HERE%\app.manifest""
"%CSC%" /nologo /target:winexe %UNOPT% /out:"%HERE%\UninstallMDEditor.exe" "%HERE%\UninstallMDEditor.cs"
:uninstaller_ready

echo Install path: %HERE%
echo Python:       %PYW%
echo.

echo [1/5] Register .md context menu (HKCU, no admin needed)...
reg add "HKCU\Software\Classes\.md\shell\MDViewer" /ve /t REG_SZ /d "Open with Markdown Editor" /f
reg add "HKCU\Software\Classes\.md\shell\MDViewer\command" /ve /t REG_SZ /d "%HERE%\MarkdownEditor.exe \"%%1\"" /f

echo [2/5] Set .md default association (double-click opens this editor)...
REM Backup the original .md default association.
REM The backup file is NOT in the dist checklist, so extraction never overwrites
REM it and it survives upgrades.
REM
REM Two cases must be told apart:
REM   1) The backup holds this app's own ProgID (MDViewer.md) -- that is a stale
REM      value left by an older build (it saved the current value on upgrade and
REM      mistook it for the original). It must be discarded and recomputed,
REM      otherwise .md association can never be restored on uninstall.
REM   2) The backup holds anything else -- that is the real original value and
REM      must be preserved untouched.
REM
REM Note: keep this comment block ASCII-only. cmd.exe reads .cmd as the OEM
REM codepage; non-ASCII bytes inside REM lines get mangled and can break
REM parsing. Chinese is fine inside echo / reg commands, not inside REM.
set "MDE_HERE=%HERE%"
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "$bak=Join-Path $env:MDE_HERE '.mdinstall.bak'; $cur=(Get-ItemProperty -Path 'HKCU:\Software\Classes\.md' -Name '(default)' -ErrorAction SilentlyContinue).'(default)'; $old=$null; if(Test-Path $bak){$old=(Get-Content -Raw -LiteralPath $bak -ErrorAction SilentlyContinue); if($old){$old=$old.Trim()}}; if($old -and $old -ne 'MDViewer.md'){Write-Output ('  Keeping original .md association backup: ' + $old)}else{$orig=''; if($cur -and $cur -ne 'MDViewer.md'){$orig=$cur}; Set-Content -LiteralPath $bak -Value $orig -Encoding ASCII -NoNewline; Write-Output ('  Saved original .md association backup: ' + $orig)}"
reg add "HKCU\Software\Classes\.md" /ve /t REG_SZ /d "MDViewer.md" /f
reg add "HKCU\Software\Classes\MDViewer.md" /ve /t REG_SZ /d "Markdown Document (MD Editor)" /f
REM Win11 OpenWith picker shows the command exe's FileDescription ("Python") unless
REM FriendlyTypeName exists. Provide it, plus a proper document icon.
reg add "HKCU\Software\Classes\MDViewer.md" /v FriendlyTypeName /t REG_EXPAND_SZ /d "Markdown Editor" /f
reg add "HKCU\Software\Classes\MDViewer.md\DefaultIcon" /ve /t REG_SZ /d "%HERE%\md-editor.ico" /f
reg add "HKCU\Software\Classes\MDViewer.md\shell\open\command" /ve /t REG_SZ /d "%HERE%\MarkdownEditor.exe \"%%1\"" /f
REM Register the shim as an application so the picker lists it with the right name/icon
reg add "HKCU\Software\Classes\Applications\MarkdownEditor.exe\shell\open\command" /ve /t REG_SZ /d "%HERE%\MarkdownEditor.exe \"%%1\"" /f
reg add "HKCU\Software\Classes\Applications\MarkdownEditor.exe\DefaultIcon" /ve /t REG_SZ /d "%HERE%\md-editor.ico" /f
REM Clear stale UserChoice. Plain "reg delete" FAILS here: Windows puts an explicit
REM Deny-SetValue ACE on UserChoice (anti-hijack), so reg.exe cannot even open it writable.
REM Use .NET DeleteSubKey (different code path) and report the result loudly.
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "if(Test-Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.md\UserChoice'){try { [Microsoft.Win32.Registry]::CurrentUser.DeleteSubKey('Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.md\UserChoice'); 'UserChoice cleared' } catch { 'UserChoice delete failed: ' + $_.Exception.Message }} else { 'UserChoice not present (skip)' }"
REM Safety net: the stale UserChoice points to ProgID "Markdown Document" which does NOT
REM exist anywhere. Recreate it here so the association resolves to OUR editor regardless.
reg add "HKCU\Software\Classes\Markdown Document" /ve /t REG_SZ /d "Markdown Editor" /f >nul 2>&1
reg add "HKCU\Software\Classes\Markdown Document" /v FriendlyTypeName /t REG_EXPAND_SZ /d "Markdown Editor" /f >nul 2>&1
reg add "HKCU\Software\Classes\Markdown Document\DefaultIcon" /ve /t REG_SZ /d "%HERE%\md-editor.ico" /f >nul 2>&1
reg add "HKCU\Software\Classes\Markdown Document\shell\open\command" /ve /t REG_SZ /d "%HERE%\MarkdownEditor.exe \"%%1\"" /f >nul 2>&1
REM Remove stale pythonw entry from Open With history (it was MRU-first, shown as "Python")
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.md\OpenWithList" /v d /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.md\OpenWithList" /v MRUList /t REG_SZ /d "befgac" /f >nul 2>&1
REM Add this editor into the Open With list
reg add "HKCU\Software\Classes\.md\OpenWithProgids" /v MDViewer.md /t REG_SZ /d "" /f >nul 2>&1
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.md\OpenWithProgids" /v MDViewer.md /t REG_SZ /d "" /f >nul 2>&1

REM ---- Self-contained Markdown (.smd) file association ----
reg add "HKCU\Software\Classes\.smd" /ve /t REG_SZ /d "MDViewer.smd" /f
reg add "HKCU\Software\Classes\.smd\shell\MDViewer" /ve /t REG_SZ /d "Open with Markdown Editor" /f
reg add "HKCU\Software\Classes\.smd\shell\MDViewer\command" /ve /t REG_SZ /d "%HERE%\MarkdownEditor.exe \"%%1\"" /f
reg add "HKCU\Software\Classes\MDViewer.smd" /ve /t REG_SZ /d "Self-contained Markdown Document" /f
reg add "HKCU\Software\Classes\MDViewer.smd" /v FriendlyTypeName /t REG_EXPAND_SZ /d "Markdown Editor" /f
reg add "HKCU\Software\Classes\MDViewer.smd\DefaultIcon" /ve /t REG_SZ /d "%HERE%\md-editor.ico" /f
reg add "HKCU\Software\Classes\MDViewer.smd\shell\open\command" /ve /t REG_SZ /d "%HERE%\MarkdownEditor.exe \"%%1\"" /f
reg add "HKCU\Software\Classes\.smd\OpenWithProgids" /v MDViewer.smd /t REG_SZ /d "" /f >nul 2>&1

echo [3/5] Create Desktop / Start Menu shortcuts...
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -ExecutionPolicy Bypass -File "%HERE%\_mklnk.ps1" -Here "%HERE%"

echo [4/5] Windows 11 context menu visibility...
if /i "%~1"=="nolegacy" (
  echo   Legacy menu NOT enabled. The item will appear under "Show more options".
) else (
  reg add "HKCU\Software\Classes\CLSID\{86ca1aa0-34aa-4e8b-a509-50c905bae2a2}\InprocServer32" /ve /t REG_SZ /d "" /f
  echo   Legacy context menu enabled. The item shows directly on right-click.
  echo   Note: this switches all right-click menus to classic style.
  echo   Run uninstall.cmd to revert.
)

echo [5/5] Register "Apps & features" uninstall entry (HKCU)...
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MDEditor" /v DisplayName /t REG_SZ /d "MDEditor (Markdown Editor)" /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MDEditor" /v DisplayIcon /t REG_SZ /d "%HERE%\md-editor.ico" /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MDEditor" /v UninstallString /t REG_SZ /d "\"%HERE%\UninstallMDEditor.exe\"" /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MDEditor" /v NoModify /t REG_DWORD /d 1 /f
reg add "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\MDEditor" /v NoRepair /t REG_DWORD /d 1 /f

echo.
echo Done. Right-click any .md file, or just double-click it.
echo Tray icon lives in the notification area: new blank doc / exit.
echo Uninstall: Settings - Apps - "MDEditor (Markdown Editor)".
REM pause hangs forever when install.cmd is invoked silently by the setup
REM exe (no interactive console). The setup passes "nopause" to skip it.
if /i not "%~1"=="nopause" pause
endlocal
