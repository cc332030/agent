@echo off
rem fetch-specs - Windows entry (thin shell: locate the logic code, pass
rem arguments through unchanged, return its exit code unchanged)
rem
rem Interpreter lookup, in order: the "py" launcher (py -3), then a
rem "python3" on PATH, then a "python" on PATH. Use the first one found and
rem exit non-zero with a message when none exists -- do not run on silently
rem (.bat must be pure ASCII, so this stays English).
setlocal
set "FETCH_SPECS_RUNTIME="
where py >nul 2>nul && set "FETCH_SPECS_RUNTIME=py -3"
if not defined FETCH_SPECS_RUNTIME where python3 >nul 2>nul && set "FETCH_SPECS_RUNTIME=python3"
if not defined FETCH_SPECS_RUNTIME where python >nul 2>nul && set "FETCH_SPECS_RUNTIME=python"
if not defined FETCH_SPECS_RUNTIME (
  echo Error: no python interpreter found ^(tried py, python3, python^) 1>&2
  exit /b 127
)
%FETCH_SPECS_RUNTIME% "%~dp0fetch-specs.py" %*
exit /b %errorlevel%
