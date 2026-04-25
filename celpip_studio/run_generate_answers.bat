@echo off
echo ============================================================
echo  CELPIP Band 9-10 Answer Generator
echo ============================================================

REM Set your API key here (or set it in your system environment variables)
REM set ANTHROPIC_API_KEY=your-key-here

if "%ANTHROPIC_API_KEY%"=="" (
    echo.
    echo ERROR: ANTHROPIC_API_KEY is not set.
    echo.
    echo Option 1: Edit this file and uncomment the line above.
    echo Option 2: Run this in your terminal first:
    echo           set ANTHROPIC_API_KEY=your-key-here
    echo.
    pause
    exit /b 1
)

REM Install anthropic if not already installed
pip show anthropic >nul 2>&1
if errorlevel 1 (
    echo Installing anthropic SDK...
    pip install anthropic
)

echo.
echo Starting generation...
echo.
python generate_answers.py

echo.
pause
