@echo off
rem Starts ConsentGuard: one server shows both the website and the API.
rem Double-click this file, then use the browser window that opens.
cd /d "%~dp0backend"
if not exist "..\frontend\dist\index.html" (
    echo Building the website first...
    pushd ..\frontend
    call npm run build
    popd
)
start "" http://127.0.0.1:5000
echo ConsentGuard is running at http://127.0.0.1:5000  (close this window to stop it)
.venv\Scripts\python.exe app.py
