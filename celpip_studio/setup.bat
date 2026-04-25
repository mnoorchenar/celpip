@echo off
echo Installing CELPIP Studio dependencies...
cd /d "%~dp0"
pip install -r requirements.txt
echo Done! Run run.bat to start the app.
pause
