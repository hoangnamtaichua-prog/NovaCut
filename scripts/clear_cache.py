# -*- coding: utf-8 -*-
"""
NovaCut Cache Cleaner
Dọn dẹp sạch toàn bộ Cache WebView2, Cache Pywebview và Temporary Data trên Windows.
"""

import os
import sys
import shutil
import glob

if sys.stdout is not None:
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def clear_all_cache():
    print("=" * 60)
    print("🧹 NOVACUT CACHE CLEANER - DỌN DẸP CACHE TOÀN DIỆN")
    print("=" * 60)

    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # 1. Dọn dẹp __pycache__ trong thư mục dự án
    pycache_count = 0
    for root, dirs, files in os.walk(root_dir):
        for d in dirs:
            if d == '__pycache__':
                full_path = os.path.join(root, d)
                try:
                    shutil.rmtree(full_path, ignore_errors=True)
                    pycache_count += 1
                except Exception:
                    pass
    print(f"✅ Đã dọn dẹp {pycache_count} thư mục __pycache__ cục bộ.")

    # 2. Dọn dẹp Cache WebView2 / Microsoft Edge Runtime
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    temp_dir = os.environ.get('TEMP', '')
    
    cache_targets = [
        os.path.join(local_app_data, 'Microsoft', 'EdgeWebView'),
        os.path.join(local_app_data, 'pywebview'),
        os.path.join(root_dir, 'EBWebView'),
        os.path.join(root_dir, '.pywebview')
    ]

    # Tìm thêm các thư mục tạm pywebview trong %TEMP%
    for f in glob.glob(os.path.join(temp_dir, '*webview*')):
        cache_targets.append(f)
    for f in glob.glob(os.path.join(temp_dir, '*pywebview*')):
        cache_targets.append(f)

    cleaned_targets = 0
    for target in cache_targets:
        if os.path.exists(target):
            try:
                if os.path.isdir(target):
                    shutil.rmtree(target, ignore_errors=True)
                else:
                    os.remove(target)
                print(f"🗑️ Đã xóa cache: {target}")
                cleaned_targets += 1
            except Exception as e:
                print(f"⚠️ Không thể xóa {target}: {e}")

    print(f"✅ Đã dọn dẹp xong {cleaned_targets} vùng bộ nhớ đệm WebView2.")
    print("=" * 60)
    print("🎉 DỌN DẸP CACHE HOÀN TẤT! BẠN CÓ THỂ MỞ LẠI APP ĐỂ NẠP CODE MỚI NHẤT.")
    print("=" * 60)

if __name__ == '__main__':
    clear_all_cache()
