@echo off
setlocal
title Dhan Turnover Scanner
pushd "%~dp0"
if errorlevel 1 goto folder_error

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "scripts\launch_app.py"
    goto finished
)
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" "scripts\launch_app.py"
    goto finished
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "scripts\launch_app.py"
    goto finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python "scripts\launch_app.py"
    goto finished
)
echo Python was not found. Install Python 3.10 or newer, then run this launcher again.
goto wait_error

:finished
if errorlevel 1 goto wait_error
popd
exit /b 0

:folder_error
echo Could not open the app folder. Keep this batch file in the project folder.
pause
exit /b 1

:wait_error
echo.
echo The app could not start. See the message above.
pause
popd
exit /b 1
