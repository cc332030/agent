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
rem Run the logic code, then hold the window open: a dot-double-click gives us
rem a console window of our own, and it vanishes the moment this script exits --
rem progress lines and the failure list would fly by unread (user's words: do
rem not close the window when the download finishes).
rem
rem Hold ONLY when we own the window. cmd /c gives us a console window of our
rem own when no console is attached (dot-double-click, shortcut) and adds the
rem prompt; launched from an existing console, a pipe or CI it just runs and
rem returns -- prompting there would look like a hung command and eat the next
rem keystroke (specs/stack/windows.adoc: do not disturb the user's session).
cmd /c ""%FETCH_SPECS_RUNTIME%" "%~dp0fetch-specs.py" %* & pause"
set "FETCH_SPECS_STATUS=%errorlevel%"
exit /b %FETCH_SPECS_STATUS%
