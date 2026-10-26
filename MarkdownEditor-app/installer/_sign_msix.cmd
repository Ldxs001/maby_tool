@echo off
REM Sideload helper for the Store MSIX: creates a self-signed test cert,
REM signs the package and installs it. Run by the user on purpose.
REM Prerequisite (do it manually once): Developer Mode = ON in
REM Settings - Privacy & security - For developers.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_sign_msix.ps1" %*
pause
