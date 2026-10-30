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
rem you to install Python from the Store instead of running.
rem
rem So a candidate is used only after it passed the probe: --probe runs the
rem logic code and stops right after it parsed its own arguments (no download,
rem no write, no self-update, no restart). The judge is exit code 0 and nothing
rem else -- the probe exits 0 only when the logic code really ran to that point,
rem which is what separates "runs" from "does not run". Any other code means
rem the candidate did start and our logic code itself refused (bad arguments,
rem no home dir, network down); reporting that as "no python" would tell the
rem user their machine is broken when it is not.
rem
rem The probe keeps its output to nul: it describes a candidate still being
rem tried, and printing it makes a healthy machine look broken.
rem
rem Exit non-zero with a message when none of them runs -- do not run on
rem silently (.bat must be pure ASCII, so this stays English).
rem
rem One line per candidate, in the order above: "which one was asked" and "in
rem what order" stay readable, and the caller's %* is never re-parsed by a block
rem body -- it is passed through below unchanged.
setlocal
set "FETCH_SPECS_FOUND="
rem %%~R is the candidate itself: py, python3 or python, in this order.
rem One line per candidate, so "which one was asked" and "in what order" stay
rem readable. The call is a line of its own and NOT inside the for body: a
rem parenthesised body is parsed whole before it runs, so %%~R in it is not the
rem candidate of *this* round, and a variable the sub sets inside one is gone
rem once the block ends. :probe runs in the file scope instead, its answer
rem travels out in FETCH_SPECS_FOUND, and only a candidate whose probe exited
rem 0 sets it.
for %%R in (py python3 python) do if not defined FETCH_SPECS_FOUND call :probe %%~R
if not defined FETCH_SPECS_FOUND (
  echo Error: no working python interpreter found ^(tried py, python3, python^) 1>&2
  exit /b 127
)
set "FETCH_SPECS_RUNTIME=%FETCH_SPECS_FOUND%"
goto run

:probe
rem %%~1 is the candidate: probe that one, and only that one.
rem The probe is `call`-ed on purpose. A .cmd/.bat started without `call` does
rem not come back: the rest of this sub never runs and the exit code is
rem whatever the candidate left behind, so a plain "%~1" here turns every
rem working candidate into "did not pass" on a machine that has python.
rem
rem No `where` first: running it once IS the answer to "does this one run".
rem The probe's 0 is the only code that accepts a candidate: 2 is argparse'
rem complaint on a python that rejects --probe, 49 is a launcher with no python
rem 3 behind it, and anything else is the logic code's own verdict. None of
rem them means "this machine has no python", so the next candidate is simply
rem tried. Output stays in nul -- it describes a candidate still being tried.
call "%~1" "%~dp0fetch-specs.py" --probe >nul 2>nul
if errorlevel 1 exit /b 0
set "FETCH_SPECS_FOUND=%~1"
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
