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
from flask import Flask, send_from_directory, Response, jsonify, request, send_file

# Project Root Directory (Parent of routes/)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
current_export_process = None
STOP_OCR_FLAG = False
review_stop_flag = False
API_KEYS_FILE = os.path.join(ROOT_DIR, 'api_keys.txt')
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
