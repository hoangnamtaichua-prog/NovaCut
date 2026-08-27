from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading
from routes.state import *
from routes.security import is_path_allowed, parse_bool, safe_join
from werkzeug.utils import secure_filename
import asr_manager
import ffmpeg_installer

video_edit_bp = Blueprint('video_edit', __name__)
STOP_EXPORT_FLAG = False
_export_lock = threading.RLock()
_export_active = False
_ocr_lock = threading.RLock()
_ocr_active = False
_review_lock = threading.RLock()
_review_active = False
_VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.mov', '.avi', '.webm', '.m4v'}
_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.m4a', '.aac', '.flac', '.ogg'}


def _terminate_process_tree(process):
    if not process or process.poll() is not None:
        return False
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], capture_output=True, timeout=10, creationflags=0x08000000)
        else:
            process.terminate()
            process.wait(timeout=5)
        return True
    except Exception:
        try:
            process.kill()
            return True
        except Exception:
            return False


def _require_permission(feature):
    import license_manager
    allowed, message, _ = license_manager.check_permission(feature)
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    return None

@video_edit_bp.route('/api/start', methods=['POST'])
def start_generation():
    global STOP_EXPORT_FLAG, _export_active
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Payload JSON không hợp lệ'}), 400
    try:
        mode = str(data.get('mode', 'none'))
        input_video = str(data.get('inputVideo') or '').strip(' "\'')
        output_dir = str(data.get('outputDir') or os.path.join(ROOT_DIR, 'output')).strip()
        output_name = secure_filename(str(data.get('outputName') or 'video_tom_tat.mp4'))
        manual_audio = str(data.get('manualAudio') or '').strip()
        manual_srt = str(data.get('manualSrt') or '').strip()
        dubbing = data.get('dubbing') or {}
        subtitles = data.get('subtitles') or []
        subtitles_enabled = parse_bool(data.get('subtitles_enabled'), True)
        subtitle_style = data.get('subtitle_style') or {}
        blur_original_subtitles = parse_bool(data.get('blur_original_subtitles'), False)
        blur_intensity = max(5, min(30, int(data.get('blur_intensity', 15))))
        original_srt_path = str(data.get('original_srt_path') or '').strip()
        ocr_region = data.get('ocr_region') or {}
        blur_lead_offset = max(-2.0, min(2.0, float(data.get('blur_lead_offset', -180)) / 1000.0))
        blur_padding = max(0.0, min(2.0, float(data.get('blur_padding', 220)) / 1000.0))
        blur_use_ai_scan = parse_bool(data.get('blur_use_ai_scan'), False)

        video_speed = float(data.get('video_speed', 1.0))
        video_zoom = float(data.get('video_zoom', 1.0))
        video_pan_x = float(data.get('video_pan_x', 0.0))
        video_pan_y = float(data.get('video_pan_y', 0.0))
        aspect_ratio = str(data.get('aspect_ratio', 'original'))
        mirror_flip = parse_bool(data.get('mirror_flip'), False)
        trim_enabled = parse_bool(data.get('trim_enabled'), False)
        trim_start = str(data.get('trim_start', '')).strip()
        trim_end = str(data.get('trim_end', '')).strip()
        encoder = str(data.get('encoder') or 'libx264')
        resolution = str(data.get('resolution') or 'original')
        bitrate = int(data.get('bitrate', 10000))
        bitrate_mode = str(data.get('bitrate_mode', 'VBR')).upper()
    except (TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': f'Tham số xuất video không hợp lệ: {exc}'}), 400

    if mode not in {'none', 'tts', 'manual', 'api'} or not isinstance(dubbing, dict) or not isinstance(subtitles, list):
        return jsonify({'success': False, 'error': 'Cấu hình mode/dubbing/subtitles không hợp lệ'}), 400
    if len(subtitles) > 50000:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề quá lớn'}), 413
    if not 0.25 <= video_speed <= 4.0 or not 1.0 <= video_zoom <= 3.0 or not -100 <= video_pan_x <= 100 or not -100 <= video_pan_y <= 100:
        return jsonify({'success': False, 'error': 'Thông số tốc độ/zoom/pan nằm ngoài giới hạn'}), 400
    if aspect_ratio not in {'original', '9:16', '1:1', '21:9'} or resolution not in {'original', '720p', '1080p', '4k'}:
        return jsonify({'success': False, 'error': 'Tỉ lệ hoặc độ phân giải không hợp lệ'}), 400
    if encoder not in {'libx264', 'h264_nvenc', 'h264_mf', 'h264_amf', 'h264_qsv'} or bitrate_mode not in {'VBR', 'CBR'} or not 500 <= bitrate <= 100000:
        return jsonify({'success': False, 'error': 'Encoder hoặc bitrate không hợp lệ'}), 400
    if not input_video or not is_path_allowed(input_video, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        return jsonify({'success': False, 'error': 'Video đầu vào không hợp lệ hoặc chưa được cho phép'}), 400
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if not is_path_allowed(output_dir):
        return jsonify({'success': False, 'error': 'Thư mục đầu ra chưa được người dùng cho phép'}), 403
    os.makedirs(output_dir, exist_ok=True)
    if not output_name:
        return jsonify({'success': False, 'error': 'Tên file đầu ra không hợp lệ'}), 400
    if not output_name.lower().endswith('.mp4'):
        output_name += '.mp4'
    try:
        safe_join(output_dir, output_name, extensions={'.mp4'})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    for optional_path, extensions in ((manual_audio, _AUDIO_EXTENSIONS), (manual_srt, {'.srt'}), (original_srt_path, {'.srt'})):
        if optional_path and not is_path_allowed(optional_path, must_exist=True, extensions=extensions):
            return jsonify({'success': False, 'error': f'File phụ trợ không hợp lệ: {optional_path}'}), 400
    try:
        dubbing['enabled'] = parse_bool(dubbing.get('enabled'), False)
        dubbing['speed'] = max(0.5, min(2.0, float(dubbing.get('speed', 1.0))))
        dubbing['threads'] = max(1, min(8, int(dubbing.get('threads', 4))))
        nested_manual_audio = str(dubbing.get('manual_audio') or '').strip()
        if nested_manual_audio and not is_path_allowed(nested_manual_audio, must_exist=True, extensions=_AUDIO_EXTENSIONS):
            return jsonify({'success': False, 'error': 'File lồng tiếng thủ công không hợp lệ'}), 400
        stem_cfg = dubbing.get('stem_separation') or {}
        if stem_cfg and not isinstance(stem_cfg, dict):
            return jsonify({'success': False, 'error': 'Cấu hình tách âm thanh không hợp lệ'}), 400
        precomputed_path = str(stem_cfg.get('precomputed_cleaned_path') or '').strip()
        if precomputed_path and not is_path_allowed(precomputed_path, must_exist=True, extensions=_AUDIO_EXTENSIONS):
            return jsonify({'success': False, 'error': 'File stem đã xử lý không hợp lệ'}), 400
        logo_data = data.get('logo') or {}
        if logo_data and not isinstance(logo_data, dict):
            return jsonify({'success': False, 'error': 'Cấu hình logo không hợp lệ'}), 400
        logo_path = str(logo_data.get('path') or '').strip()
        if logo_path and not is_path_allowed(logo_path, must_exist=True, extensions={'.png', '.jpg', '.jpeg', '.webp'}):
            return jsonify({'success': False, 'error': 'File logo không hợp lệ'}), 400
    except (TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': f'Cấu hình lồng tiếng không hợp lệ: {exc}'}), 400

    with _export_lock:
        if _export_active:
            return jsonify({'success': False, 'error': 'Một tác vụ xuất video khác đang chạy'}), 409
        _export_active = True
        STOP_EXPORT_FLAG = False

    def generate():
        nonlocal mode, manual_audio, input_video
        blurred_temp_video = None
        process = None
        try:
            ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
            
            if not input_video or not os.path.exists(input_video):
                yield f"data: 🛑 ERROR: Không tìm thấy video đầu vào: {input_video}\n\n"
                return

            # Helper to probe video duration and audio track
            def probe_video_info(v_path):
                d_sec = 0.0
                has_aud = True
                try:
                    ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe') if 'ffmpeg.exe' in ffmpeg_path else 'ffprobe'
                    if os.path.exists(ffprobe_path) or ffprobe_path == 'ffprobe':
                        cmd_probe = [
                            ffprobe_path, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type',
                            '-of', 'json', v_path
                        ]
                        res_p = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=30, **ffmpeg_installer.get_stealth_subprocess_kwargs())
                        if res_p.returncode == 0:
                            info_p = json.loads(res_p.stdout)
                            d_sec = float(info_p.get('format', {}).get('duration', 0.0))
                            has_aud = any(s.get('codec_type') == 'audio' for s in info_p.get('streams', []))
                            if d_sec > 0:
                                return d_sec, has_aud
                except Exception:
                    pass

                # Fallback to ffmpeg -i
                try:
                    cmd = [ffmpeg_path, '-i', v_path]
                    proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace', timeout=30, **ffmpeg_installer.get_stealth_subprocess_kwargs())
                    m = re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)', proc.stderr)
                    if m:
                        h, mins, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
                        d_sec = h * 3600 + mins * 60 + s
                    has_aud = 'Audio:' in proc.stderr
                    if d_sec > 0:
                        return d_sec, has_aud
                except Exception:
                    pass

                # Fallback to cv2
                try:
                    import cv2
                    cap = cv2.VideoCapture(v_path)
                    if cap.isOpened():
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                        cap.release()
                        if fps > 0 and frames > 0:
                            d_sec = float(frames / fps)
                except Exception:
                    pass

                return d_sec, has_aud

            video_duration, has_orig_audio = probe_video_info(input_video)

            # --- Generate temp SRT from subtitles array for Burn-In (ƯU TIÊN CHỮ DỊCH TIẾNG VIỆT) ---
            temp_srt_path = None
            if subtitles and isinstance(subtitles, list) and len(subtitles) > 0:
                temp_srt_path = os.path.join(output_dir, f'temp_subs_{int(time.time())}.srt')
                def format_srt_time(seconds):
                    hrs = int(seconds // 3600)
                    mins = int((seconds % 3600) // 60)
                    secs = int(seconds % 60)
                    msecs = int(round((seconds - int(seconds)) * 1000))
                    return f"{hrs:02d}:{mins:02d}:{secs:02d},{msecs:03d}"
                
                try:
                    with open(temp_srt_path, 'w', encoding='utf-8') as f:
                        for i, sub in enumerate(subtitles, 1):
                            t_start = format_srt_time(float(sub.get('startSeconds', 0)))
                            t_end = format_srt_time(float(sub.get('endSeconds', 0)))
                            translated_txt = sub.get('translation', '').strip()
                            orig_txt = sub.get('text', '').strip() or sub.get('original_text', '').strip()
                            display_text = translated_txt if translated_txt else orig_txt
                            f.write(f"{i}\n{t_start} --> {t_end}\n{display_text}\n\n")
                except Exception as e:
                    yield f"data: ⚠️ Lỗi tạo file phụ đề tạm: {str(e)}\n\n"
                    temp_srt_path = None

            # ═══════════════════════════════════════════════════════
            # 1. DYNAMIC BLUR: Chuẩn bị bộ lọc làm mờ (ƯU TIÊN CHỮ GỐC)
            # ═══════════════════════════════════════════════════════
            dyn_blur_filters = []
            if blur_original_subtitles and input_video and os.path.exists(input_video):
                # 1.1 Tạo danh sách câu phụ đề làm mờ ưu tiên CHỮ GỐC của phim
                orig_blur_entries = []
                
                if subtitles and isinstance(subtitles, list) and len(subtitles) > 0:
                    for sub in subtitles:
                        s_start = float(sub.get('startSeconds', 0))
                        s_end = float(sub.get('endSeconds', 0))
                        # ƯU TIÊN CHỮ GỐC: original_text -> text -> translation
                        orig_txt = str(sub.get('original_text') or sub.get('text') or '').strip()
                        if not orig_txt:
                            orig_txt = str(sub.get('translation') or '').strip()
                        ai_box = sub.get('aiBox')
                        if s_end > s_start:
                            if ai_box and isinstance(ai_box, dict) and 'x_pct' in ai_box and 'w_pct' in ai_box:
                                box_x_r = float(ai_box['x_pct']) / 100.0
                                box_w_r = float(ai_box['w_pct']) / 100.0
                                vis_s = ai_box.get('visual_start') or sub.get('visual_start')
                                vis_e = ai_box.get('visual_end') or sub.get('visual_end')
                                if vis_s is not None and vis_e is not None:
                                    orig_blur_entries.append((s_start, s_end, orig_txt, box_x_r, box_w_r, float(vis_s), float(vis_e)))
                                else:
                                    orig_blur_entries.append((s_start, s_end, orig_txt, box_x_r, box_w_r))
                            else:
                                orig_blur_entries.append((s_start, s_end, orig_txt))
                elif original_srt_path and os.path.exists(original_srt_path):
                    from auto_edit_pipeline import parse_srt_entries
                    orig_blur_entries = parse_srt_entries(original_srt_path)
                elif manual_srt and os.path.exists(manual_srt):
                    from auto_edit_pipeline import parse_srt_entries
                    orig_blur_entries = parse_srt_entries(manual_srt)
                elif temp_srt_path and os.path.exists(temp_srt_path):
                    from auto_edit_pipeline import parse_srt_entries
                    orig_blur_entries = parse_srt_entries(temp_srt_path)

                if orig_blur_entries:
                    already_scanned = len(orig_blur_entries) > 0 and all(len(item) >= 5 for item in orig_blur_entries)
                    if already_scanned:
                        yield f"data: 🎯 [Dynamic Blur] Đã nạp thành công tọa độ AI Pixel từ Preview cho {len(orig_blur_entries)} câu phụ đề!\n\n"
                    elif blur_use_ai_scan:
                        yield f"data: 🚀 [Dynamic Blur] Kích hoạt AI quét tọa độ (AI Scan)...\n\n"
                        try:
                            from ocr_module import scan_subtitles_pixel_boxes_generator
                            for status, data_payload in scan_subtitles_pixel_boxes_generator(input_video, ocr_region, orig_blur_entries):
                                if status == "progress":
                                    yield f"data: ✨ {data_payload}\n\n"
                                elif status == "done":
                                    orig_blur_entries = data_payload
                        except Exception as e:
                            yield f"data: ⚠️ [AI Scan Lỗi] {str(e)}. Fallback về tính toán độ rộng mặc định...\n\n"
                    else:
                        yield f"data: ✨ [Dynamic Blur] Phát hiện {len(orig_blur_entries)} đoạn phụ đề. Đang tính toán độ rộng làm mờ tự động theo CHỮ GỐC của video...\n\n"
                    
                    try:
                        from auto_edit_pipeline import build_dynamic_blur_filter_chain
                        blur_sz = max(5, min(30, blur_intensity))
                        y_ratio = float(ocr_region.get('y', 81.5)) / 100.0 if ocr_region.get('y') is not None else 0.815
                        h_ratio = float(ocr_region.get('h', 9.5)) / 100.0 if ocr_region.get('h') is not None else 0.095
                        x_ratio = float(ocr_region.get('x', 20)) / 100.0 if ocr_region.get('x') is not None else 0.20
                        w_box = float(ocr_region.get('w', 60)) / 100.0 if ocr_region.get('w') is not None else 0.60
                        center_x = x_ratio + (w_box / 2.0)
                        
                        lead_s = abs(blur_lead_offset)
                        pad_s = blur_padding
                        
                        dyn_blur_filters, _ = build_dynamic_blur_filter_chain(
                            "0:v", orig_blur_entries,
                            blur_sz=blur_sz,
                            y_ratio=y_ratio,
                            h_ratio=h_ratio,
                            center_x_ratio=center_x,
                            lead_sec=lead_s,
                            pad_sec=pad_s
                        )
                    except Exception as e:
                        yield f"data: ⚠️ [Dynamic Blur] Lỗi: {str(e)}. Tiếp tục với video gốc...\n\n"
                else:
                    yield "data: ⚠️ [Dynamic Blur] Không tìm thấy phụ đề gốc để xác định thời gian và vị trí làm mờ. Bỏ qua blur.\n\n"
                
            # ═══════════════════════════════════════════════════════
            # 2. AI DUBBING: Tạo track lồng tiếng AI từ phụ đề
            # ═══════════════════════════════════════════════════════
            dub_track = None
            is_dubbing_enabled = dubbing.get('enabled', False)
            dubbing_mode = dubbing.get('mode', 'tts')
            
            # Parse subtitles from manual_srt if subtitles list is empty
            subs_for_dubbing = subtitles or []
            if is_dubbing_enabled and dubbing_mode == 'tts' and not subs_for_dubbing:
                srt_candidate = manual_srt or original_srt_path
                if srt_candidate and os.path.exists(srt_candidate):
                    try:
                        from auto_edit_pipeline import parse_srt_entries
                        raw_entries = parse_srt_entries(srt_candidate)
                        subs_for_dubbing = [{"text": txt, "startSeconds": s, "endSeconds": e} for s, e, txt in raw_entries]
                    except Exception:
                        pass

            if is_dubbing_enabled:
                if dubbing_mode == 'tts':
                    if not subs_for_dubbing:
                        yield "data: 🛑 [LỖI LỒNG TIẾNG] Danh sách phụ đề trống! Vui lòng nạp hoặc dịch phụ đề trước khi xuất video có lồng tiếng.\n\n"
                    else:
                        voice_id = dubbing.get('voice_id', 'ngoc_huyen')
                        speed_dub = dubbing.get('speed', 1.0)
                        yield f"data: 🎙️ Đang tiến hành tạo giọng lồng tiếng AI cho {len(subs_for_dubbing)} câu phụ đề (Giọng: {voice_id})...\n\n"
                        import ai_dubbing
                        
                        open_speaker_key = ''
                        api_keys_file = API_KEYS_FILE
                        if os.path.exists(api_keys_file):
                            with open(api_keys_file, 'r', encoding='utf-8') as f:
                                for line in f:
                                    if line.startswith('openSpeakerApiKey='):
                                        open_speaker_key = line.split('=', 1)[1].strip()
                                        
                        temp_dub_dir = os.path.join(output_dir, f'dubbing_temp_{int(time.time())}')
                        dub_threads = dubbing.get('threads', 4)
                        try:
                            for event_type, msg in ai_dubbing.build_dubbing_track_for_subtitles_generator(
                                subtitles=subs_for_dubbing,
                                voice_id=voice_id,
                                speed=speed_dub,
                                temp_dir=temp_dub_dir,
                                open_speaker_key=open_speaker_key,
                                min_total_duration=video_duration,
                                max_workers=dub_threads,
                                check_stop=lambda: STOP_EXPORT_FLAG
                            ):
                                if STOP_EXPORT_FLAG:
                                    yield "data: 🛑 Đã dừng tiến trình lồng tiếng theo yêu cầu khẩn cấp.\n\n"
                                    return
                                if event_type == 'progress':
                                    yield f"data: {msg}\n\n"
                                elif event_type == 'done':
                                    dub_track = msg
                                    
                            if STOP_EXPORT_FLAG:
                                yield "data: 🛑 Đã dừng tiến trình xuất video.\n\n"
                                return
                            if dub_track and os.path.exists(dub_track):
                                yield "data: ✅ Đã tạo và đồng bộ xong track âm thanh lồng tiếng AI!\n\n"
                            else:
                                yield "data: 🛑 [LỖI LỒNG TIẾNG] Không tạo được track âm thanh lồng tiếng AI! Vui lòng kiểm tra lại giọng đọc hoặc API key.\n\n"
                        except Exception as e:
                            yield f"data: 🛑 [LỖI LỒNG TIẾNG] Lỗi ngoại lệ: {str(e)}\n\n"
                elif dubbing_mode == 'manual' and (dubbing.get('manual_audio') or manual_audio):
                    dub_track = dubbing.get('manual_audio') or manual_audio
                    if os.path.exists(dub_track):
                        yield f"data: 🎵 Sử dụng file âm thanh lồng tiếng có sẵn: {os.path.basename(dub_track)}\n\n"
                    else:
                        yield f"data: 🛑 [LỖI ÂM THANH] File âm thanh thủ công không tồn tại: {dub_track}\n\n"
                        dub_track = None

            # ═══════════════════════════════════════════════════════
            # 3. VIDEO & AUDIO PIPELINE EXPORT (FFMPEG ENGINE)
            # ═══════════════════════════════════════════════════════
            os.makedirs(output_dir, exist_ok=True)
            out_file_name = output_name if output_name.lower().endswith('.mp4') else f"{output_name}.mp4"
            final_output_path = safe_join(output_dir, out_file_name, extensions={'.mp4'})
            
            yield f"data: 🚀 Đang khởi chạy bộ biên mã FFmpeg ({encoder})...\n\n"

            # Construct Video Filter Complex
            v_filters = []
            curr_v = "0:v"

            # 3.0 Dynamic Blur (Single-Pass Integrated Engine)
            if dyn_blur_filters:
                v_filters.extend(dyn_blur_filters)
                last_blur_tag = re.search(r'\[([a-zA-Z0-9_]+)\]$', dyn_blur_filters[-1])
                if last_blur_tag:
                    curr_v = last_blur_tag.group(1)

            # 3.0b Video Zoom & Crop
            if video_zoom > 1.01:
                crop_w = f"iw/{video_zoom:.4f}"
                crop_h = f"ih/{video_zoom:.4f}"
                crop_x = f"(iw-{crop_w})/2 - ({video_pan_x:.1f}*(iw/800))"
                crop_y = f"(ih-{crop_h})/2 - ({video_pan_y:.1f}*(ih/450))"
                v_filters.append(f"[{curr_v}]crop=w={crop_w}:h={crop_h}:x='max(0,min(iw-ow,{crop_x}))':y='max(0,min(ih-oh,{crop_y}))'[v_cropped]")
                curr_v = "v_cropped"

            # 3.1 Speed
            if abs(video_speed - 1.0) > 0.01:
                v_filters.append(f"[{curr_v}]setpts=PTS/{video_speed:.4f}[v_speed]")
                curr_v = "v_speed"

            # 3.2 Mirror Flip
            if mirror_flip:
                v_filters.append(f"[{curr_v}]hflip[v_flip]")
                curr_v = "v_flip"

            # 3.3 Aspect Ratio & Resolution
            if aspect_ratio == '9:16':
                v_filters.append(f"[{curr_v}]scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
                curr_v = "v_aspect"
            elif aspect_ratio == '1:1':
                v_filters.append(f"[{curr_v}]scale=1080:1080:force_original_aspect_ratio=decrease,pad=1080:1080:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
                curr_v = "v_aspect"
            elif aspect_ratio == '21:9':
                v_filters.append(f"[{curr_v}]scale=1920:822:force_original_aspect_ratio=decrease,pad=1920:822:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
                curr_v = "v_aspect"
            elif resolution == '1080p':
                v_filters.append(f"[{curr_v}]scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
                curr_v = "v_aspect"
            elif resolution == '720p':
                v_filters.append(f"[{curr_v}]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
                curr_v = "v_aspect"
            elif resolution == '4k':
                v_filters.append(f"[{curr_v}]scale=3840:2160:force_original_aspect_ratio=decrease,pad=3840:2160:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
                curr_v = "v_aspect"

            # 3.4 Subtitles (Hardcode / Burn-In)
            if subtitles_enabled:
                srt_target = temp_srt_path or manual_srt or original_srt_path
                if srt_target and os.path.exists(srt_target):
                    escaped_srt = srt_target.replace('\\', '/').replace(':', '\\:')
                    font_name = re.sub(r'[^\w .-]', '', str(subtitle_style.get('font', 'Arial')))[:80] or 'Arial'
                    font_size = max(8, min(120, int(subtitle_style.get('size', 18))))
                    def hex_to_ass(hex_val, default='&H00FFFFFF'):
                        if not hex_val: return default
                        h = str(hex_val).lstrip('#')
                        if len(h) == 6:
                            return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
                        return default
                    primary_col = hex_to_ass(subtitle_style.get('color'), '&H00FFFFFF')
                    outline_col = hex_to_ass(subtitle_style.get('outline_color'), '&H00000000')
                    outline_w = max(0, min(10, int(subtitle_style.get('outline', 2))))
                    bold_flag = 1 if parse_bool(subtitle_style.get('bold'), False) else 0
                    italic_flag = 1 if parse_bool(subtitle_style.get('italic'), False) else 0
                    style_str = f"Fontname={font_name},Fontsize={font_size},PrimaryColour={primary_col},OutlineColour={outline_col},BorderStyle=1,Outline={outline_w},Bold={bold_flag},Italic={italic_flag},Alignment=2,MarginV=25"
                    v_filters.append(f"[{curr_v}]subtitles='{escaped_srt}':force_style='{style_str}'[v_sub]")
                    curr_v = "v_sub"
            else:
                yield "data: ℹ️ [Phụ đề] Tùy chọn chèn phụ đề đang TẮT -> Video xuất ra sẽ KHÔNG có phụ đề.\n\n"

            # Inputs initialization
            inputs = ['-i', input_video]
            dub_input_idx = None
            if dub_track and os.path.exists(dub_track):
                dub_input_idx = len(inputs) // 2
                inputs.extend(['-i', dub_track])

            # 3.5 Logo Watermark Overlay
            logo_data = data.get('logo') or {}
            logo_enabled = parse_bool(logo_data.get('enabled'), False)
            logo_path = logo_data.get('path', '').strip()
            
            if logo_enabled and logo_path and os.path.exists(logo_path):
                logo_input_idx = len(inputs) // 2
                inputs.extend(['-i', logo_path])

                x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
                y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
                w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
                h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
                opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

                v_filters.append(f"[{logo_input_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f}[logo_alpha]")
                v_filters.append(f"[logo_alpha][{curr_v}]scale2ref=w='main_w*{w_pct/100:.4f}':h='main_h*{h_pct/100:.4f}':force_original_aspect_ratio=decrease[logo_scaled][v_ref]")
                v_filters.append(f"[v_ref][logo_scaled]overlay=x='main_w*{x_pct/100:.4f}':y='main_h*{y_pct/100:.4f}'[v_logo]")
                curr_v = "v_logo"

            # Final video output label
            if not v_filters:
                v_filters.append("[0:v]null[v_final]")
            else:
                v_filters[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[v_final]', v_filters[-1])

            # 3.6 AI Stem & Vocal Separation (Lọc bỏ giọng thoại cũ, giữ lại hiệu ứng SFX)
            stem_enabled = parse_bool(dubbing.get('remove_original_vocals'), False) or (
                isinstance(dubbing.get('stem_separation'), dict)
                and parse_bool(dubbing.get('stem_separation', {}).get('enabled'), False)
            )
            stem_mode = 'mdx_net_hq4'
            stem_device = 'auto'
            precomputed_cleaned_path = ''
            if isinstance(dubbing.get('stem_separation'), dict):
                stem_cfg = dubbing.get('stem_separation', {})
                stem_mode = stem_cfg.get('mode', 'mdx_net_hq4')
                stem_device = stem_cfg.get('device', 'auto')
                precomputed_cleaned_path = stem_cfg.get('precomputed_cleaned_path', '')

            sfx_input_idx = None
            if stem_enabled and has_orig_audio:
                try:
                    cleaned_sfx = None
                    if precomputed_cleaned_path and os.path.exists(precomputed_cleaned_path) and os.path.getsize(precomputed_cleaned_path) > 1000:
                        cleaned_sfx = precomputed_cleaned_path
                        print(f"[Export Pipeline] ⚡ Tái sử dụng file âm thanh SFX đã tách sẵn: {cleaned_sfx}")
                    else:
                        import audio_separator
                        temp_stem_dir = os.path.join(ROOT_DIR, "output", "temp_stems")
                        sep_res = audio_separator.separate_audio_stems(input_video, output_dir=temp_stem_dir, mode=stem_mode, device=stem_device)
                        cleaned_sfx = sep_res.get('cleaned_path')

                    if cleaned_sfx and os.path.exists(cleaned_sfx):
                        sfx_input_idx = len(inputs) // 2
                        inputs.extend(['-i', cleaned_sfx])
                except Exception as e:
                    print(f"Lỗi tách âm thanh AI: {e}")

            # Construct Audio Filter Complex
            voice_vol = float(dubbing.get('voice_volume', 1.0))
            orig_vol = float(dubbing.get('original_volume', 0.3))
            ducking = bool(dubbing.get('audio_ducking', True))
            
            a_filters = []
            orig_src = f"[{sfx_input_idx}:a]" if sfx_input_idx is not None else "[0:a]"
            
            if dub_input_idx is not None:
                if has_orig_audio and orig_vol > 0.01:
                    if abs(video_speed - 1.0) > 0.01:
                        a_filters.append(f"{orig_src}atempo={video_speed:.4f},volume={orig_vol:.2f}[a_orig]")
                    else:
                        a_filters.append(f"{orig_src}volume={orig_vol:.2f}[a_orig]")
                    a_filters.append(f"[{dub_input_idx}:a]volume={voice_vol:.2f}[a_voice]")
                    if ducking:
                        a_filters.append(f"[a_voice]asplit=2[a_voice_ctrl][a_voice_mix]")
                        a_filters.append(f"[a_orig][a_voice_ctrl]sidechaincompress=threshold=0.08:ratio=5:attack=20:release=350[a_orig_ducked]")
                        a_filters.append(f"[a_orig_ducked][a_voice_mix]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[a_final]")
                    else:
                        a_filters.append(f"[a_orig][a_voice]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0[a_final]")
                else:
                    a_filters.append(f"[{dub_input_idx}:a]volume={voice_vol:.2f}[a_final]")
            else:
                if has_orig_audio:
                    if abs(video_speed - 1.0) > 0.01:
                        a_filters.append(f"{orig_src}atempo={video_speed:.4f}[a_final]")
                    else:
                        a_filters.append(f"{orig_src}anull[a_final]")
                else:
                    a_filters.append(f"aevalsrc=0:d={video_duration or 10}:s=44100[a_final]")

            full_filter_complex = ";".join(v_filters + a_filters)

            # ── Encoder Selection with Hardware Probe ──
            # Helper to check if a GPU encoder actually works on this machine
            def is_encoder_supported(enc_name):
                try:
                    cmd_t = [
                        ffmpeg_path, '-y', '-f', 'lavfi', '-i', 'nullsrc=s=64x64:d=0.1',
                        '-c:v', enc_name, '-f', 'null', '-'
                    ]
                    res_t = subprocess.run(cmd_t, capture_output=True, text=True, timeout=10, **ffmpeg_installer.get_stealth_subprocess_kwargs())
                    return res_t.returncode == 0, res_t.stderr
                except Exception as exc:
                    return False, str(exc)

            # Use a NEW local variable to avoid Python UnboundLocalError
            active_encoder = encoder  # encoder is from the outer scope (read-only)

            if 'nvenc' in active_encoder.lower():
                ok, err_detail = is_encoder_supported('h264_nvenc')
                if not ok:
                    yield "data: ⚠️ [CẢNH BÁO GPU] Bộ mã hóa NVIDIA NVENC không hoạt động trên máy này.\n\n"
                    if 'driver does not support' in err_detail.lower() or 'minimum required' in err_detail.lower():
                        yield "data: 📋 Nguyên nhân: Driver card đồ họa NVIDIA quá cũ, không hỗ trợ phiên bản NVENC API mới.\n\n"
                        yield "data: 💡 Giải pháp: Cập nhật Driver NVIDIA lên phiên bản 610.00 trở lên tại: https://www.nvidia.com/download/index.aspx\n\n"
                    elif 'no capable devices found' in err_detail.lower():
                        yield "data: 📋 Nguyên nhân: Máy tính không có card đồ họa NVIDIA hỗ trợ mã hóa phần cứng.\n\n"
                    else:
                        yield f"data: 📋 Chi tiết từ FFmpeg: {err_detail[:300]}\n\n"
                    yield "data: 🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...\n\n"
                    active_encoder = 'libx264'
            elif 'mf' in active_encoder.lower():
                ok, err_detail = is_encoder_supported('h264_mf')
                if not ok:
                    yield "data: ⚠️ [CẢNH BÁO GPU] Bộ mã hóa MediaFoundation không hoạt động trên máy này.\n\n"
                    yield "data: 🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...\n\n"
                    active_encoder = 'libx264'
            elif 'amf' in active_encoder.lower():
                ok, err_detail = is_encoder_supported('h264_amf')
                if not ok:
                    yield "data: ⚠️ [CẢNH BÁO GPU] Bộ mã hóa AMD AMF không hoạt động trên máy này.\n\n"
                    yield "data: 📋 Nguyên nhân: Driver AMD Adrenalin quá cũ hoặc card đồ họa không hỗ trợ AMF.\n\n"
                    yield "data: 💡 Giải pháp: Cập nhật Driver AMD tại: https://www.amd.com/en/support\n\n"
                    yield "data: 🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...\n\n"
                    active_encoder = 'libx264'
            elif 'qsv' in active_encoder.lower():
                ok, err_detail = is_encoder_supported('h264_qsv')
                if not ok:
                    yield "data: ⚠️ [CẢNH BÁO GPU] Bộ mã hóa Intel QSV không hoạt động trên máy này.\n\n"
                    yield "data: 📋 Nguyên nhân: Driver Intel Graphics quá cũ hoặc CPU không hỗ trợ Quick Sync Video.\n\n"
                    yield "data: 💡 Giải pháp: Cập nhật Driver Intel tại: https://www.intel.com/content/www/us/en/download-center\n\n"
                    yield "data: 🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...\n\n"
                    active_encoder = 'libx264'

            # Assemble main FFmpeg command
            cmd_export = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'info']
            
            if trim_enabled and trim_start:
                cmd_export.extend(['-ss', trim_start])
            if trim_enabled and trim_end:
                cmd_export.extend(['-to', trim_end])
                
            cmd_export.extend(inputs)
            cmd_export.extend(['-filter_complex', full_filter_complex])
            cmd_export.extend(['-map', '[v_final]', '-map', '[a_final]'])

            # Encoding parameters based on validated active_encoder
            if 'nvenc' in active_encoder.lower():
                cmd_export.extend(['-c:v', 'h264_nvenc', '-preset', 'p4', '-b:v', f'{bitrate}k'])
            elif 'mf' in active_encoder.lower():
                cmd_export.extend(['-c:v', 'h264_mf', '-b:v', f'{bitrate}k'])
            elif 'amf' in active_encoder.lower():
                cmd_export.extend(['-c:v', 'h264_amf', '-quality', 'speed', '-b:v', f'{bitrate}k'])
            elif 'qsv' in active_encoder.lower():
                cmd_export.extend(['-c:v', 'h264_qsv', '-preset', 'medium', '-b:v', f'{bitrate}k'])
            else:
                cmd_export.extend(['-c:v', 'libx264', '-preset', 'medium', '-crf', '19'])
                
            cmd_export.extend([
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '192k',
                final_output_path
            ])

            encoder_label = "GPU " + active_encoder.upper() if active_encoder != 'libx264' else "CPU libx264"
            yield f"data: 🎬 Đang xuất video chất lượng cao (Bộ mã hóa: {encoder_label}, Âm lượng lồng tiếng: {int(voice_vol*100)}%, Âm lượng gốc: {int(orig_vol*100)}%)...\n\n"

            global current_export_process, _export_active
            process = subprocess.Popen(
                cmd_export,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=ROOT_DIR,
                encoding='utf-8',
                errors='replace',
                **ffmpeg_installer.get_stealth_subprocess_kwargs()
            )
            with _export_lock:
                current_export_process = process

            time_regex = re.compile(r'time=(\d+):(\d+):([0-9.]+)')
            for line in iter(process.stdout.readline, ''):
                if line:
                    l_str = line.strip()
                    if 'frame=' in l_str or 'time=' in l_str or 'size=' in l_str or 'speed=' in l_str:
                        m = time_regex.search(l_str)
                        if m and video_duration > 0:
                            hrs = int(m.group(1))
                            mins = int(m.group(2))
                            secs = float(m.group(3))
                            cur_sec = hrs * 3600 + mins * 60 + secs
                            pct = min(99, int((cur_sec / video_duration) * 100))
                            yield f"data: ⏳ [Tiến độ: {pct}%] {l_str}\n\n"
                        else:
                            yield f"data: ⏳ {l_str}\n\n"
                    elif 'error' in l_str.lower() or 'warning' in l_str.lower():
                        yield f"data: ℹ️ {l_str}\n\n"

            process.stdout.close()
            return_code = process.wait()
            
            if return_code == 0 and os.path.exists(final_output_path):
                file_size_mb = os.path.getsize(final_output_path) / (1024 * 1024)
                yield f"data: ✅ [XUẤT THÀNH CÔNG] Video đã được lưu tại: {final_output_path} ({file_size_mb:.1f} MB)\n\n"
                yield f"data: --- HOÀN THÀNH QUÁ TRÌNH TẠO ---\n\n"
            else:
                yield f"data: 🛑 [LỖI XUẤT VIDEO] FFmpeg không thể tạo được video đầu ra.\n\n"
                yield f"data: 📋 Nguyên nhân có thể: File video đầu vào bị hỏng, bộ mã hóa ({active_encoder}) gặp sự cố, hoặc ổ đĩa đầy.\n\n"
                yield f"data: 💡 Thử lại với bộ mã hóa CPU (libx264) nếu đang dùng GPU, hoặc kiểm tra lại file video gốc.\n\n"
        except GeneratorExit:
            _terminate_process_tree(process)
        except Exception as ex:
            yield f"data: 🛑 [LỖI HỆ THỐNG]: {str(ex)}\n\n"
        finally:
            with _export_lock:
                if current_export_process is process:
                    current_export_process = None
                _export_active = False
            if blurred_temp_video and os.path.exists(blurred_temp_video):
                try:
                    os.remove(blurred_temp_video)
                except Exception:
                    pass

    return Response(generate(), mimetype='text/event-stream')

@video_edit_bp.route('/api/stop_export', methods=['POST'])
@video_edit_bp.route('/api/stop', methods=['POST'])
def stop_export_process():
    global current_export_process, STOP_EXPORT_FLAG
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    STOP_EXPORT_FLAG = True
    with _export_lock:
        process = current_export_process
    stopped = _terminate_process_tree(process)
        
    return jsonify({
        'success': True,
        'stopped': stopped,
        'message': 'Đã gửi yêu cầu dừng tác vụ xuất video hiện tại.'
    })

@video_edit_bp.route('/api/stop_ocr', methods=['POST'])
def stop_ocr():
    global STOP_OCR_FLAG
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    STOP_OCR_FLAG = True
    return jsonify({"status": "stopped"})

@video_edit_bp.route('/api/ocr_extract', methods=['POST'])
def ocr_extract():
    global STOP_OCR_FLAG, _ocr_active
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error

    data = request.get_json(silent=True) or {}
    video_path = str(data.get('video_path') or '').strip()
    region = data.get('region') or {}
    try:
        fps = max(0.1, min(30.0, float(data.get('fps', 2))))
        threads = max(1, min(8, int(data.get('threads', 2))))
    except (TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': f'Tham số OCR không hợp lệ: {exc}'}), 400
    device = str(data.get('device', 'cpu')).lower()
    if device not in {'cpu', 'cuda', 'auto'} or not isinstance(region, dict):
        return jsonify({'success': False, 'error': 'Device hoặc vùng OCR không hợp lệ'}), 400
    if not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        return jsonify({'success': False, 'error': 'Video OCR không hợp lệ hoặc chưa được cho phép'}), 400
    with _ocr_lock:
        if _ocr_active:
            return jsonify({'success': False, 'error': 'Một tác vụ OCR khác đang chạy'}), 409
        _ocr_active = True
        STOP_OCR_FLAG = False

    def generate():
        global _ocr_active
        import importlib
        import ocr_module
        importlib.reload(ocr_module)
        try:
            for msg in ocr_module.process_ocr(video_path, region, fps, threads, device, lambda: STOP_OCR_FLAG):
                yield msg
        except Exception as e:
            yield f"data: Lỗi xử lý OCR: {str(e)}\n\n"
        finally:
            with _ocr_lock:
                _ocr_active = False

    return Response(generate(), mimetype='text/event-stream')

@video_edit_bp.route('/api/ocr/scan_preview_single', methods=['POST'])
def ocr_scan_preview_single():
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    import ocr_module
    data = request.json or {}
    video_path = data.get('video_path')
    try:
        timestamp = float(data.get('timestamp', 0))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'error': 'Timestamp không hợp lệ'}), 400
    region = data.get('region') or {'x': 20, 'y': 81.5, 'w': 60, 'h': 9.5}

    if not video_path or not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp đường dẫn video'}), 400

    if not isinstance(region, dict):
        return jsonify({'success': False, 'error': 'Vùng OCR không hợp lệ'}), 400
    timestamp = max(0.0, timestamp)

    result = ocr_module.scan_single_frame_box(video_path, timestamp, region)
    return jsonify(result)

@video_edit_bp.route('/api/ocr/scan_preview_boxes', methods=['POST'])
def ocr_scan_preview_boxes():
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    import json
    import ocr_module
    data = request.json or {}
    video_path = data.get('video_path')
    region = data.get('region') or {'x': 20, 'y': 81.5, 'w': 60, 'h': 9.5}
    subtitles = data.get('subtitles') or []

    if not video_path or not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        return jsonify({'success': False, 'error': 'Vui lòng cung cấp đường dẫn video'}), 400
    if not isinstance(region, dict) or not isinstance(subtitles, list) or len(subtitles) > 50000:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề không hợp lệ hoặc quá lớn'}), 400

    def generate():
        try:
            for event in ocr_module.scan_preview_boxes_generator(video_path, region, subtitles):
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'type': 'error', 'message': str(ex)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@video_edit_bp.route('/api/review/styles', methods=['GET'])
def review_get_styles():
    import review_styles
    return jsonify({
        'styles': review_styles.REVIEW_STYLES
    })

@video_edit_bp.route('/api/review/generate_prompt', methods=['POST'])
def review_generate_prompt():
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_review')
    if not allowed:
        return jsonify({'error': perm_msg}), 403

    import review_phim
    data = request.json or {}
    video_path = data.get('video_path')
    srt_path = data.get('srt_path')
    review_style = data.get('review_style', 'dramatic')
    custom_style_prompt = data.get('custom_style_prompt', '')
    
    if not video_path or not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        return jsonify({'error': 'Video path is invalid or missing'}), 400
    if srt_path and not is_path_allowed(srt_path, must_exist=True, extensions={'.srt'}):
        return jsonify({'error': 'Subtitle path is invalid or not allowed'}), 400
    if review_style not in {'dramatic', 'humorous', 'deep_analysis', 'fast_paced', 'horror', 'emotional', 'custom'}:
        return jsonify({'error': 'Review style không hợp lệ'}), 400
    custom_style_prompt = str(custom_style_prompt)[:10000]
    
    prompt, err = review_phim.extract_prompt_from_video(
        video_path,
        custom_srt_path=srt_path,
        review_style=review_style,
        custom_style_prompt=custom_style_prompt
    )
    if err:
        return jsonify({'error': err}), 400
        
    return jsonify({'prompt': prompt})

@video_edit_bp.route('/api/review/stop', methods=['POST'])
@video_edit_bp.route('/api/stop_auto_edit', methods=['POST'])
def review_stop():
    global review_stop_flag
    permission_error = _require_permission('can_access_review')
    if permission_error:
        return permission_error
    review_stop_flag = True
    return jsonify({'success': True})

@video_edit_bp.route('/api/review/check_cache', methods=['POST'])
def review_check_cache():
    permission_error = _require_permission('can_access_review')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if not is_path_allowed(output_dir):
        return jsonify({'success': False, 'error': 'Thư mục cache chưa được người dùng cho phép'}), 403
    temp_dir = safe_join(output_dir, 'auto_edit_temp')
    
    if not os.path.exists(temp_dir):
        return jsonify({"has_cache": False})
        
    cached_files = []
    if os.path.exists(os.path.join(temp_dir, 'script.txt')): cached_files.append('script.txt')
    if os.path.exists(os.path.join(temp_dir, 'voice_review.wav')): cached_files.append('voice_review.wav')
    if os.path.exists(os.path.join(temp_dir, 'voice_review_cleaned.srt')): cached_files.append('voice_review_cleaned.srt')
    if os.path.exists(os.path.join(temp_dir, 'timeline.json')): cached_files.append('timeline.json')
    
    return jsonify({
        "has_cache": len(cached_files) > 0,
        "files": cached_files
    })

@video_edit_bp.route('/api/review/start', methods=['POST'])
def review_start():
    global review_stop_flag, _review_active
    permission_error = _require_permission('can_access_review')
    if permission_error:
        return permission_error

    import review_phim
    data = request.get_json(silent=True) or {}
    video_path = str(data.get('video_path') or '').strip()
    mode = str(data.get('mode', 'manual')).lower()
    voice_id = re.sub(r'[^a-zA-Z0-9_-]', '_', str(data.get('voice_id', 'ngoc_huyen')))[:100]
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    output_name = secure_filename(str(data.get('output_name', 'video_review.mp4')))
    srt_path = str(data.get('srt_path') or '').strip()
    if mode not in {'manual', 'api', 'narration'}:
        return jsonify({'success': False, 'error': 'Chế độ review không hợp lệ'}), 400
    if not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        return jsonify({'success': False, 'error': 'Video review không hợp lệ hoặc chưa được cho phép'}), 400
    if srt_path and not is_path_allowed(srt_path, must_exist=True, extensions={'.srt'}):
        return jsonify({'success': False, 'error': 'File phụ đề review không hợp lệ'}), 400
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if not is_path_allowed(output_dir):
        return jsonify({'success': False, 'error': 'Thư mục đầu ra chưa được người dùng cho phép'}), 403
    os.makedirs(output_dir, exist_ok=True)
    if not output_name:
        return jsonify({'success': False, 'error': 'Tên video đầu ra không hợp lệ'}), 400
    if not output_name.lower().endswith('.mp4'):
        output_name += '.mp4'
    try:
        safe_join(output_dir, output_name, extensions={'.mp4'})
    except ValueError as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400
    data.update({
        'video_path': video_path,
        'voice_id': voice_id,
        'output_dir': output_dir,
        'output_name': output_name,
        'srt_path': srt_path,
    })

    script_json = data.get('script_json')
    if mode == 'manual' and (not isinstance(script_json, list) or not script_json or len(script_json) > 50000):
        return jsonify({'success': False, 'error': 'Kịch bản JSON không hợp lệ hoặc quá lớn'}), 400
    with _review_lock:
        if _review_active:
            return jsonify({'success': False, 'error': 'Một tác vụ Review Phim khác đang chạy'}), 409
        _review_active = True
        review_stop_flag = False
    
    def check_stop_func():
        return review_stop_flag

    # Chế độ Kể lại Video (Narration) - Giữ nguyên video, overlay voice
    if mode == 'narration':
        def narration_generate():
            global _review_active
            try:
                import auto_edit_pipeline
                try:
                    import importlib
                    importlib.reload(auto_edit_pipeline)
                except Exception:
                    pass
                yield from auto_edit_pipeline.run_narration_workflow(data, check_stop_func)
            except Exception as e:
                yield f"data: 🛑 Lỗi hệ thống: {str(e)}\n\n"
            finally:
                with _review_lock:
                    _review_active = False
            
        return Response(narration_generate(), mimetype='text/event-stream')

    if mode == 'api':
        openai_key = data.get('openai_key')
        openai_base_url = data.get('openai_base_url', 'https://api.openai.com/v1')
        openai_model = data.get('openai_model', 'gpt-5.6-luna')
        srt_path = data.get('srt_path')
        
        def api_generate():
            global _review_active
            try:
                import auto_edit_pipeline
                try:
                    import importlib
                    importlib.reload(auto_edit_pipeline)
                except Exception:
                    pass
                yield from auto_edit_pipeline.run_auto_edit_workflow(data, check_stop_func)
            except Exception as e:
                yield f"data: 🛑 Lỗi hệ thống: {str(e)}\n\n"
            finally:
                with _review_lock:
                    _review_active = False
            
        return Response(api_generate(), mimetype='text/event-stream')
    
    def generate():
        global _review_active
        try:
            import review_phim
            import importlib
            importlib.reload(review_phim)
            yield from review_phim.build_video_workflow(
                video_path=video_path,
                script_json=script_json,
                voice_id=voice_id,
                output_dir=output_dir,
                output_name=output_name,
                check_stop=check_stop_func
            )
        except Exception as e:
            yield f"data: 🛑 Lỗi không xác định: {str(e)}\n\n"
        finally:
            with _review_lock:
                _review_active = False
            
    return Response(generate(), mimetype='text/event-stream')

