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
from flask import Blueprint, jsonify, request
import audio_separator
import license_manager

audio_bp = Blueprint('audio', __name__)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Trạng thái tiến trình tách âm thanh
_separation_progress = {
    "is_processing": False,
    "percent": 0,
    "message": "",
    "status": "idle",
    "result": None,
    "error": None
}


@audio_bp.route('/api/audio/separate', methods=['POST'])
def api_separate_audio():
    """
    Endpoint thực hiện Tách Âm Thanh AI & Lọc Giọng Thoại Cũ từ Video / Audio.
    """
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'success': False, 'error': perm_msg}), 403

    data = request.get_json(silent=True) or {}
    media_path = data.get('media_path', '').strip()
    mode = data.get('mode', 'ai_neural').strip() # 'ai_neural' or 'dsp_turbo'
    remove_vocals = bool(data.get('remove_vocals', True))
    remove_bgm = bool(data.get('remove_bgm', False))
    keep_sfx = bool(data.get('keep_sfx', True))

    if not media_path:
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp đường dẫn video hoặc audio.'}), 400

    if not os.path.isabs(media_path):
        media_path = os.path.join(ROOT_DIR, media_path)

    if not os.path.exists(media_path):
        return jsonify({'success': False, 'error': f'Không tìm thấy file: {media_path}'}), 404

    global _separation_progress
    _separation_progress["is_processing"] = True
    _separation_progress["percent"] = 5
    _separation_progress["message"] = "Đang khởi tạo bộ tách âm thanh AI..."
    _separation_progress["status"] = "processing"
    _separation_progress["error"] = None
    _separation_progress["result"] = None

    def _progress_cb(pct, msg):
        global _separation_progress
        _separation_progress["percent"] = pct
        _separation_progress["message"] = msg

    try:
        res = audio_separator.separate_audio_stems(
            input_media_path=media_path,
            remove_vocals=remove_vocals,
            remove_bgm=remove_bgm,
            keep_sfx=keep_sfx,
            mode=mode,
            progress_cb=_progress_cb
        )

        cleaned_path = res.get('cleaned_path', '')
        vocals_path = res.get('vocals_path', '')
        inst_path = res.get('instrumental_path', '')

        result_payload = {
            "success": True,
            "mode": mode,
            "cleaned_path": cleaned_path,
            "cleaned_url": f"/api/file?path={urllib.parse.quote(cleaned_path)}" if cleaned_path else "",
            "vocals_path": vocals_path,
            "vocals_url": f"/api/file?path={urllib.parse.quote(vocals_path)}" if vocals_path else "",
            "instrumental_path": inst_path,
            "instrumental_url": f"/api/file?path={urllib.parse.quote(inst_path)}" if inst_path else "",
            "message": "🎉 Đã tách và lọc âm thanh AI thành công!"
        }

        _separation_progress["is_processing"] = False
        _separation_progress["percent"] = 100
        _separation_progress["status"] = "completed"
        _separation_progress["message"] = "Hoàn tất tách âm thanh!"
        _separation_progress["result"] = result_payload

        return jsonify(result_payload)

    except Exception as e:
        _separation_progress["is_processing"] = False
        _separation_progress["status"] = "error"
        _separation_progress["error"] = str(e)
        _separation_progress["message"] = f"Lỗi tách âm thanh: {str(e)}"
        return jsonify({'success': False, 'error': str(e)}), 500


@audio_bp.route('/api/audio/separate/progress', methods=['GET'])
def api_separate_progress():
    """Lấy tiến trình tách âm thanh thời gian thực."""
    global _separation_progress
    return jsonify(_separation_progress)
