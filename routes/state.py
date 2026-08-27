import os
import subprocess
import sys
import mimetypes
import json
import logging
import traceback
import re
import time
import threading
import asr_manager
from platformdirs import user_data_dir
from flask import Flask, send_from_directory, Response, jsonify, request, send_file

def get_app_root_dir():
    """Xác định chính xác tuyệt đối thư mục gốc của ứng dụng NovaCut."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr and os.path.dirname(curr) != curr:
        if os.path.exists(os.path.join(curr, 'web', 'index.html')):
            norm_curr = os.path.normpath(curr).lower()
            if not norm_curr.endswith(os.path.normpath('patches/active').lower()) and not norm_curr.endswith(os.path.normpath('release/novacut').lower()):
                return os.path.abspath(curr)
        curr = os.path.dirname(curr)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Project Root Directory
ROOT_DIR = get_app_root_dir()
USER_DATA_DIR = user_data_dir('NovaCut', 'NovaCut', roaming=True)
os.makedirs(USER_DATA_DIR, exist_ok=True)
current_export_process = None
STOP_OCR_FLAG = False
review_stop_flag = False
API_KEYS_FILE = os.path.join(USER_DATA_DIR, 'api_keys.txt')
current_asr_process = None

def _time_to_seconds(t_str):
    try:
        t_str = str(t_str).strip().replace(',', '.')
        parts = t_str.split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return float(t_str)
    except Exception:
        return 0.0
