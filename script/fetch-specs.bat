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
rem %%~R is the candidate itself: py, python3 or python, in this order -- with
rem an explicit .exe, because the $PATH lookup in :take matches exact file
rem names only (it does not try PATHEXT), so a bare "py" never matches py.exe.
rem One line per candidate, so "which one was asked" and "in what order" stay
rem readable.
for %%R in (py.exe python3.exe python.exe) do if not defined FETCH_SPECS_RUNTIME call :take %%~R
if not defined FETCH_SPECS_RUNTIME (
  echo Error: no python interpreter found in PATH ^(tried py, python3, python^) 1>&2
  exit /b 127
)
goto run

:take
rem %~1 is the candidate (py.exe, python3.exe, python.exe): take it if PATH has
rem it, and only that one. %~$PATH:1 is "where PATH resolves %~1 to", empty when
rem it is not there -- an exact-name search, hence the .exe in the candidates.
rem `if` is a plain comparison rather than another parenthesis block: a block
rem body is parsed whole before it runs, so the answer of *this* round would be
rem lost (same cmd rule that made the old probe skip a working candidate).
rem Single % here: this is a subroutine, not a for body -- %% would collapse to
rem a literal % and the check would never see the resolved path (that bug made
rem every candidate look missing and the entry reported "no python" on machines
rem that have it).
rem `where` is no better here: its "not found" is -1, and comparing that to 0
rem needs a parenthesis block again.
if "%~$PATH:1"=="" exit /b 0
set "FETCH_SPECS_RUNTIME=%~$PATH:1"
exit /b 0

:run
rem Run the logic code, then hold the window open: a dot-double-click gives us
rem a console window of our own (this .bat is already running inside it), and
rem it vanishes the moment this script exits -- progress lines and the failure
rem list would fly by unread (user's words: do not close the window when the
rem download finishes).
rem
rem Capture the status BEFORE the pause, and in THIS cmd instance. The old
rem nested form `cmd /c "python ... & pause"` could never pass the logic code's
rem exit code through: `cmd /c` returns the errorlevel of the LAST command on
rem the line, which is pause -- always 0 -- so a real failure (exit code 2,
rem missing config group) came back as 0. Running the interpreter directly in
rem this cmd keeps %errorlevel% pointing at the logic code when the `set` line
rem runs; pause then holds the window, and `exit /b` returns the saved status.
"%FETCH_SPECS_RUNTIME%" "%~dp0fetch-specs.py" %*
set "FETCH_SPECS_STATUS=%errorlevel%"
pause
exit /b %FETCH_SPECS_STATUS%
