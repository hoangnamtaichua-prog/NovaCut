import os
import json
import uuid
import time
import shutil
import subprocess
from datetime import timedelta

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def get_capcut_drafts_dirs():
    """Lấy danh sách các thư mục chứa Projects của CapCut PC và JianYing Pro (剪映)"""
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    if not local_app_data:
        local_app_data = os.path.expanduser('~\\AppData\\Local')
        
    candidates = [
        os.path.join(local_app_data, 'CapCut', 'User Data', 'Projects', 'com.lveditor.draft'),
        os.path.join(local_app_data, 'JianyingPro', 'User Data', 'Projects', 'com.lveditor.draft'),
        r"D:\CapCut\User Data\Projects\com.lveditor.draft",
        r"D:\JianyingPro\User Data\Projects\com.lveditor.draft",
        r"E:\CapCut\User Data\Projects\com.lveditor.draft",
        r"E:\JianyingPro\User Data\Projects\com.lveditor.draft",
    ]
    existing = [c for c in candidates if os.path.exists(c)]
    if not existing:
        return [candidates[0]]
    return existing

def is_capcut_installed():
    """Kiểm tra xem máy tính đã cài đặt CapCut PC hoặc JianYing Pro hay chưa"""
    local_app_data = os.environ.get('LOCALAPPDATA', '')
    candidates = [
        os.path.join(local_app_data, 'CapCut', 'Apps', 'CapCut.exe'),
        os.path.join(local_app_data, 'JianyingPro', 'Apps', 'JianyingPro.exe'),
    ]
    for c in candidates:
        if os.path.exists(c):
            return True
    # Kiểm tra trong thư mục User Data Projects
    for d in get_capcut_drafts_dirs():
        if os.path.exists(d):
            return True
    return False

def get_recent_drafts():
    """Lấy danh sách các dự án CapCut PC và JianYing Pro gần nhất"""
    draft_dirs = get_capcut_drafts_dirs()
    drafts = []
    seen_paths = set()
    
    for drafts_dir in draft_dirs:
        if os.path.exists(drafts_dir):
            for folder_name in os.listdir(drafts_dir):
                folder_path = os.path.join(drafts_dir, folder_name)
                if os.path.isdir(folder_path) and folder_path not in seen_paths:
                    seen_paths.add(folder_path)
                    draft_content_path = os.path.join(folder_path, 'draft_content.json')
                    draft_meta_path = os.path.join(folder_path, 'draft_meta_info.json')
                    
                    if os.path.exists(draft_content_path):
                        draft_name = folder_name
                        cover_path = None
                        duration = 0
                        
                        # Lấy thông tin chi tiết từ meta_info nếu có
                        if os.path.exists(draft_meta_path):
                            try:
                                with open(draft_meta_path, 'r', encoding='utf-8') as f:
                                    meta = json.load(f)
                                    draft_name = meta.get('draft_name', folder_name)
                                    duration = meta.get('draft_duration', 0)
                                    if meta.get('draft_cover'):
                                        c_p = os.path.join(folder_path, meta.get('draft_cover'))
                                        if os.path.exists(c_p):
                                            cover_path = c_p
                            except Exception:
                                pass
                                
                        # Nếu chưa có cover, tìm file png/jpg trong folder
                        if not cover_path:
                            for ext in ['.jpg', '.png', '.jpeg']:
                                c_cand = os.path.join(folder_path, f'draft_cover{ext}')
                                if os.path.exists(c_cand):
                                    cover_path = c_cand
                                    break
                        
                        mtime = os.path.getmtime(draft_content_path)
                        time_str = time.strftime('%d/%m/%Y %H:%M', time.localtime(mtime))
                        
                        app_type = "JianYing" if "Jianying" in drafts_dir else "CapCut"
                        drafts.append({
                            'id': folder_name,
                            'name': f"{draft_name} ({app_type})" if len(draft_dirs) > 1 else draft_name,
                            'path': folder_path,
                            'mtime': mtime,
                            'time_str': time_str,
                            'cover': cover_path,
                            'duration': round(duration / 1000000.0, 1) if duration else 0
                        })
    
    drafts.sort(key=lambda x: x.get('mtime', 0), reverse=True)
    return drafts

def get_draft_video_tracks(draft_path):
    """
    Lấy danh sách các track video và thống kê trong một draft CapCut
    """
    draft_content_path = os.path.join(draft_path, 'draft_content.json')
    if not os.path.exists(draft_content_path):
        return {"success": False, "error": "Không tìm thấy file draft_content.json"}
    
    try:
        with open(draft_content_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        video_tracks = []
        text_track_count = 0
        total_subtitles = 0
        
        # Thống kê materials
        video_materials = {m['id']: m for m in data.get('materials', {}).get('videos', [])}
        image_materials = {m['id']: m for m in data.get('materials', {}).get('images', [])}
        
        for i, track in enumerate(data.get('tracks', [])):
            t_type = track.get('type')
            if t_type == 'video':
                segments = track.get('segments', [])
                video_count = 0
                photo_count = 0
                for s in segments:
                    m_id = s.get('material_id')
                    mat = video_materials.get(m_id) or image_materials.get(m_id, {})
                    if mat.get('type') == 'photo' or m_id in image_materials:
                        photo_count += 1
                    else:
                        video_count += 1
                        
                video_tracks.append({
                    "id": track.get('id', str(i)),
                    "index": i,
                    "segment_count": len(segments),
                    "video_count": video_count,
                    "photo_count": photo_count,
                    "flag": track.get('flag', 0)
                })
            elif t_type == 'text':
                text_track_count += 1
                total_subtitles += len(track.get('segments', []))
        
        return {
            "success": True,
            "tracks": video_tracks,
            "text_tracks": text_track_count,
            "total_subtitles": total_subtitles
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

def parse_srt_file(srt_path):
    """Đọc file SRT và chuyển thành danh sách các block thời gian (microsecond)"""
    if not os.path.exists(srt_path):
        return []
    
    with open(srt_path, 'r', encoding='utf-8-sig', errors='replace') as f:
        content = f.read()
        
    blocks = []
    # Regex parse SRT: 00:00:01,200 --> 00:00:04,500
    pattern = re.compile(r'(\d+)\s*\n(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})')
    
    def time_to_us(t_str):
        t_str = t_str.replace(',', '.')
        parts = t_str.split(':')
        h = int(parts[0])
        m = int(parts[1])
        s_parts = parts[2].split('.')
        s = int(s_parts[0])
        ms = int(s_parts[1]) if len(s_parts) > 1 else 0
        return int((h * 3600 + m * 60 + s) * 1000000 + ms * 1000)
        
    for m in pattern.finditer(content):
        start_us = time_to_us(m.group(2))
        end_us = time_to_us(m.group(3))
        blocks.append({
            'start': start_us,
            'duration': end_us - start_us
        })
        
    return blocks

def sync_video_with_srt(draft_path, target_track_id=None, short_video_action="slow", long_video_action="cut", custom_srt_path=None, custom_subtitles=None):
    """
    Đồng bộ video trên track CapCut với phụ đề.
    short_video_action: 'slow' (làm chậm khớp 100% SRT), 'gap' (giữ nguyên để khoảng trống)
    long_video_action: 'cut' (cắt ngắn vừa SRT), 'fast' (tua nhanh giữ toàn bộ cảnh)
    """
    draft_content_path = os.path.join(draft_path, 'draft_content.json')
    backup_path = os.path.join(draft_path, 'draft_content.json.bak2')
    
    if not os.path.exists(draft_content_path):
        return {"success": False, "error": "Không tìm thấy file draft_content.json trong dự án."}
        
    # Tạo bản sao lưu an toàn
    try:
        shutil.copy2(draft_content_path, backup_path)
    except Exception as e:
        print(f"Backup warning: {e}")
    
    try:
        with open(draft_content_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            
        srt_blocks = []
        
        # 1. Xác định nguồn phụ đề
        if custom_subtitles and len(custom_subtitles) > 0:
            # Dùng phụ đề truyền từ Tab Biên tập phim
            for sub in custom_subtitles:
                def str_to_us(t_val):
                    if isinstance(t_val, (int, float)):
                        return int(t_val * 1000000)
                    t_str = str(t_val).replace(',', '.')
                    parts = t_str.split(':')
                    if len(parts) == 3:
                        h = int(parts[0])
                        m = int(parts[1])
                        s = float(parts[2])
                        return int((h * 3600 + m * 60 + s) * 1000000)
                    return 0
                s_start = str_to_us(sub.get('start', 0))
                s_end = str_to_us(sub.get('end', 0))
                if s_end > s_start:
                    srt_blocks.append({'start': s_start, 'duration': s_end - s_start})
        elif custom_srt_path and os.path.exists(custom_srt_path):
            srt_blocks = parse_srt_file(custom_srt_path)
        else:
            # Tìm track text/phụ đề nội bộ trong dự án CapCut
            text_track = None
            max_text_segments = -1
            for track in data.get('tracks', []):
                if track.get('type') == 'text':
                    seg_count = len(track.get('segments', []))
                    if seg_count > max_text_segments:
                        text_track = track
                        max_text_segments = seg_count
                        
            if not text_track or max_text_segments == 0:
                return {"success": False, "error": "Dự án CapCut chưa có Track Phụ đề (Text/SRT). Vui lòng thêm phụ đề trong CapCut hoặc chọn nguồn phụ đề từ Tab Biên tập phim."}
                
            # Trích xuất timerange từ text track
            for seg in text_track.get('segments', []):
                tr = seg.get('target_timerange', {})
                start = tr.get('start', 0)
                duration = tr.get('duration', 0)
                if duration > 0:
                    srt_blocks.append({'start': start, 'duration': duration})
                    
        if not srt_blocks:
            return {"success": False, "error": "Không tìm thấy câu phụ đề nào để đồng bộ."}
            
        # Sắp xếp phụ đề theo thời gian
        srt_blocks.sort(key=lambda x: x['start'])
        
        # 2. Tìm video track mục tiêu
        video_track = None
        for i, track in enumerate(data.get('tracks', [])):
            if track.get('type') == 'video':
                if target_track_id is not None:
                    if str(track.get('id', '')) == str(target_track_id) or str(i) == str(target_track_id):
                        video_track = track
                        break
                else:
                    if len(track.get('segments', [])) > 0:
                        video_track = track
                        break
                        
        if not video_track:
            return {"success": False, "error": "Không tìm thấy Track Video nào có chứa clip để đồng bộ."}
            
        # Đổi flag = 2 (Overlay track) để ngăn CapCut tự động hút dính (snapping) làm lệch timeline
        if video_track.get('flag', 0) == 0:
            video_track['flag'] = 2
            has_main_track = any(t.get('flag', 1) == 0 for t in data.get('tracks', []) if t.get('type') == 'video' and t != video_track)
            if not has_main_track:
                new_main_track = {
                    "attribute": 0,
                    "flag": 0,
                    "id": str(uuid.uuid4()).upper(),
                    "segments": [],
                    "type": "video"
                }
                data['tracks'].insert(0, new_main_track)
                
        segments = video_track.get('segments', [])
        if not segments:
            return {"success": False, "error": "Track Video được chọn không có đoạn clip nào."}
            
        # Sắp xếp segments video theo thứ tự thời gian hiện tại
        segments.sort(key=lambda x: x.get('target_timerange', {}).get('start', 0))
        
        if 'materials' not in data:
            data['materials'] = {}
        if 'speeds' not in data['materials']:
            data['materials']['speeds'] = []
            
        materials_speeds = data['materials']['speeds']
        video_materials = {m['id']: m for m in data['materials'].get('videos', [])}
        image_materials = {m['id']: m for m in data['materials'].get('images', [])}
        
        # 3. Tiến hành khớp từng clip với từng câu phụ đề
        new_segments = []
        video_count = 0
        photo_count = 0
        
        num_items = min(len(segments), len(srt_blocks))
        
        for i in range(num_items):
            seg = segments[i]
            srt_block = srt_blocks[i]
            
            srt_start = srt_block['start']
            
            # Tính khoảng thời gian cần đạt đến đầu câu phụ đề tiếp theo để không bị ngắt quãng
            if i < len(srt_blocks) - 1:
                next_start = srt_blocks[i+1]['start']
                target_duration_needed = next_start - srt_start
            else:
                target_duration_needed = srt_block['duration']
                
            target_duration_needed = max(1, target_duration_needed)
            target_start = srt_start
            source_duration = seg.get('source_timerange', {}).get('duration', 0)
            
            current_speed_ref = None
            speed_idx = -1
            if 'extra_material_refs' in seg:
                for ref in seg['extra_material_refs']:
                    for j, s in enumerate(materials_speeds):
                        if s.get('id') == ref:
                            current_speed_ref = s
                            speed_idx = j
                            break
                    if current_speed_ref:
                        break
                        
            new_target_duration = source_duration
            new_speed_val = 1.0
            
            material_id = seg.get('material_id')
            mat = video_materials.get(material_id) or image_materials.get(material_id, {})
            is_photo = (mat.get('type') == 'photo') or (material_id in image_materials)
            
            if is_photo:
                photo_count += 1
                new_target_duration = target_duration_needed
                if 'source_timerange' not in seg:
                    seg['source_timerange'] = {'start': 0, 'duration': target_duration_needed}
                else:
                    seg['source_timerange']['duration'] = target_duration_needed
            else:
                video_count += 1
                if source_duration >= target_duration_needed:
                    # Clip dài hơn câu thoại
                    if long_video_action == "fast":
                        new_target_duration = target_duration_needed
                        new_speed_val = max(0.01, source_duration / target_duration_needed)
                    else:
                        # Cắt ngắn vừa khít câu thoại
                        new_target_duration = target_duration_needed
                        if 'source_timerange' not in seg:
                            seg['source_timerange'] = {'start': 0, 'duration': target_duration_needed}
                        else:
                            seg['source_timerange']['duration'] = target_duration_needed
                else:
                    # Clip ngắn hơn câu thoại
                    if short_video_action == "slow":
                        new_target_duration = target_duration_needed
                        safe_source = max(1, source_duration)
                        new_speed_val = max(0.01, safe_source / target_duration_needed)
                    else:
                        new_target_duration = source_duration
                        
            seg['target_timerange'] = {
                'start': target_start,
                'duration': int(new_target_duration)
            }
            
            if new_speed_val != 1.0:
                if current_speed_ref:
                    materials_speeds[speed_idx]['speed'] = float(new_speed_val)
                else:
                    new_speed_id = str(uuid.uuid4()).upper()
                    materials_speeds.append({
                        "curve_speed": None,
                        "id": new_speed_id,
                        "mode": 0,
                        "speed": float(new_speed_val),
                        "type": "speed"
                    })
                    if 'extra_material_refs' not in seg:
                        seg['extra_material_refs'] = []
                    seg['extra_material_refs'].insert(0, new_speed_id)
            elif current_speed_ref and new_speed_val == 1.0:
                materials_speeds[speed_idx]['speed'] = 1.0
                
            new_segments.append(seg)
            
        video_track['segments'] = new_segments
        
        # Ghi lại file draft_content.json
        with open(draft_content_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))
            
        msg_parts = []
        if video_count > 0:
            msg_parts.append(f"{video_count} video")
        if photo_count > 0:
            msg_parts.append(f"{photo_count} ảnh")
            
        msg_str = " và ".join(msg_parts) if msg_parts else "0 clip"
        return {
            "success": True, 
            "message": f"Đã đồng bộ {msg_str} với {num_items} câu phụ đề thành công!",
            "synced_count": num_items,
            "video_count": video_count,
            "photo_count": photo_count,
            "total_subtitles": len(srt_blocks)
        }
    except Exception as e:
        import traceback
        return {"success": False, "error": str(e), "trace": traceback.format_exc()}

def relaunch_capcut():
    """Khởi động lại CapCut PC để load ngay timeline mới"""
    try:
        # Tắt process CapCut.exe nếu đang chạy
        subprocess.run(['taskkill', '/F', '/IM', 'CapCut.exe'], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
        time.sleep(0.5)
        
        # Tìm đường dẫn CapCut.exe
        local_app_data = os.environ.get('LOCALAPPDATA', '')
        capcut_exe = os.path.join(local_app_data, 'CapCut', 'Apps', 'CapCut.exe')
        
        # Nếu chưa tìm thấy ở Apps, tìm trong thư mục cài đặt mặc định
        if not os.path.exists(capcut_exe):
            apps_dir = os.path.join(local_app_data, 'CapCut', 'Apps')
            if os.path.exists(apps_dir):
                for f in os.listdir(apps_dir):
                    sub = os.path.join(apps_dir, f)
                    if os.path.isdir(sub) and os.path.exists(os.path.join(sub, 'CapCut.exe')):
                        capcut_exe = os.path.join(sub, 'CapCut.exe')
                        break
                        
        if os.path.exists(capcut_exe):
            subprocess.Popen([capcut_exe], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
            return True
        return False
    except Exception as e:
        print(f"Error relaunching CapCut: {e}")
        return False
