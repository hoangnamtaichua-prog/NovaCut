import os
import sys
import json
import uuid
import time
import re
import shutil
import subprocess
import urllib.parse
from flask import Blueprint, request, jsonify, Response, send_file
from routes.state import ROOT_DIR, USER_DATA_DIR
from routes.security import is_path_allowed
import license_manager
import comic_crawler
import comic_panel_detector
import comic_review_engine
import comic_video_renderer

comic_review_bp = Blueprint('comic_review', __name__)

_active_stops = {}
_session_dirs = {}
_SESSION_CACHE_FILE = os.path.join(ROOT_DIR, 'temp', 'comic_sessions.json')

def _load_session_cache():
    global _session_dirs
    if os.path.exists(_SESSION_CACHE_FILE):
        try:
            with open(_SESSION_CACHE_FILE, 'r', encoding='utf-8') as f:
                _session_dirs.update(json.load(f))
        except Exception:
            pass

def _save_session_cache():
    try:
        os.makedirs(os.path.dirname(_SESSION_CACHE_FILE), exist_ok=True)
        with open(_SESSION_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_session_dirs, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

_load_session_cache()

def _resolve_session_dir(session_id, custom_save_dir=None, project_folder_name=None):
    _load_session_cache()

    # 1. Nếu custom_save_dir được cung cấp và tồn tại
    if custom_save_dir and os.path.exists(custom_save_dir):
        # 1a. Nếu chính custom_save_dir đã chứa panels.json hoặc panels
        if os.path.exists(os.path.join(custom_save_dir, 'panels.json')) or os.path.exists(os.path.join(custom_save_dir, 'panels')):
            _session_dirs[session_id] = custom_save_dir
            _save_session_cache()
            try:
                from routes.security import register_user_path
                register_user_path(custom_save_dir)
            except Exception:
                pass
            return custom_save_dir

        # 1b. Nếu có project_folder_name
        if project_folder_name and project_folder_name.strip():
            clean_name = re.sub(r'[\\/*?:"<>|]', '_', project_folder_name.strip())
            s_dir = os.path.join(custom_save_dir, clean_name)
            _session_dirs[session_id] = s_dir
            _save_session_cache()
            try:
                from routes.security import register_user_path
                register_user_path(s_dir)
            except Exception:
                pass
            return s_dir

        # 1c. Tự động tìm thư mục con gần nhất chứa panels.json (ví dụ chapter-1)
        try:
            candidates = []
            for item in os.listdir(custom_save_dir):
                sub = os.path.join(custom_save_dir, item)
                if os.path.isdir(sub) and (os.path.exists(os.path.join(sub, 'panels.json')) or os.path.exists(os.path.join(sub, 'panels'))):
                    candidates.append((os.path.getmtime(sub), sub))
            if candidates:
                candidates.sort(reverse=True)
                best_sub = candidates[0][1]
                _session_dirs[session_id] = best_sub
                _save_session_cache()
                try:
                    from routes.security import register_user_path
                    register_user_path(best_sub)
                except Exception:
                    pass
                return best_sub
        except Exception:
            pass

    # 2. Nếu project_folder_name được cung cấp mà không có custom_save_dir
    if project_folder_name and project_folder_name.strip():
        clean_name = re.sub(r'[\\/*?:"<>|]', '_', project_folder_name.strip())
        s_dir = os.path.join(ROOT_DIR, 'projects', 'comic_reviews', clean_name)
        _session_dirs[session_id] = s_dir
        _save_session_cache()
        try:
            from routes.security import register_user_path
            register_user_path(s_dir)
        except Exception:
            pass
        return s_dir

    # 3. Kiểm tra cache
    if session_id in _session_dirs and os.path.exists(_session_dirs[session_id]):
        return _session_dirs[session_id]

    s_dir = comic_crawler.get_session_dir(ROOT_DIR, session_id)
    _session_dirs[session_id] = s_dir
    _save_session_cache()
    return s_dir

@comic_review_bp.route('/api/comic_review/detect_project', methods=['GET', 'POST'])
def detect_comic_project():
    """Tự động kiểm tra xem trong thư mục lưu trữ đã có sẵn dữ liệu ô tranh / truyện chưa."""
    data = request.args if request.method == 'GET' else (request.json or {})
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    session_id = data.get('session_id', '').strip()

    s_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
    panels_file = os.path.join(s_dir, 'panels.json')
    panels_dir = os.path.join(s_dir, 'panels')
    raw_pages_dir = os.path.join(s_dir, 'raw_pages')

    found = False
    panel_count = 0
    if os.path.exists(panels_file):
        try:
            with open(panels_file, 'r', encoding='utf-8') as f:
                p_data = json.load(f)
                panel_count = len(p_data)
                found = panel_count > 0
        except Exception:
            pass

    if not found and os.path.exists(panels_dir):
        files = [f for f in os.listdir(panels_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))]
        panel_count = len(files)
        found = panel_count > 0

    # Nếu không tìm thấy trong s_dir, thử tìm kiếm thông minh trong custom_save_dir hoặc thư mục cha
    if not found and custom_save_dir and os.path.isdir(custom_save_dir):
        check_dirs = [custom_save_dir]
        parent = os.path.dirname(custom_save_dir)
        if parent and os.path.isdir(parent) and parent != custom_save_dir:
            check_dirs.append(parent)

        for c_dir in check_dirs:
            try:
                for item in os.listdir(c_dir):
                    sub = os.path.join(c_dir, item)
                    if os.path.isdir(sub):
                        sub_meta = os.path.join(sub, 'panels.json')
                        if os.path.exists(sub_meta):
                            with open(sub_meta, 'r', encoding='utf-8') as f:
                                sub_p = json.load(f)
                                if sub_p:
                                    s_dir = sub
                                    panel_count = len(sub_p)
                                    found = True
                                    _session_dirs[session_id] = s_dir
                                    _save_session_cache()
                                    try:
                                        from routes.security import register_user_path
                                        register_user_path(s_dir)
                                    except Exception:
                                        pass
                                    break
            except Exception:
                pass
            if found:
                break

    raw_count = len(os.listdir(raw_pages_dir)) if os.path.exists(raw_pages_dir) else 0
    base_name = os.path.basename(s_dir)
    return jsonify({
        'success': True,
        'found': found,
        'folder_path': s_dir,
        'project_folder_name': base_name,
        'panel_count': panel_count,
        'raw_page_count': raw_count
    })

def _check_permission():
    allowed, msg, _ = license_manager.check_permission('can_access_review')
    if not allowed:
        return False, msg
    return True, None

def _get_api_keys():
    api_file = os.path.join(USER_DATA_DIR, 'api_keys.txt')
    legacy_file = os.path.join(ROOT_DIR, 'api_keys.txt')
    keys = {}
    for p in [api_file, legacy_file]:
        if os.path.exists(p):
            try:
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if '=' in line:
                            k, v = line.strip().split('=', 1)
                            if k not in keys or not keys[k]:
                                keys[k] = v
            except Exception:
                pass
    return keys

@comic_review_bp.route('/api/comic_review/stop', methods=['POST'])
def stop_comic_task():
    data = request.json or {}
    session_id = data.get('session_id', 'default')
    _active_stops[session_id] = True
    return jsonify({'success': True})

@comic_review_bp.route('/api/comic_review/crawl_stream', methods=['POST'])
def crawl_comic_stream():
    allowed, msg = _check_permission()
    if not allowed:
        return jsonify({'success': False, 'error': msg}), 403

    data = request.json or {}
    url = data.get('url', '').strip()
    local_folder = data.get('folder_path', '').strip()
    session_id = data.get('session_id') or f"comic_{uuid.uuid4().hex[:8]}"
    chapter_scope = str(data.get('chapter_scope', '5')).strip()
    chapter_count = int(data.get('chapter_count', 5))
    is_all = bool(data.get('is_all', False)) or (chapter_scope == 'all')
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    _active_stops[session_id] = False

    def check_stop():
        return _active_stops.get(session_id, False)

    def generate():
        import importlib
        importlib.reload(comic_crawler)
        importlib.reload(comic_panel_detector)

        session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
        yield f"data: [SESSION_DIR] {session_dir}\n\n"
        raw_pages = []

        if local_folder and os.path.isdir(local_folder):
            yield f"data: 📂 Đang nạp ảnh truyện từ thư mục máy tính: {local_folder}...\n\n"
            try:
                raw_pages = comic_crawler.load_from_local_folder(local_folder, ROOT_DIR, session_id, custom_parent_dir=custom_save_dir, folder_name=project_folder_name)
                yield f"data: ✅ Đã nạp thành công {len(raw_pages)} trang ảnh truyện.\n\n"
            except Exception as e:
                yield f"data: 🛑 Lỗi nạp thư mục: {str(e)}\n\n"
                return
        elif url:
            for log_msg in comic_crawler.crawl_comic_chapters(url, ROOT_DIR, session_id, chapter_scope=chapter_scope, chapter_count=chapter_count, is_all=is_all, custom_parent_dir=custom_save_dir, folder_name=project_folder_name, check_stop=check_stop):
                yield log_msg
            raw_dir = os.path.join(session_dir, 'raw_pages')
            if os.path.exists(raw_dir):
                raw_pages = [os.path.join(raw_dir, f) for f in sorted(os.listdir(raw_dir))]
        else:
            yield "data: 🛑 Vui lòng cung cấp Link web truyện hoặc chọn Thư mục ảnh truyện.\n\n"
            return

        if not raw_pages:
            yield "data: 🛑 Không có trang ảnh nào để xử lý cắt ô tranh.\n\n"
            return

        # Tiến hành cắt ô tranh (Panel Slicing)
        yield "data: ✂️ [Cắt Ô Tranh] Đang tiến hành phân tích bố cục và cắt ô tranh (Panels)...\n\n"
        panels_dir = os.path.join(session_dir, 'panels')
        panels = []
        for event_type, payload in comic_panel_detector.extract_panels_stream(raw_pages, panels_dir, check_stop=check_stop):
            if event_type == 'progress':
                pct, msg = payload
                yield f"data: [PROGRESS] {pct}\n\n"
                yield f"data: {msg}\n\n"
            elif event_type == 'done':
                panels = payload

        # Lưu metadata panels vào root session và thư mục scripts dự trữ
        with open(os.path.join(session_dir, 'panels.json'), 'w', encoding='utf-8') as f:
            json.dump(panels, f, ensure_ascii=False, indent=2)

        scripts_dir = os.path.join(session_dir, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, 'danh_sách_ô_tranh.json'), 'w', encoding='utf-8') as f:
            json.dump(panels, f, ensure_ascii=False, indent=2)

        yield f"data: [PANELS_READY] {len(panels)}\n\n"
        yield f"data: 🎉 Hoàn thành thu thập! Đã tạo {len(panels)} ô tranh sẵn sàng để viết kịch bản.\n\n"

    return Response(generate(), mimetype='text/event-stream')

@comic_review_bp.route('/api/comic_review/panels', methods=['GET'])
def get_session_panels():
    session_id = request.args.get('session_id', '').strip()
    custom_save_dir = request.args.get('custom_save_dir', '').strip()
    project_folder_name = request.args.get('project_folder_name', '').strip()
    if not session_id and not project_folder_name:
        return jsonify({'success': False, 'error': 'Thiếu session_id'}), 400

    session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
    meta_path = os.path.join(session_dir, 'panels.json')
    if not os.path.exists(meta_path):
        return jsonify({'success': False, 'error': 'Chưa có dữ liệu panel cho session này'}), 404

    with open(meta_path, 'r', encoding='utf-8') as f:
        panels = json.load(f)

    extra_q = []
    if custom_save_dir:
        extra_q.append(f"custom_save_dir={urllib.parse.quote(custom_save_dir)}")
    if project_folder_name:
        extra_q.append(f"project_folder_name={urllib.parse.quote(project_folder_name)}")
    extra_str = ("?" + "&".join(extra_q)) if extra_q else ""

    # Thêm URL truy cập ảnh
    for p in panels:
        p['thumb_url'] = f"/api/comic_review/media/{session_id}/panels/{p['filename']}{extra_str}"
        if p.get('source_page'):
            p['raw_page_url'] = f"/api/comic_review/media/{session_id}/raw_pages/{p['source_page']}{extra_str}"

    return jsonify({'success': True, 'session_id': session_id, 'panels': panels, 'total': len(panels)})

@comic_review_bp.route('/api/comic_review/generate_script_stream', methods=['POST'])
def generate_script_stream():
    allowed, msg = _check_permission()
    if not allowed:
        return jsonify({'success': False, 'error': msg}), 403

    data = request.json or {}
    session_id = data.get('session_id', '')
    style = data.get('style', 'badass')
    chapter_scope = str(data.get('chapter_scope', '5')).strip()
    chapter_count = int(data.get('chapter_count', 5))
    is_all = bool(data.get('is_all', False)) or (chapter_scope == 'all')
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    voice_id = data.get('voice_id', 'vi-VN-NamMinhNeural')
    speed = float(data.get('speed') or data.get('voice_speed') or 1.10)
    inpaint_bubbles = bool(data.get('inpaint_bubbles', False))
    filter_text_heavy = bool(data.get('filter_text_heavy', True))
    pacing = data.get('pacing', 'balanced')

    session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
    meta_path = os.path.join(session_dir, 'panels.json')
    if not os.path.exists(meta_path):
        return jsonify({'success': False, 'error': 'Chưa có dữ liệu panels'}), 400

    with open(meta_path, 'r', encoding='utf-8') as f:
        panels = json.load(f)

    api_config = _get_api_keys()
    _active_stops[session_id] = False

    def check_stop():
        return _active_stops.get(session_id, False)

    def generate():
        import importlib
        import concurrent.futures
        importlib.reload(comic_review_engine)

        yield "data: 🔍 [AI OCR] Đang chuẩn bị quét đọc chữ thoại trên các ô tranh...\n\n"
        if inpaint_bubbles:
            yield "data: 🪄 [Inpaint] Đã bật chế độ tự động xóa chữ bong bóng thoại (Clean Art)...\n\n"
        
        panel_texts = []
        for event_type, payload in comic_review_engine.extract_ocr_generator(
            panels, 
            max_panels=70, 
            inpaint_bubbles=inpaint_bubbles, 
            check_stop=check_stop
        ):
            if event_type == 'progress':
                pct, msg = payload
                yield f"data: [PROGRESS] {pct}\n\n"
                yield f"data: {msg}\n\n"
            elif event_type == 'done':
                panel_texts = payload

        if check_stop():
            yield "data: 🛑 Đã dừng xử lý.\n\n"
            return

        scope_desc = "Toàn bộ truyện" if is_all else f"{chapter_count} chap"
        yield f"data: 🤖 [AI Biên Kịch] Bắt đầu phân tích cốt truyện theo phong cách '{style}' (Phạm vi: {scope_desc})...\n\n"
        
        raw_beats = []
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    comic_review_engine.generate_comic_review_script,
                    panel_texts,
                    api_config,
                    style=style,
                    chapter_scope=chapter_scope,
                    chapter_count=chapter_count,
                    is_all=is_all,
                    filter_text_heavy=filter_text_heavy,
                    pacing=pacing,
                    check_stop=check_stop
                )
                start_t = time.time()
                while not future.done():
                    if check_stop():
                        yield "data: 🛑 Đã dừng xử lý.\n\n"
                        return
                    elapsed = int(time.time() - start_t)
                    yield f"data: 🤖 [AI Biên Kịch] Đang phân tích cốt truyện & viết lời bình ({elapsed}s)...\n\n"
                    time.sleep(2)
                raw_beats = future.result()
        except Exception as e:
            yield f"data: 🛑 Lỗi AI sinh kịch bản: {str(e)}\n\n"
            return

        yield f"data: 🎙️ [Tạo Voice] Đã hoàn thành {len(raw_beats)} phân cảnh kịch bản! Bắt đầu tạo giọng đọc review đồng bộ...\n\n"

        audio_dir = os.path.join(session_dir, 'audio')
        os.makedirs(audio_dir, exist_ok=True)

        segments = []
        curr_time = 0.0
        total_beats = len(raw_beats)

        # Lọc danh sách ô tranh hợp lệ (loại bỏ triệt để ô tranh quảng cáo / credit)
        ad_panel_ids = {item['panel_id'] for item in panel_texts if item.get('is_ad')}
        clean_panels = [p for p in panels if p['id'] not in ad_panel_ids]
        if filter_text_heavy:
            heavy_ids = {item['panel_id'] for item in panel_texts if item.get('is_text_heavy')}
            art_panels = [p for p in clean_panels if p['id'] not in heavy_ids]
            if art_panels:
                clean_panels = art_panels
        if not clean_panels:
            clean_panels = panels

        ocr_map = {item['panel_id']: item for item in panel_texts}
        panel_map = {p['id']: p for p in clean_panels}

        for idx, beat in enumerate(raw_beats, start=1):
            if check_stop():
                yield "data: 🛑 Đã dừng tạo giọng đọc.\n\n"
                return

            script_text = beat.get('script_text', '').strip()
            pct = int((idx / total_beats) * 100)
            yield f"data: [PROGRESS] {pct}\n\n"
            script_preview = script_text[:42] + ("..." if len(script_text) > 42 else "")
            yield f"data: 🎙️ [Tạo Voice] Phân cảnh {idx}/{total_beats} ({pct}%) • \"{script_preview}\"\n\n"

            p_id = beat.get('panel_id', idx)
            chosen_panel = panel_map.get(p_id) or (clean_panels[(idx - 1) % len(clean_panels)] if clean_panels else None)

            # Kiểm tra nếu ô tranh đã có phiên bản xóa chữ sạch sẽ (clean art)
            chosen_filename = chosen_panel['filename'] if chosen_panel else ""
            chosen_path = chosen_panel['path'] if chosen_panel else ""
            if chosen_panel and chosen_panel.get('id') in ocr_map:
                o_item = ocr_map[chosen_panel['id']]
                if inpaint_bubbles and o_item.get('clean_filename') and os.path.exists(o_item.get('clean_path', '')):
                    chosen_filename = o_item['clean_filename']
                    chosen_path = o_item['clean_path']

            script_text = beat.get('script_text', '').strip()
            audio_filename = f"beat_{idx:04d}.mp3"
            audio_path = os.path.join(audio_dir, audio_filename)

            try:
                comic_review_engine.generate_voice_for_text(script_text, voice_id, audio_path, speed=speed)
                dur = comic_review_engine.get_audio_duration(audio_path)
            except Exception as err:
                dur = 3.5

            st = curr_time
            et = curr_time + dur
            curr_time = et

            extra_q = []
            if custom_save_dir:
                extra_q.append(f"custom_save_dir={urllib.parse.quote(custom_save_dir)}")
            if project_folder_name:
                extra_q.append(f"project_folder_name={urllib.parse.quote(project_folder_name)}")
            extra_str = ("?" + "&".join(extra_q)) if extra_q else ""
            t_str = f"&t={int(time.time())}" if extra_str else f"?t={int(time.time())}"

            seg_data = {
                "id": idx,
                "panel_id": chosen_panel['id'] if chosen_panel else idx,
                "panel_filename": chosen_filename,
                "panel_path": chosen_path,
                "panel_url": (f"/api/comic_review/media/{session_id}/panels/{chosen_filename}{extra_str}{t_str}") if chosen_panel else "",
                "source_page": chosen_panel.get('source_page', '') if chosen_panel else "",
                "script_text": script_text,
                "audio_filename": audio_filename,
                "audio_path": audio_path,
                "audio_url": f"/api/comic_review/media/{session_id}/audio/{audio_filename}{extra_str}{t_str}",
                "duration": dur,
                "start_time": round(st, 2),
                "end_time": round(et, 2),
                "voice_id": voice_id
            }
            segments.append(seg_data)

        # 1. Lưu segments vào session
        with open(os.path.join(session_dir, 'segments.json'), 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

        # 2. Lưu kịch bản dự trữ vào thư mục scripts
        scripts_dir = os.path.join(session_dir, 'scripts')
        os.makedirs(scripts_dir, exist_ok=True)
        with open(os.path.join(scripts_dir, 'kịch_bản_phân_cảnh.json'), 'w', encoding='utf-8') as f:
            json.dump(segments, f, ensure_ascii=False, indent=2)

        # File văn bản thuần kịch bản review dễ đọc và sao lưu
        script_txt_lines = [
            "=================================================================",
            f"KỊCH BẢN REVIEW TRUYỆN TRANH: {project_folder_name or session_id}",
            f"Phong cách: {style} | Phạm vi: {scope_desc}",
            f"Tổng số phân cảnh: {len(segments)} câu | Giọng đọc: {voice_id}",
            f"Thời gian tạo: {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "=================================================================\n"
        ]
        for seg in segments:
            script_txt_lines.append(f"[Phân cảnh #{seg['id']}] (Thời lượng: {seg['duration']}s | Ô tranh: {seg.get('panel_filename', '')})")
            script_txt_lines.append(f"{seg['script_text']}\n")

        with open(os.path.join(scripts_dir, 'kịch_bản_review.txt'), 'w', encoding='utf-8') as f:
            f.write("\n".join(script_txt_lines))

        # Lưu thông tin dự án
        project_info = {
            "session_id": session_id,
            "project_dir": session_dir,
            "project_name": project_folder_name or session_id,
            "style": style,
            "chapter_scope": chapter_scope,
            "chapter_count": chapter_count,
            "voice_id": voice_id,
            "speed": speed,
            "total_segments": len(segments),
            "created_at": time.strftime('%Y-%m-%d %H:%M:%S')
        }
        with open(os.path.join(scripts_dir, 'thông_tin_dự_án.json'), 'w', encoding='utf-8') as f:
            json.dump(project_info, f, ensure_ascii=False, indent=2)

        yield f"data: [SEGMENTS_READY] {json.dumps(segments, ensure_ascii=False)}\n\n"
        yield f"data: 📁 Kịch bản dự trữ đã được lưu vào thư mục dự án: scripts/kịch_bản_review.txt\n\n"
        yield "data: 🎉 Đã khởi tạo hoàn tất Bảng Kịch bản 4 Cột! Bạn có thể xem trước, chỉnh sửa kịch bản, đổi ảnh hoặc nghe thử voice.\n\n"

    return Response(generate(), mimetype='text/event-stream')

@comic_review_bp.route('/api/comic_review/inpaint_beat_panel', methods=['POST'])
def inpaint_beat_panel():
    """Xóa chữ trong khung thoại cho 1 ô tranh cụ thể bằng RapidOCR + OpenCV Inpainting."""
    allowed, msg = _check_permission()
    if not allowed:
        return jsonify({'success': False, 'error': msg}), 403

    data = request.json or {}
    panel_path = data.get('panel_path', '').strip()
    session_id = data.get('session_id', '').strip()
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    beat_id = data.get('beat_id')

    if not panel_path or not os.path.exists(panel_path):
        return jsonify({'success': False, 'error': 'File ảnh ô tranh không tồn tại'}), 404

    try:
        clean_path = comic_review_engine.inpaint_single_panel(panel_path)
        clean_filename = os.path.basename(clean_path)

        # Cập nhật segments.json nếu có session_id và beat_id
        if session_id:
            s_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
            seg_file = os.path.join(s_dir, 'segments.json')
            if os.path.exists(seg_file) and beat_id is not None:
                try:
                    with open(seg_file, 'r', encoding='utf-8') as f:
                        segs = json.load(f)
                    for seg in segs:
                        if str(seg.get('id')) == str(beat_id):
                            seg['panel_filename'] = clean_filename
                            seg['panel_path'] = clean_path
                            extra_q = []
                            if custom_save_dir:
                                extra_q.append(f"custom_save_dir={urllib.parse.quote(custom_save_dir)}")
                            if project_folder_name:
                                extra_q.append(f"project_folder_name={urllib.parse.quote(project_folder_name)}")
                            extra_str = ("?" + "&".join(extra_q)) if extra_q else ""
                            t_str = f"&t={int(time.time())}" if extra_str else f"?t={int(time.time())}"
                            seg['panel_url'] = f"/api/comic_review/media/{session_id}/panels/{clean_filename}{extra_str}{t_str}"
                            break
                    with open(seg_file, 'w', encoding='utf-8') as f:
                        json.dump(segs, f, ensure_ascii=False, indent=2)
                except Exception as e:
                    logger.error(f"Error updating segments.json after inpaint: {e}")

        extra_q = []
        if custom_save_dir:
            extra_q.append(f"custom_save_dir={urllib.parse.quote(custom_save_dir)}")
        if project_folder_name:
            extra_q.append(f"project_folder_name={urllib.parse.quote(project_folder_name)}")
        extra_str = ("?" + "&".join(extra_q)) if extra_q else ""
        t_str = f"&t={int(time.time())}" if extra_str else f"?t={int(time.time())}"

        clean_url = f"/api/comic_review/media/{session_id}/panels/{clean_filename}{extra_str}{t_str}" if session_id else ""

        return jsonify({
            'success': True,
            'clean_path': clean_path,
            'clean_filename': clean_filename,
            'clean_url': clean_url
        })
    except Exception as e:
        logger.error(f"Inpaint failed: {e}")
        return jsonify({'success': False, 'error': f"Lỗi xóa chữ: {str(e)}"}), 500

@comic_review_bp.route('/api/comic_review/crop_panel', methods=['POST'])
def crop_panel():
    """Cắt lại khung tranh cho 1 phân cảnh hoặc ô tranh từ panel hoặc trang gốc."""
    allowed, msg = _check_permission()
    if not allowed:
        return jsonify({'success': False, 'error': msg}), 403

    data = request.json or {}
    session_id = data.get('session_id', '').strip()
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    beat_id = data.get('beat_id')
    source_type = data.get('source_type', 'panel')  # 'panel' hoặc 'raw_page'
    source_filename = data.get('source_filename', '').strip()
    panel_path = data.get('panel_path', '').strip()

    crop_x = float(data.get('x', 0))
    crop_y = float(data.get('y', 0))
    crop_w = float(data.get('width', 0))
    crop_h = float(data.get('height', 0))
    rotate = int(data.get('rotate', 0)) % 360

    session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)

    # Xác định đường dẫn file ảnh nguồn
    img_file = ""
    if source_type == 'raw_page':
        img_file = os.path.join(session_dir, 'raw_pages', source_filename)
    elif panel_path and os.path.exists(panel_path):
        img_file = panel_path
    elif source_filename:
        img_file = os.path.join(session_dir, 'panels', source_filename)

    if not img_file or not os.path.exists(img_file):
        return jsonify({'success': False, 'error': f"Không tìm thấy file ảnh nguồn: {source_filename}"}), 404

    try:
        import numpy as np
        img_bytes = np.fromfile(img_file, dtype=np.uint8)
        img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return jsonify({'success': False, 'error': 'Không thể đọc dữ liệu ảnh'}), 400

        # Xoay nếu có
        if rotate == 90:
            img = cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        elif rotate == 180:
            img = cv2.rotate(img, cv2.ROTATE_180)
        elif rotate == 270:
            img = cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)

        ih, iw = img.shape[:2]

        # Chuẩn hóa tọa độ cắt an toàn trong giới hạn ảnh
        x = max(0, min(iw - 10, int(round(crop_x))))
        y = max(0, min(ih - 10, int(round(crop_y))))
        w = max(10, min(iw - x, int(round(crop_w))))
        h = max(10, min(ih - y, int(round(crop_h))))

        cropped = img[y:y+h, x:x+w]

        # Đặt tên file ảnh cắt mới
        timestamp = int(time.time() * 1000) % 1000000
        beat_suffix = f"b{beat_id}_" if beat_id is not None else ""
        new_filename = f"panel_{beat_suffix}crop_{timestamp}.jpg"
        panels_dir = os.path.join(session_dir, 'panels')
        os.makedirs(panels_dir, exist_ok=True)
        new_path = os.path.join(panels_dir, new_filename)

        _, encoded = cv2.imencode('.jpg', cropped, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        with open(new_path, 'wb') as f:
            f.write(encoded)

        # Cập nhật vào segments.json nếu có beat_id
        seg_file = os.path.join(session_dir, 'segments.json')
        if os.path.exists(seg_file) and beat_id is not None:
            try:
                with open(seg_file, 'r', encoding='utf-8') as f:
                    segs = json.load(f)
                for seg in segs:
                    if str(seg.get('id')) == str(beat_id):
                        seg['panel_filename'] = new_filename
                        seg['panel_path'] = new_path
                        extra_q = []
                        if custom_save_dir:
                            extra_q.append(f"custom_save_dir={urllib.parse.quote(custom_save_dir)}")
                        if project_folder_name:
                            extra_q.append(f"project_folder_name={urllib.parse.quote(project_folder_name)}")
                        extra_str = ("?" + "&".join(extra_q)) if extra_q else ""
                        t_str = f"&t={int(time.time())}" if extra_str else f"?t={int(time.time())}"
                        seg['panel_url'] = f"/api/comic_review/media/{session_id}/panels/{new_filename}{extra_str}{t_str}"
                        break
                with open(seg_file, 'w', encoding='utf-8') as f:
                    json.dump(segs, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Error updating segments.json after crop: {e}")

        # Thêm vào panels.json để có thể tái sử dụng trong gallery
        panels_meta = os.path.join(session_dir, 'panels.json')
        if os.path.exists(panels_meta):
            try:
                with open(panels_meta, 'r', encoding='utf-8') as f:
                    p_list = json.load(f)
                new_p_entry = {
                    "id": len(p_list) + 1,
                    "filename": new_filename,
                    "path": new_path,
                    "source_page": source_filename if source_type == 'raw_page' else "",
                    "width": w,
                    "height": h
                }
                p_list.append(new_p_entry)
                with open(panels_meta, 'w', encoding='utf-8') as f:
                    json.dump(p_list, f, ensure_ascii=False, indent=2)
            except Exception as e:
                logger.error(f"Error appending to panels.json: {e}")

        extra_q = []
        if custom_save_dir:
            extra_q.append(f"custom_save_dir={urllib.parse.quote(custom_save_dir)}")
        if project_folder_name:
            extra_q.append(f"project_folder_name={urllib.parse.quote(project_folder_name)}")
        extra_str = ("?" + "&".join(extra_q)) if extra_q else ""
        t_str = f"&t={int(time.time())}" if extra_str else f"?t={int(time.time())}"
        new_url = f"/api/comic_review/media/{session_id}/panels/{new_filename}{extra_str}{t_str}"

        return jsonify({
            'success': True,
            'panel_filename': new_filename,
            'panel_path': new_path,
            'panel_url': new_url,
            'width': w,
            'height': h
        })
    except Exception as e:
        logger.error(f"Crop panel failed: {e}")
        return jsonify({'success': False, 'error': f"Lỗi cắt ảnh: {str(e)}"}), 500

@comic_review_bp.route('/api/comic_review/generate_beat_voice', methods=['POST'])
def generate_single_beat_voice():
    allowed, msg = _check_permission()
    if not allowed:
        return jsonify({'success': False, 'error': msg}), 403

    data = request.json or {}
    session_id = data.get('session_id', '')
    beat_id = int(data.get('beat_id', 1))
    script_text = data.get('script_text', '').strip()
    voice_id = data.get('voice_id', 'vi-VN-NamMinhNeural')
    speed = float(data.get('speed') or data.get('voice_speed') or 1.10)

    session_dir = _resolve_session_dir(session_id)
    audio_dir = os.path.join(session_dir, 'audio')
    os.makedirs(audio_dir, exist_ok=True)

    audio_filename = f"beat_{beat_id:04d}.mp3"
    audio_path = os.path.join(audio_dir, audio_filename)

    try:
        comic_review_engine.generate_voice_for_text(script_text, voice_id, audio_path, speed=speed)
        dur = comic_review_engine.get_audio_duration(audio_path)
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

    audio_url = f"/api/comic_review/media/{session_id}/audio/{audio_filename}?t={int(time.time()*1000)}"
    return jsonify({
        'success': True,
        'beat_id': beat_id,
        'duration': dur,
        'audio_url': audio_url
    })

@comic_review_bp.route('/api/comic_review/media/<session_id>/<media_type>/<filename>', methods=['GET'])
def get_comic_media(session_id, media_type, filename):
    custom_save_dir = request.args.get('custom_save_dir', '').strip()
    project_folder_name = request.args.get('project_folder_name', '').strip()
    session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
    target_dir = os.path.join(session_dir, media_type)
    file_path = os.path.join(target_dir, filename)
    if not os.path.exists(file_path):
        return "Not found", 404
    return send_file(file_path)

@comic_review_bp.route('/api/comic_review/render_video_stream', methods=['POST'])
def render_comic_video_stream():
    allowed, msg = _check_permission()
    if not allowed:
        return jsonify({'success': False, 'error': msg}), 403

    data = request.json or {}
    session_id = data.get('session_id', '')
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    segments = data.get('segments', [])
    aspect_ratio = data.get('aspect_ratio', '9:16')
    ken_burns = bool(data.get('ken_burns', True))
    burn_subs = bool(data.get('burn_subs', True))
    bgm_path = data.get('bgm_path')
    output_name = data.get('output_name', 'comic_review_final.mp4').strip()
    if not output_name.lower().endswith('.mp4'):
        output_name += '.mp4'

    output_dir = os.path.join(ROOT_DIR, 'output', 'comic_reviews')
    os.makedirs(output_dir, exist_ok=True)
    final_output_path = os.path.join(output_dir, output_name)

    session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
    _active_stops[session_id] = False

    def check_stop():
        return _active_stops.get(session_id, False)

    def generate():
        import importlib
        import shutil
        importlib.reload(comic_video_renderer)

        # Cập nhật đường dẫn tuyệt đối cho segments
        for s in segments:
            if not os.path.isabs(s.get('panel_path', '')):
                s['panel_path'] = os.path.join(session_dir, 'panels', s.get('panel_filename', ''))
            if not os.path.isabs(s.get('audio_path', '')):
                s['audio_path'] = os.path.join(session_dir, 'audio', s.get('audio_filename', ''))

        for log_msg in comic_video_renderer.render_comic_review_video(
            segments=segments,
            output_path=final_output_path,
            aspect_ratio=aspect_ratio,
            ken_burns=ken_burns,
            bgm_path=bgm_path,
            burn_subs=burn_subs,
            check_stop=check_stop
        ):
            yield log_msg

        if os.path.exists(final_output_path) and os.path.getsize(final_output_path) > 1000:
            try:
                from export_history import get_export_history_service
                service = get_export_history_service()
                service.record_export(
                    output_path=final_output_path,
                    source_tool='comic_review',
                    source_kind='comic_review',
                    export_run_id=f"comic_{session_id}_{int(time.time()*1000)}",
                    params={
                        'session_id': session_id,
                        'aspect_ratio': aspect_ratio,
                        'segments_count': len(segments)
                    }
                )
            except Exception as he:
                logging.getLogger(__name__).error(f"[ExportHistory] Error recording comic review export: {he}")

            # Lưu thêm bản sao trực tiếp trong thư mục dự án (nội bộ dự án, không ghi lịch sử bản sao này)
            try:
                proj_output = os.path.join(session_dir, 'output')
                os.makedirs(proj_output, exist_ok=True)
                shutil.copy2(final_output_path, os.path.join(proj_output, output_name))
            except Exception:
                pass
            yield f"data: [RENDER_FINISHED] {final_output_path}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@comic_review_bp.route('/api/comic_review/open_folder', methods=['POST'])
def open_comic_folder():
    data = request.json or {}
    session_id = data.get('session_id', '')
    custom_save_dir = data.get('custom_save_dir', '').strip()
    project_folder_name = data.get('project_folder_name', '').strip()
    folder_type = data.get('type', 'project')

    session_dir = _resolve_session_dir(session_id, custom_save_dir, project_folder_name)
    if folder_type == 'output':
        target_path = os.path.join(session_dir, 'output')
        if not os.path.exists(target_path):
            target_path = os.path.join(ROOT_DIR, 'output', 'comic_reviews')
    else:
        target_path = session_dir

    os.makedirs(target_path, exist_ok=True)
    try:
        import subprocess
        if sys.platform.startswith('win'):
            os.startfile(target_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', target_path])
        else:
            subprocess.Popen(['xdg-open', target_path])
        return jsonify({'success': True, 'folder_path': target_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
