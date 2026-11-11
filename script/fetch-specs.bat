@echo off
rem fetch-specs - Windows entry (thin shell: locate the logic code, pass
rem arguments through unchanged, return its exit code unchanged)
rem
rem Interpreter lookup, in order: the "py" launcher, then a "python3" on PATH,
rem then a "python" on PATH. Use the first one found -- no probe.
rem
rem Do NOT "probe" a candidate before using it. Running the logic code once to
rem ask "does this interpreter work" is the wrong test on the machines this
rem entry exists for: that run imports the config and stops with exit code 2
rem when the config file next to this script is missing (a fresh landing dir, a
rem repo checkout), and a batch `for` body cannot see why a candidate failed.
rem Every candidate then looks broken and the user is told "no working python
rem interpreter found" on a machine that has python right there in PATH
rem (user's words: stop detecting, just take it from PATH). So: pick by PATH,
rem run the logic code for real, and let the logic code speak for itself --
rem it already reports what is missing (config, pathconfig, network) with a
rem readable message and exit code 2.
rem
rem Exit non-zero with a message when none of them is on PATH -- do not run on
rem silently (.bat must be pure ASCII, so this stays English).
rem
rem One line per candidate, in the order above: "which one was asked" and "in
rem what order" stay readable, and the caller's %* is never re-parsed by a block
rem body -- it is passed through below unchanged.
setlocal
set "FETCH_SPECS_RUNTIME="
rem %%~R is the candidate itself: py, python3 or python, in this order.
rem One line per candidate, so "which one was asked" and "in what order" stay
rem readable.
for %%R in (py python3 python) do if not defined FETCH_SPECS_RUNTIME call :take %%~R
if not defined FETCH_SPECS_RUNTIME (
  echo Error: no python interpreter found in PATH ^(tried py, python3, python^) 1>&2
  exit /b 127
)
goto run

:take
rem %%~1 is the candidate: take it if PATH has it, and only that one.
rem %%~$PATH:1 is "where PATH resolves %%~1 to", empty when it is not there.
rem `if` is `if defined` rather than another parenthesis block: a block body is
rem parsed whole before it runs, so the answer of *this* round would be lost
rem (same cmd rule that made the old probe skip a working candidate).
rem `where` is no better here: its "not found" is -1, and comparing that to 0
rem needs a parenthesis block again.
if not defined %%~$PATH:1 exit /b 0
set "FETCH_SPECS_RUNTIME=%~1"
exit /b 0

:run
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
