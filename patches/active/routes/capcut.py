from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading
from routes.state import *
import asr_manager

capcut_bp = Blueprint('capcut', __name__)

@capcut_bp.route('/api/capcut/drafts', methods=['GET'])
def api_capcut_drafts():
    try:
        import capcut_sync
        drafts = capcut_sync.get_recent_drafts()
        installed = capcut_sync.is_capcut_installed() or len(drafts) > 0
        return jsonify({
            'success': True,
            'drafts': drafts,
            'has_capcut': installed,
            'message': 'Đã quét xong danh sách dự án CapCut.' if installed else 'Không tìm thấy CapCut PC trên máy này. Bạn có thể tải miễn phí tại capcut.com.'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@capcut_bp.route('/api/capcut/tracks', methods=['POST'])
def api_capcut_tracks():
    try:
        import capcut_sync
        data = request.json or {}
        draft_path = data.get('draft_path')
        if not draft_path:
            return jsonify({'success': False, 'error': 'Vui lòng chọn Dự án CapCut'}), 400
        result = capcut_sync.get_draft_video_tracks(draft_path)
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@capcut_bp.route('/api/capcut/sync', methods=['POST'])
def api_capcut_sync():
    try:
        import license_manager
        allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
        if not allowed:
            return jsonify({'success': False, 'error': perm_msg}), 403

        import capcut_sync
        data = request.json or {}
        draft_path = data.get('draft_path')
        target_track_id = data.get('target_track_id')
        short_video_action = data.get('short_video_action', 'slow')
        long_video_action = data.get('long_video_action', 'cut')
        custom_subtitles = data.get('subtitles')
        custom_srt_path = data.get('srt_path')
        relaunch = data.get('relaunch', True)
        
        if not draft_path:
            return jsonify({'success': False, 'error': 'Vui lòng chọn Dự án CapCut'}), 400
            
        result = capcut_sync.sync_video_with_srt(
            draft_path=draft_path,
            target_track_id=target_track_id,
            short_video_action=short_video_action,
            long_video_action=long_video_action,
            custom_srt_path=custom_srt_path,
            custom_subtitles=custom_subtitles
        )
        
        if result.get('success') and relaunch:
            capcut_sync.relaunch_capcut()
            
        return jsonify(result)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@capcut_bp.route('/api/capcut/open_folder', methods=['POST'])
def api_capcut_open_folder():
    import subprocess
    data = request.json or {}
    draft_path = data.get('draft_path')
    if draft_path and os.path.exists(draft_path):
        subprocess.Popen(f'explorer "{draft_path}"')
        return jsonify({'success': True})
    
    import capcut_sync
    drafts_dir = capcut_sync.get_capcut_drafts_dir()
    if os.path.exists(drafts_dir):
        subprocess.Popen(f'explorer "{drafts_dir}"')
    return jsonify({'success': True})

