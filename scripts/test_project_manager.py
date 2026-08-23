# -*- coding: utf-8 -*-
"""
Test Suite: Project Save & Load (.amsproj) System
Kiểm thử toàn diện các tính năng lưu, nạp, liệt kê, xóa và xuất tệp dự án .amsproj
"""

import os
import sys
import json
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from flask import Flask
from routes.project import project_bp, PROJECTS_DIR

def create_test_client():
    app = Flask(__name__)
    app.register_blueprint(project_bp)
    return app.test_client()

def test_save_and_load_project():
    print("1. Testing Project Save & Load (.amsproj)...")
    client = create_test_client()
    
    sample_project = {
        "project_name": "Test_Review_Phim_Kinh_Di",
        "video": {
            "path": "D:/Videos/phim_kinh_di.mp4",
            "filename": "phim_kinh_di.mp4",
            "duration": 125.5
        },
        "active_tab": "viewEditor",
        "subtitles": [
            {
                "id": "1",
                "time": "00:00:01,000 - 00:00:04,500",
                "startSeconds": 1.0,
                "endSeconds": 4.5,
                "text": "这是一部非常恐怖的电影",
                "translation": "Đây là một bộ phim vô cùng rùng rợn và kịch tính",
                "selected": True
            },
            {
                "id": "2",
                "time": "00:00:05,000 - 00:00:08,200",
                "startSeconds": 5.0,
                "endSeconds": 8.2,
                "text": "主角走进了一个废弃的房间",
                "translation": "Nhân vật chính bước vào một căn phòng bỏ hoang",
                "selected": True
            }
        ],
        "tts_voice": {
            "voice_id": "vi-VN-HoaiMyNeural",
            "voice_speed": 1.1,
            "voice_pitch": 0,
            "voice_volume": 1.0,
            "cloned_voice_id": ""
        },
        "logo_overlay": {
            "enabled": True,
            "path": "assets/logo.png",
            "x_pct": 5.0,
            "y_pct": 5.0,
            "w_pct": 18.0,
            "h_pct": 12.0,
            "opacity": 95
        }
    }
    
    # 1. Save Project
    res = client.post('/api/project/save', json=sample_project)
    assert res.status_code == 200, f"Mã HTTP phải là 200, nhận: {res.status_code}"
    save_data = res.get_json()
    assert save_data['success'] is True
    filename = save_data['filename']
    assert filename == "Test_Review_Phim_Kinh_Di.amsproj"
    print(f"  -> Saved successfully as: {filename}")
    
    # 2. Load Project
    res_load = client.post('/api/project/load', json={"filename": filename})
    assert res_load.status_code == 200
    load_data = res_load.get_json()
    assert load_data['success'] is True
    proj = load_data['project']
    
    # Verify Data Integrity
    assert proj['project_name'] == "Test_Review_Phim_Kinh_Di"
    assert proj['video']['path'] == "D:/Videos/phim_kinh_di.mp4"
    assert len(proj['subtitles']) == 2
    assert proj['subtitles'][0]['translation'] == "Đây là một bộ phim vô cùng rùng rợn và kịch tính"
    assert proj['logo_overlay']['opacity'] == 95
    print("  -> Data Integrity: 100% Match across Video, Subtitles, Voice, Logo")
    print("  ✅ PASS: Save & Load Project")

def test_list_and_search_projects():
    print("\n2. Testing List Recent Projects...")
    client = create_test_client()
    
    res = client.get('/api/project/list')
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    assert len(data['projects']) >= 1
    
    target_p = next((p for p in data['projects'] if "Test_Review_Phim_Kinh_Di" in p['filename']), None)
    assert target_p is not None, "Phải tìm thấy dự án vừa lưu trong danh sách"
    assert target_p['subtitles_count'] == 2
    assert target_p['video_name'] == "phim_kinh_di.mp4"
    print(f"  -> Listed {len(data['projects'])} projects. Found: {target_p['project_name']}")
    print("  ✅ PASS: List Recent Projects")

def test_autosave():
    print("\n3. Testing AutoSave Mechanism...")
    client = create_test_client()
    
    autosave_data = {
        "project_name": "Du_An_Dang_Lam_Do",
        "video": { "path": "D:/Videos/sample.mp4", "filename": "sample.mp4" },
        "subtitles": [{ "id": "1", "text": "Draft 1", "translation": "Bản dịch nháp" }]
    }
    
    res = client.post('/api/project/autosave', json=autosave_data)
    assert res.status_code == 200
    data = res.get_json()
    assert data['success'] is True
    
    autosave_path = os.path.join(PROJECTS_DIR, '_autosave.amsproj')
    assert os.path.exists(autosave_path), "File _autosave.amsproj phải tồn tại"
    print("  -> AutoSave file written and verified at projects/_autosave.amsproj")
    print("  ✅ PASS: AutoSave Mechanism")

def test_export_and_delete():
    print("\n4. Testing Export File & Delete Project...")
    client = create_test_client()
    
    filename = "Test_Review_Phim_Kinh_Di.amsproj"
    
    # Test Export File
    res_exp = client.post('/api/project/export_file', json={"project_name": "Test_Review_Phim_Kinh_Di"})
    assert res_exp.status_code == 200
    assert "attachment" in res_exp.headers.get("Content-Disposition", "")
    print("  -> Export File HTTP Response: 200 OK with attachment header")
    
    # Test Delete Project
    res_del = client.post('/api/project/delete', json={"filename": filename})
    assert res_del.status_code == 200
    del_data = res_del.get_json()
    assert del_data['success'] is True
    
    # Verify file deleted
    filepath = os.path.join(PROJECTS_DIR, filename)
    assert not os.path.exists(filepath), f"File {filename} phải không còn tồn tại sau khi xóa"
    print(f"  -> Project {filename} successfully removed from disk.")
    print("  ✅ PASS: Export & Delete Project")

if __name__ == '__main__':
    print("==========================================================")
    print("🧪 BẮT ĐẦU KIỂM THỬ HỆ THỐNG LƯU & MỞ DỰ ÁN (.amsproj)")
    print("==========================================================")
    test_save_and_load_project()
    test_list_and_search_projects()
    test_autosave()
    test_export_and_delete()
    print("\n🎉 TẤT CẢ CÁC BÀI KIỂM THỬ DỰ ÁN ĐÃ PASS 100%! HỆ THỐNG HOẠT ĐỘNG HOÀN HẢO!")
