# -*- coding: utf-8 -*-
"""
Hệ thống Quản lý Lưu & Mở Dự án (.amsproj) cho AI-Movie-Shorts.
Cho phép lưu lại toàn bộ tiến trình: Video, Phụ đề, Giọng đọc, Căn chỉnh khung hình, Logo, BGM.
"""

import os
import json
import time
import glob
import re
from datetime import datetime
from flask import Blueprint, jsonify, request, send_file, Response
from routes.state import ROOT_DIR, USER_DATA_DIR
from routes.security import atomic_write_json, is_path_allowed, safe_join
PROJECTS_DIR = os.path.join(USER_DATA_DIR, 'projects')
os.makedirs(PROJECTS_DIR, exist_ok=True)

project_bp = Blueprint('project', __name__)

def _sanitize_filename(name):
    """Làm sạch tên dự án để làm tên file hợp lệ trên Windows/Linux."""
    clean = re.sub(r'[\\/*?:"<>|]', '_', str(name).strip())
    clean = re.sub(r'\s+', '_', clean)
    return clean or "Du_An_Moi"

@project_bp.route('/api/project/list', methods=['GET'])
def list_projects():
    """Liệt kê tất cả các dự án đã lưu trong thư mục projects/."""
    try:
        project_files = glob.glob(os.path.join(PROJECTS_DIR, '*.amsproj'))
        project_files += glob.glob(os.path.join(PROJECTS_DIR, '*.json'))
        # Loại bỏ trùng lặp nếu có
        project_files = list(set(project_files))
        
        projects = []
        for p_path in project_files:
            try:
                fname = os.path.basename(p_path)
                is_autosave = (fname == '_autosave.amsproj' or fname == '_autosave.json')
                
                stat = os.stat(p_path)
                modified_time = stat.st_mtime
                file_size = stat.st_size
                
                with open(p_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                p_name = data.get('project_name') or os.path.splitext(fname)[0]
                if is_autosave:
                    p_name = "⚡ [Bản nháp tự động lưu] " + (data.get('project_name') or "Chưa đặt tên")

                video_info = data.get('video') or {}
                video_name = video_info.get('filename') or (os.path.basename(video_info.get('path', '')) if video_info.get('path') else 'Chưa có video')
                sub_count = len(data.get('subtitles') or [])
                
                projects.append({
                    "filename": fname,
                    "filepath": p_path,
                    "project_id": data.get('project_id', fname),
                    "project_name": p_name,
                    "is_autosave": is_autosave,
                    "video_name": video_name,
                    "video_path": video_info.get('path', ''),
                    "subtitles_count": sub_count,
                    "tts_voice": (data.get('tts_voice') or {}).get('voice_id', ''),
                    "created_at": data.get('created_at') or datetime.fromtimestamp(stat.st_ctime).strftime('%d/%m/%Y %H:%M'),
                    "updated_at": data.get('updated_at') or datetime.fromtimestamp(modified_time).strftime('%d/%m/%Y %H:%M'),
                    "modified_epoch": modified_time,
                    "file_size_kb": round(file_size / 1024, 1)
                })
            except Exception as read_err:
                print(f"Lỗi đọc file dự án {p_path}: {read_err}")
                continue
                
        # Sắp xếp dự án mới chỉnh sửa lên đầu tiên
        projects.sort(key=lambda x: (not x['is_autosave'], x['modified_epoch']), reverse=True)
        return jsonify({"success": True, "projects": projects, "count": len(projects)})
    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi liệt kê dự án: {str(e)}"}), 500

@project_bp.route('/api/project/save', methods=['POST'])
def save_project():
    """Lưu dự án hiện tại vào file .amsproj (tại filepath chỉ định hoặc trong thư mục projects/)."""
    try:
        data = request.get_json(silent=True) or {}
        project_name = data.get('project_name', '').strip() or 'Du_An_Moi'
        safe_name = _sanitize_filename(project_name)
        
        target_filepath = data.get('filepath') or data.get('target_filepath')
        if target_filepath and os.path.isabs(target_filepath):
            filepath = os.path.normpath(target_filepath)
            filename = os.path.basename(filepath)
            if project_name == 'Du_An_Moi':
                project_name = os.path.splitext(filename)[0]
                safe_name = _sanitize_filename(project_name)
        else:
            filename = f"{safe_name}.amsproj"
            filepath = os.path.join(PROJECTS_DIR, filename)
        
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        data['updated_at'] = now_str
        if not data.get('created_at'):
            data['created_at'] = now_str
        if not data.get('project_id'):
            data['project_id'] = f"proj_{int(time.time())}_{safe_name}"
            
        data['project_name'] = project_name
        data['filename'] = filename
        data['filepath'] = filepath
        data['format_version'] = "1.0"
        data['app_version'] = "2026.8"

        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Tạo bản sao lưu trong projects/ để hiển thị danh sách gần đây
        internal_path = os.path.join(PROJECTS_DIR, f"{safe_name}.amsproj")
        if os.path.normpath(filepath) != os.path.normpath(internal_path):
            try:
                with open(internal_path, 'w', encoding='utf-8') as f_copy:
                    json.dump(data, f_copy, ensure_ascii=False, indent=2)
            except Exception:
                pass
            
        return jsonify({
            "success": True,
            "message": f"Đã lưu dự án '{project_name}' thành công!",
            "filename": filename,
            "filepath": filepath,
            "updated_at": now_str
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi lưu dự án: {str(e)}"}), 500

@project_bp.route('/api/project/load', methods=['POST'])
def load_project():
    """Nạp dữ liệu dự án từ file chỉ định (filepath hoặc filename)."""
    try:
        req_data = request.get_json(silent=True) or {}
        filename = req_data.get('filename', '').strip()
        filepath = req_data.get('filepath', '').strip()
        
        target_path = None
        if filepath and os.path.exists(filepath):
            target_path = filepath
        elif filename:
            cand = os.path.join(PROJECTS_DIR, filename)
            if os.path.exists(cand):
                target_path = cand
                
        if not target_path or not os.path.exists(target_path):
            return jsonify({"success": False, "error": "Không tìm thấy file dự án yêu cầu!"}), 404
            
        with open(target_path, 'r', encoding='utf-8') as f:
            project_data = json.load(f)
            
        project_data['filename'] = os.path.basename(target_path)
        project_data['filepath'] = target_path

        # Tự động sao chép vào projects/ nếu mở từ ngoài để lưu vào danh sách gần đây
        safe_name = _sanitize_filename(project_data.get('project_name', os.path.splitext(os.path.basename(target_path))[0]))
        internal_path = os.path.join(PROJECTS_DIR, f"{safe_name}.amsproj")
        if os.path.normpath(target_path) != os.path.normpath(internal_path):
            try:
                with open(internal_path, 'w', encoding='utf-8') as f_copy:
                    json.dump(project_data, f_copy, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return jsonify({
            "success": True,
            "project": project_data,
            "filename": os.path.basename(target_path),
            "filepath": target_path
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi nạp dự án: {str(e)}"}), 500

@project_bp.route('/api/project/delete', methods=['POST'])
def delete_project():
    """Xóa dự án khỏi thư mục projects/."""
    try:
        req_data = request.get_json(silent=True) or {}
        filename = req_data.get('filename', '').strip()
        if not filename:
            return jsonify({"success": False, "error": "Thiếu tên file cần xóa"}), 400
            
        target_path = os.path.join(PROJECTS_DIR, filename)
        if os.path.exists(target_path):
            os.remove(target_path)
            return jsonify({"success": True, "message": f"Đã xóa dự án {filename}!"})
        else:
            return jsonify({"success": False, "error": "File không tồn tại"}), 404
    except Exception as e:
        return jsonify({"success": False, "error": f"Lỗi xóa dự án: {str(e)}"}), 500

@project_bp.route('/api/project/autosave', methods=['POST'])
def autosave_project():
    """Tự động lưu nháp phiên làm việc vào _autosave.amsproj."""
    try:
        data = request.get_json(silent=True) or {}
        filepath = os.path.join(PROJECTS_DIR, '_autosave.amsproj')
        
        now_str = datetime.now().strftime('%d/%m/%Y %H:%M:%S')
        data['updated_at'] = now_str
        data['is_autosave'] = True
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"success": True, "saved_at": now_str})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@project_bp.route('/api/project/export_file', methods=['POST'])
def export_file():
    """Trả về file .amsproj để tải về máy tính."""
    try:
        data = request.get_json(silent=True) or {}
        p_name = data.get('project_name') or 'Du_An'
        safe_name = _sanitize_filename(p_name)
        
        content = json.dumps(data, ensure_ascii=False, indent=2)
        response = Response(
            content,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment;filename={safe_name}.amsproj"}
        )
        return response
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
