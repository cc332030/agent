@echo off
rem fetch-specs - Windows entry (thin shell: locate the logic code, pass
rem arguments through unchanged, return its exit code unchanged)
rem
rem Interpreter lookup, in order: the "py" launcher, then a "python3" on PATH,
rem then a "python" on PATH. Use the first one that actually runs.
rem
rem "found on PATH" is NOT "runs": the py launcher is installed on machines
rem where its default python 3 is absent (the Store shim registers it and then
rem dies with "Python was not found"), and a Store shim named python.exe tells
rem you to install Python from the Store instead of running. A probe that only
rem asks `where` picks such a hit and the caller sees "py is not
rem recognized as an internal or external command" -- an interpreter error
rem reported by our own entry.
rem
rem The judge is ONLY exit code 0, never "errorlevel is not 127": every candidate
rem runs the logic code once with --probe (stops at "the manifest can be
rem computed": nothing downloaded, nothing written, no self-update, no restart)
rem and only 0 counts. The candidates that do run the script exit with their own
rem verdicts and must not be skipped: 2 is argparse' complaint on python 3.12
rem and earlier (that python runs the script fine: it rejects --probe), and
rem "the logic code failed" (network, home dir, ...) is the logic code's own
rem answer. Rejecting "anything but 127" instead would drop a working py on the
rem WinGet/Store builds, whose py.exe exits 49 when no python is installed at
rem all -- and then report "no working python" on a machine that has one.
rem
rem Exit non-zero with a message when none of them runs -- do not run on
rem silently (.bat must be pure ASCII, so this stays English).
setlocal
set "FETCH_SPECS_RUNTIME="
for %%R in (py python3 python) do (
  if not defined FETCH_SPECS_RUNTIME (
    where %%R >nul 2>nul && (
      rem %%~R is the candidate itself: py, python3 or python, in this order
      %%~R "%~dp0fetch-specs.py" --probe >nul 2>nul
      if not errorlevel 1 (
        set "FETCH_SPECS_RUNTIME=%%~R"
      ) else (
        rem 127 = no interpreter found, anything else = a python whose own
        rem verdict belongs to the caller: in both cases say why and go on
        echo Note: %%R did not pass the probe of fetch-specs.py 1>&2
      )
    )
  )
)
if not defined FETCH_SPECS_RUNTIME (
  echo Error: no working python interpreter found ^(tried py, python3, python^) 1>&2
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
