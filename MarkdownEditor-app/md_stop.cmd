@echo off
REM SPDX-License-Identifier: AGPL-3.0-or-later
REM Copyright (C) 2026 wUwproject. Licensed under GNU AGPL v3 (or later).
REM Stop the running MD editor backend (safe even if it is not running).
"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe" -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*md_server.py*' -or $_.CommandLine -like '*_md_run.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"
echo Stop signal sent. (No effect if backend is not running.)
