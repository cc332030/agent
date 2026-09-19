@echo off
python3 "%~dp0fetch-specs.py" %*
exit /b %errorlevel%
