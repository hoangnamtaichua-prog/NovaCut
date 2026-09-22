@echo off
setlocal
title NovaCut - AI Video and Review Editor

cd /d "%~dp0"

echo ============================================================
echo   NOVACUT - HE THONG BIEN TAP VIDEO VA REVIEW PHIM AI
echo ============================================================
echo.

:: 1. Uu tien them thu muc bin vao PATH (FFmpeg, ffprobe)
if exist "%~dp0bin" set "PATH=%~dp0bin;%PATH%"

:: 2. Kiem tra va lua chon trinh thuc thi Python phu hop
set PYTHON_EXE=

python --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_EXE=python
    goto :RUN_APP
)

py -3 --version >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    set PYTHON_EXE=py -3
    goto :RUN_APP
)

if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    set PYTHON_EXE="%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
    goto :RUN_APP
)
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set PYTHON_EXE="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
    goto :RUN_APP
)
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set PYTHON_EXE="%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
    goto :RUN_APP
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set PYTHON_EXE="%ProgramFiles%\Python312\python.exe"
    goto :RUN_APP
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set PYTHON_EXE="%ProgramFiles%\Python311\python.exe"
    goto :RUN_APP
)
if exist "%ProgramFiles%\Python310\python.exe" (
    set PYTHON_EXE="%ProgramFiles%\Python310\python.exe"
    goto :RUN_APP
)
if exist "%~dp0runtimes\python\python.exe" (
    set PYTHON_EXE="%~dp0runtimes\python\python.exe"
    goto :RUN_APP
)
if exist "%~dp0python-nuget\python.exe" (
    set PYTHON_EXE="%~dp0python-nuget\python.exe"
    goto :RUN_APP
)

:NOT_FOUND
echo [LOI] Khong tim thay Python tren may tinh cua ban!
echo Vui long cai dat Python (khuyen nghi 3.10 - 3.12) va tich chon "Add python.exe to PATH".
echo.
pause
exit /b 1

:RUN_APP
echo [INFO] Trinh thuc thi Python: %PYTHON_EXE%
echo [INFO] Dang khoi chay ung dung NovaCut...
echo.

%PYTHON_EXE% web_app.py %*

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ============================================================
    echo [CANH BAO] Ung dung da dung lai voi ma thoat: %ERRORLEVEL%
    echo ============================================================
    echo.
    pause
)
