@echo off
chcp 65001 >nul
title NovaCut - Dọn Dẹp Bộ Nhớ Đệm Cache
echo ============================================================
echo 🧹 DANG XOA SACH TOAN BO CACHE HE THONG & WEBVIEW2...
echo ============================================================
python scripts\clear_cache.py
echo.
pause
