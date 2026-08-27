# -*- coding: utf-8 -*-
"""
Routes API AI Audio Stem & Vocal Separation
Cung cấp API Tách Âm Thanh, Lọc Bỏ Giọng Thoại Cũ, Xóa Nhạc Nền BGM & Giữ Lại Âm Gốc / Hiệu Ứng SFX.
"""

import os
import sys
import time
import json
import urllib.parse
import threading
from flask import Blueprint, jsonify, request, Response
import os, json, threading, time, traceback
from routes.state import *
import license_manager
from routes.security import is_path_allowed, parse_bool
import audio_separator

audio_bp = Blueprint('audio', __name__)

# Trạng thái tiến trình tách âm thanh & Cờ dừng khẩn cấp
_cancel_requested = False
_separation_lock = threading.Lock()
_separation_progress = {
    "is_processing": False,
    "percent": 0,
    "message": "",
    "status": "idle",
    "device": "auto",
    "mode": "mdx_net_hq4",
    "logs": [],
    "result": None,
    "error": None
}


def _add_log(msg):
    """Ghi log hệ thống kèm mốc thời gian."""
    global _separation_progress
    timestamp = time.strftime('%H:%M:%S')
    formatted = f"[{timestamp}] {msg}"
    _separation_progress["logs"].append(formatted)
    if len(_separation_progress["logs"]) > 100:
        _separation_progress["logs"] = _separation_progress["logs"][-100:]
    print(formatted)


def _run_separation_worker(media_path, mode, device, remove_vocals, remove_bgm, keep_sfx):
    """Luồng worker chạy ngầm xử lý tách âm thanh, không làm nghẽn Flask server."""
    global _cancel_requested, _separation_progress
    def _progress_cb(pct, msg):
        global _separation_progress
        _separation_progress["percent"] = pct
        _separation_progress["message"] = msg

    def _logger_cb(msg):
        _add_log(msg)

    def _cancel_check():
        global _cancel_requested
        return _cancel_requested

    try:
        res = audio_separator.separate_audio_stems(
            input_media_path=media_path,
            remove_vocals=remove_vocals,
            remove_bgm=remove_bgm,
            keep_sfx=keep_sfx,
            mode=mode,
            device=device,
            progress_cb=_progress_cb,
            logger_cb=_logger_cb,
            cancel_check_cb=_cancel_check
        )

        cleaned_path = res.get('cleaned_path', '')
        vocals_path = res.get('vocals_path', '')
        inst_path = res.get('instrumental_path', '')

        result_payload = {
            "success": True,
            "mode": mode,
            "device": res.get("device", device),
            "cleaned_path": cleaned_path,
            "cleaned_url": f"/api/file?path={urllib.parse.quote(cleaned_path)}" if cleaned_path else "",
            "vocals_path": vocals_path,
            "vocals_url": f"/api/file?path={urllib.parse.quote(vocals_path)}" if vocals_path else "",
            "instrumental_path": inst_path,
            "instrumental_url": f"/api/file?path={urllib.parse.quote(inst_path)}" if inst_path else "",
            "message": "🎉 Đã tách và lọc âm thanh AI thành công!"
        }

        _add_log("✅ Hoàn tất tách và xuất file âm thanh thành công!")
        _separation_progress["is_processing"] = False
        _separation_progress["percent"] = 100
        _separation_progress["status"] = "completed"
        _separation_progress["message"] = "Hoàn tất tách âm thanh!"
        _separation_progress["result"] = result_payload

    except Exception as e:
        is_cancelled = "dừng tác vụ" in str(e).lower() or _cancel_requested
        _separation_progress["is_processing"] = False
        _separation_progress["status"] = "cancelled" if is_cancelled else "error"
        _separation_progress["error"] = str(e)
        _separation_progress["message"] = "🛑 Đã dừng khẩn cấp theo yêu cầu." if is_cancelled else f"Lỗi: {str(e)}"
        _add_log(f"⚠️ {_separation_progress['message']}")


@audio_bp.route('/api/audio/separate', methods=['POST'])
def api_separate_audio():
    """
    Endpoint thực hiện Tách Âm Thanh AI & Lọc Giọng Thoại Cũ từ Video / Audio.
    Hỗ trợ:
    - mode: 'mdx_net_hq4', 'mdx_net_hq5', 'ai_neural', 'dsp_turbo'
    - device: 'cuda', 'cpu', 'auto'
    - remove_vocals, remove_bgm, keep_sfx
    """
    global _cancel_requested, _separation_progress
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'success': False, 'error': perm_msg}), 403

    data = request.get_json(silent=True) or {}
    media_path = data.get('media_path', '').strip()
    mode = data.get('mode', 'mdx_net_hq4').strip()
    device = data.get('device', 'auto').strip()
    remove_vocals = parse_bool(data.get('remove_vocals'), True)
    remove_bgm = parse_bool(data.get('remove_bgm'), False)
    keep_sfx = parse_bool(data.get('keep_sfx'), True)

    if not media_path:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp đường dẫn video hoặc audio.'}), 400

    if not os.path.isabs(media_path):
        media_path = os.path.join(ROOT_DIR, media_path)

    if not os.path.exists(media_path):
        return jsonify({'success': False, 'error': f'Không tìm thấy file: {media_path}'}), 404

    _cancel_requested = False
    _separation_progress = {
        "is_processing": True,
        "percent": 5,
        "message": "Đang khởi tạo bộ tách âm thanh AI...",
        "status": "processing",
        "device": device,
        "mode": mode,
        "logs": [],
        "error": None,
        "result": None
    }

    _add_log(f"🚀 Bắt đầu tác vụ tách âm thanh (Mode: {mode}, Device: {device.upper()})...")

    # Khởi chạy luồng ngầm phi đồng bộ (Non-blocking) để Flask luôn lắng nghe lệnh Dừng khẩn cấp
    worker_thread = threading.Thread(
        target=_run_separation_worker,
        args=(media_path, mode, device, remove_vocals, remove_bgm, keep_sfx),
        daemon=True
    )
    worker_thread.start()

    return jsonify({"success": True, "status": "processing", "message": "Đã bắt đầu tiến trình tách âm thanh"})


@audio_bp.route('/api/audio/separate/cancel', methods=['GET', 'POST'])
def api_separate_cancel():
    """Dừng khẩn cấp tiến trình tách âm thanh."""
    global _cancel_requested, _separation_progress
    _cancel_requested = True
    _separation_progress["is_processing"] = False
    _separation_progress["status"] = "cancelled"
    _separation_progress["message"] = "🛑 Đang gửi tín hiệu dừng khẩn cấp..."
    _add_log("🛑 Người dùng nhấn [Dừng khẩn cấp]! Đang giải phóng bộ nhớ...")
    return jsonify({'success': True, 'message': 'Đã gửi yêu cầu dừng khẩn cấp.'})


@audio_bp.route('/api/audio/separate/progress', methods=['GET'])
def api_separate_progress():
    """Lấy tiến trình tách âm thanh & System log thời gian thực."""
    global _separation_progress
    return jsonify(_separation_progress)
