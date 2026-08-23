import os
import json
import time
import requests
import subprocess
import re
import shutil
import random
import traceback
import ffmpeg_installer
import ai_dubbing
import timeline_sanitizer

def is_api_voice(voice_id):
    if not voice_id:
        return False
    if voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh']:
        return False
    if voice_id.startswith('rvc_') or voice_id.startswith('edge_'):
        return False
    try:
        import custom_voices
        if custom_voices.get_voice_by_id(voice_id):
            return False
    except:
        pass
    return True

def parse_srt_time(t_str):
    t_str = t_str.strip().replace(',', '.')
    parts = t_str.split(':')
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return float(t_str)

def format_srt_time(seconds):
    seconds = max(0.0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    if ms >= 1000:
        s += 1
        ms -= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def parse_srt_entries(srt_file_path):
    if not srt_file_path or not os.path.exists(srt_file_path):
        return []
    entries = []
    try:
        with open(srt_file_path, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        blocks = re.split(r'\n\s*\n', content.strip())
        for block in blocks:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if len(lines) >= 2:
                time_line = lines[1] if '-->' in lines[1] else lines[0]
                if '-->' in time_line:
                    t_parts = time_line.split('-->')
                    s_sec = parse_srt_time(t_parts[0])
                    e_sec = parse_srt_time(t_parts[1])
                    txt_lines = lines[2:] if time_line == lines[1] else lines[1:]
                    txt = " ".join(txt_lines).strip()
                    entries.append((s_sec, e_sec, txt))
    except Exception:
        pass
    return entries

def calc_sub_width_ratio(text):
    """Tính tỷ lệ chiều rộng box blur khớp với độ dài câu chữ (chữ ngắn -> blur ngắn, chữ dài -> blur dài)"""
    if not text:
        return 0.35
    clean = text.strip()
    if not clean:
        return 0.35
    units = 0.0
    for char in clean:
        code = ord(char)
        # Ký tự CJK (Trung, Nhật, Hàn)
        if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0x3040 <= code <= 0x30FF) or (0xAC00 <= code <= 0xD7AF):
            units += 2.9
        elif char == ' ':
            units += 0.9
        else:
            units += 1.45
    return max(0.12, min(0.92, (units * 1.02 + 4.5) / 100.0))

def build_dynamic_blur_filter_chain(curr_v, active_intervals, blur_sz=15, y_ratio=0.815, h_ratio=0.095, center_x_ratio=0.50, lead_sec=0.18, pad_sec=0.22):
    """Xây dựng filter FFmpeg multi-bucket blur tự động bám sát chữ phụ đề theo độ dài và thời gian.
    Tự động gộp khoảng cách và chia nhỏ chunk (batching) an toàn để tránh tràn bộ nhớ stack biểu thức của FFmpeg.
    """
    BUCKETS = [0.18, 0.32, 0.48, 0.65, 0.85]
    bucket_map = {b: [] for b in BUCKETS}
    
    for item in active_intervals:
        box_x = None
        box_w = None
        vis_s = None
        vis_e = None
        if len(item) >= 7:
            s, e, txt, box_x, box_w, vis_s, vis_e = item[0], item[1], item[2], item[3], item[4], item[5], item[6]
        elif len(item) >= 5:
            s, e, txt, box_x, box_w = item[0], item[1], item[2], item[3], item[4]
        elif len(item) == 3:
            s, e, txt = item
        else:
            s, e = item[0], item[1]
            txt = ""
            
        # Áp dụng lead_sec, pad_sec và visual_start/end nếu có từ AI Scan
        s_lead = max(0.0, float(s) - lead_sec)
        if vis_s is not None and float(vis_s) >= 0:
            s_lead = min(s_lead, float(vis_s))

        e_trail = float(e) + pad_sec
        if vis_e is not None and float(vis_e) > float(e):
            e_trail = max(e_trail, float(vis_e))
        
        # Nếu có tọa độ Bounding Box AI thì dùng trực tiếp, ngược lại tính theo ký tự
        if box_w is not None and float(box_w) > 0:
            w = float(box_w)
        else:
            w = calc_sub_width_ratio(txt)
            
        chosen = next((b for b in BUCKETS if b >= w), BUCKETS[-1])
        bucket_map[chosen].append((s_lead, e_trail))
        
    filter_chain = []
    curr = curr_v
    step = 0
    MAX_EXPR_CHUNK = 25  # Giới hạn tối đa 25 biểu thức between() trên mỗi overlay để FFmpeg tuyệt đối không bị lỗi eval stack
    
    for b in BUCKETS:
        raw_intervals = bucket_map[b]
        if not raw_intervals:
            continue
            
        merged = []
        for interval in sorted(raw_intervals, key=lambda x: x[0]):
            if not merged:
                merged.append(list(interval))
            else:
                # Nếu khoảng cách giữa 2 phụ đề <= max(pad_sec + 0.25, 0.75s), gộp thành dải mờ liên tục chống nhấp nháy
                gap_bridge_threshold = max(pad_sec + 0.25, 0.75)
                if interval[0] <= merged[-1][1] + gap_bridge_threshold:
                    merged[-1][1] = max(merged[-1][1], interval[1])
                else:
                    merged.append(list(interval))
                    
        # Chia các khoảng thời gian thành các chunk nhỏ an toàn (chunk_size <= MAX_EXPR_CHUNK)
        chunks = [merged[i:i + MAX_EXPR_CHUNK] for i in range(0, len(merged), MAX_EXPR_CHUNK)]
        x_ratio = max(0.01, min(0.99 - b, center_x_ratio - (b / 2.0)))
        
        for ch in chunks:
            enable_expr = "+".join([f"between(t,{s:.2f},{e:.2f})" for s, e in ch])
            next_v = f"v_dynblur_{step}"
            filter_chain.append(f"[{curr}]split[v_bbase_{step}][v_bcrop_{step}]")
            filter_chain.append(f"[v_bcrop_{step}]crop=iw*{b:.3f}:ih*{h_ratio:.3f}:iw*{x_ratio:.3f}:ih*{y_ratio:.3f},avgblur=sizeX={blur_sz}:sizeY={blur_sz}[v_bblur_{step}]")
            filter_chain.append(f"[v_bbase_{step}][v_bblur_{step}]overlay=main_w*{x_ratio:.3f}:main_h*{y_ratio:.3f}:enable='{enable_expr}'[{next_v}]")
            curr = next_v
            step += 1
        
    return filter_chain, curr

def split_text_to_sentences(text):
    """Tách văn bản thành các câu riêng biệt để TTS từng câu."""
    text = text.strip()
    if not text:
        return []
    # Tách theo dấu câu kết thúc (.!?) hoặc xuống dòng kép
    raw_parts = re.split(r'(?<=[.!?])\s+|\n{2,}', text)
    sentences = []
    for part in raw_parts:
        part = part.strip()
        if not part:
            continue
        # Nếu câu quá dài (>80 ký tự), cố tách thêm ở dấu phẩy/chấm phẩy
        if len(part) > 80:
            sub_parts = re.split(r'(?<=[,;])\s+', part)
            buffer = ""
            for sp in sub_parts:
                if buffer and len(buffer) + len(sp) > 70:
                    sentences.append(buffer.strip())
                    buffer = sp
                else:
                    buffer = (buffer + " " + sp).strip() if buffer else sp
            if buffer:
                sentences.append(buffer.strip())
        else:
            sentences.append(part)
    return [s for s in sentences if len(s) > 1]

def enforce_max_2_lines_srt(srt_entries, max_chars_per_line=40):
    """Đảm bảo mỗi block SRT chỉ hiện tối đa 2 dòng trên màn hình.
    Nếu text dài hơn 2 dòng, tách thành nhiều block kế tiếp."""
    result = []
    for start, end, text in srt_entries:
        text = text.strip()
        if not text:
            continue
        words = text.split()
        # Tính số dòng nếu wrap ở max_chars_per_line
        lines = []
        current_line = ""
        for word in words:
            if current_line and len(current_line) + 1 + len(word) > max_chars_per_line:
                lines.append(current_line)
                current_line = word
            else:
                current_line = (current_line + " " + word).strip() if current_line else word
        if current_line:
            lines.append(current_line)
        
        if len(lines) <= 2:
            # OK, giữ nguyên (dùng \N cho 2 dòng nếu cần)
            display_text = "\n".join(lines)
            result.append((start, end, display_text))
        else:
            # Tách thành nhiều block, mỗi block tối đa 2 dòng
            total_dur = end - start
            total_chars = sum(len(l) for l in lines)
            chunks = []
            i = 0
            while i < len(lines):
                chunk_lines = lines[i:i+2]
                chunks.append("\n".join(chunk_lines))
                i += 2
            # Phân bổ thời gian theo tỷ lệ ký tự
            cursor = start
            for i, chunk_text in enumerate(chunks):
                chunk_chars = len(chunk_text.replace("\n", ""))
                chunk_dur = (total_dur * chunk_chars / total_chars) if total_chars > 0 else (total_dur / len(chunks))
                
                # To prevent float precision issues leaving a gap at the very end
                if i == len(chunks) - 1:
                    chunk_end = end
                else:
                    chunk_end = cursor + chunk_dur
                    
                result.append((cursor, chunk_end, chunk_text))
                cursor = chunk_end
    return result

def get_video_duration_ffprobe(video_path):
    """Lấy duration video bằng ffprobe, ffmpeg -i fallback, hoặc cv2 fallback."""
    if not video_path or not os.path.exists(video_path):
        return 0.0

    ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    
    # 1. Thử ffprobe nếu có binary
    ffprobe_candidates = []
    if os.name == 'nt':
        ffprobe_candidates.append(os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe'))
    ffprobe_candidates.append('ffprobe')
    
    for ff_p in ffprobe_candidates:
        if os.path.exists(ff_p) or ff_p == 'ffprobe':
            try:
                cmd = [ff_p, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', video_path]
                res = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
                val = float(res)
                if val > 0:
                    return val
            except Exception:
                pass

    # 2. Thử ffmpeg -i stderr inspection (luôn hoạt động vì ffmpeg.exe luôn có sẵn)
    try:
        cmd = [ffmpeg_path, '-i', video_path]
        proc = subprocess.run(cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
        m = re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)', proc.stderr)
        if m:
            h, mins, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
            val = h * 3600 + mins * 60 + s
            if val > 0:
                return val
    except Exception:
        pass

    # 3. Fallback OpenCV
    try:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS)
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
            cap.release()
            if fps > 0 and frames > 0:
                return float(frames / fps)
    except Exception:
        pass

    return 0.0

def run_ffmpeg_with_progress_yield(cmd, total_duration, start_pct, end_pct, desc, check_stop_func=None):
    """Chạy FFmpeg và yield % tiến độ dựa trên time= trong output."""
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding='utf-8',
        errors='replace'
    )
    last_reported_pct = -1
    last_report_time = 0
    time_regex = re.compile(r'time=(\d+):(\d+):([0-9.]+)')
    error_lines = []

    for line in iter(process.stdout.readline, ''):
        if not line:
            break
        if check_stop_func and check_stop_func():
            process.terminate()
            yield f"data: 🛑 Đã dừng tiến trình {desc}.\n\n"
            return False

        line_str = line.strip()
        if 'error' in line_str.lower() or 'fatal' in line_str.lower():
            error_lines.append(line_str)

        m = time_regex.search(line_str)
        if m and total_duration > 0:
            hrs = int(m.group(1))
            mins = int(m.group(2))
            secs = float(m.group(3))
            cur_sec = hrs * 3600 + mins * 60 + secs
            render_ratio = min(1.0, cur_sec / total_duration)
            overall_pct = int(start_pct + ((end_pct - start_pct) * render_ratio))
            now = time.time()
            if overall_pct >= last_reported_pct + 2 or (now - last_report_time > 2.0 and overall_pct > last_reported_pct):
                yield f"data: ⚙️ {desc}: {cur_sec:.0f}s/{total_duration:.0f}s ({overall_pct}%)\n\n"
                yield f"data: [PROGRESS] {overall_pct}\n\n"
                last_reported_pct = overall_pct
                last_report_time = now

    process.stdout.close()
    return_code = process.wait()
    if return_code != 0:
        if check_stop_func and check_stop_func():
            yield f"data: 🛑 Đã dừng tiến trình {desc}.\n\n"
            return False
        err_msg = "\n".join(error_lines[-5:]) if error_lines else f"Exit code {return_code}"
        yield f"data: 🛑 Lỗi khi {desc}: {err_msg}\n\n"
        return False
    return True

def generate_tts_per_sentence_stream(sentences, voice_id, speed, temp_dir, api_key_openspeaker='', check_stop_func=None, start_pct=20, end_pct=40):
    """
    Tạo TTS cho từng câu và yield progress real-time theo %.
    Yields:
      ('progress', (index, total, pct, snippet))
      ('error', error_str)
      ('done', (final_audio, final_srt, srt_entries))
    """
    ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe') if os.name == 'nt' else 'ffprobe'
    
    sentence_dir = os.path.join(temp_dir, 'sentences')
    os.makedirs(sentence_dir, exist_ok=True)
    
    is_kokoro = voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh']
    tts_url = "http://127.0.0.1:5000/api/tts/kokoro" if is_kokoro else "http://127.0.0.1:5000/api/tts/openspeaker"
    
    audio_segments = []  # (path, duration, text)
    total = len(sentences)
    
    for i, sentence in enumerate(sentences):
        if check_stop_func and check_stop_func():
            yield 'error', "STOPPED"
            return
        
        pct = int(start_pct + ((end_pct - start_pct) * (i + 1) / total)) if total > 0 else end_pct
        snippet = (sentence[:35] + '...') if len(sentence) > 35 else sentence
        yield 'progress', (i + 1, total, pct, snippet)
        
        filename = f"sent_{i}.wav" if is_kokoro else f"sent_{i}.mp3"
        tts_payload = {
            "text": sentence,
            "voice_id": voice_id,
            "speed": speed,
            "output_dir": sentence_dir,
            "filename": filename
        }
        if not is_kokoro and api_key_openspeaker:
            tts_payload['api_key'] = api_key_openspeaker
        
        try:
            res = requests.post(tts_url, json=tts_payload, timeout=120)
            if res.status_code != 200:
                yield 'error', f"Lỗi TTS câu {i+1}: {res.text}"
                return
        except Exception as e:
            yield 'error', f"Lỗi gọi API TTS câu {i+1}: {str(e)}"
            return
        
        audio_path = os.path.join(sentence_dir, filename)
        if not os.path.exists(audio_path):
            yield 'error', f"Không tìm thấy file audio câu {i+1}"
            return
        
        # Convert to WAV to avoid MP3 padding/desync issues
        wav_path = os.path.join(sentence_dir, f"sent_{i}_pcm.wav")
        try:
            conv_cmd = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error', '-i', audio_path, '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le', wav_path]
            subprocess.run(conv_cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as e:
            yield 'error', f"Lỗi convert WAV câu {i+1}: {e.stderr.decode()}"
            return
        
        # Đo duration trên file WAV (chính xác tuyệt đối bằng module wave)
        dur = 2.0
        try:
            import wave
            with wave.open(wav_path, 'rb') as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    dur = frames / float(rate)
        except Exception:
            dur = get_video_duration_ffprobe(wav_path)
            if dur <= 0:
                dur = 2.0
        
        audio_segments.append((wav_path, dur, sentence))
    
    if not audio_segments:
        yield 'error', "Không có câu nào để tạo TTS."
        return
    
    # Concat tất cả audio thành 1 file
    concat_list_path = os.path.join(sentence_dir, 'concat.txt')
    with open(concat_list_path, 'w', encoding='utf-8') as f:
        for seg_path, _, _ in audio_segments:
            f.write(f"file '{os.path.abspath(seg_path)}'\n")
    
    final_audio = os.path.join(temp_dir, 'voice_review.wav')
    cmd_concat = [
        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'concat', '-safe', '0', '-i', concat_list_path,
        '-c:a', 'pcm_s16le',
        final_audio
    ]
    proc = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        yield 'error', f"Lỗi concat audio: {proc.stderr}"
        return
    
    # Tạo SRT chính xác từ duration cộng dồn
    final_srt = os.path.join(temp_dir, 'voice_review.srt')
    cursor = 0.0
    srt_entries = []
    with open(final_srt, 'w', encoding='utf-8') as sf:
        for idx, (_, dur, txt) in enumerate(audio_segments):
            s_time = cursor
            e_time = cursor + dur
            sf.write(f"{idx+1}\n")
            sf.write(f"{format_srt_time(s_time)} --> {format_srt_time(e_time)}\n")
            sf.write(f"{txt}\n\n")
            srt_entries.append((s_time, e_time, txt))
            cursor = e_time
    
    yield 'done', (final_audio, final_srt, srt_entries)

def generate_tts_per_sentence(sentences, voice_id, speed, temp_dir, api_key_openspeaker='', check_stop_func=None, start_pct=20, end_pct=40):
    """Hàm wrapper tương thích ngược chạy generator trả về tuple kết quả cuối."""
    final_audio = None
    final_srt = None
    srt_entries = []
    error = None
    for msg_type, data in generate_tts_per_sentence_stream(sentences, voice_id, speed, temp_dir, api_key_openspeaker, check_stop_func, start_pct, end_pct):
        if msg_type == 'error':
            error = data
        elif msg_type == 'done':
            final_audio, final_srt, srt_entries = data
def resolve_openai_credentials(payload=None):
    if payload is None:
        payload = {}
    openai_key = payload.get('openai_key')
    openai_base_url = payload.get('openai_base_url') or 'https://api.openai.com/v1'
    openai_model = payload.get('openai_model') or 'gpt-5.6-luna'
    
    if not openai_key or not str(openai_key).strip() or str(openai_key).startswith('•'):
        root_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_files = [
            os.path.join(root_dir, 'api_keys.txt'),
            'api_keys.txt'
        ]
        try:
            import license_manager
            candidate_files.append(os.path.join(license_manager.get_user_data_dir(), 'api_keys.txt'))
        except Exception:
            pass

        for api_keys_file in candidate_files:
            if os.path.exists(api_keys_file):
                try:
                    with open(api_keys_file, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('openaiKey='):
                                openai_key = line.strip().split('=', 1)[1]
                            elif line.startswith('openaiBaseUrl=') and (not openai_base_url or openai_base_url == 'https://api.openai.com/v1'):
                                openai_base_url = line.strip().split('=', 1)[1]
                            elif line.startswith('openaiModel=') and (not openai_model or openai_model in ['gpt-4o-mini', 'gpt-5.6-luna']):
                                openai_model = line.strip().split('=', 1)[1]
                    if openai_key and not openai_key.startswith('•'):
                        break
                except Exception:
                    pass

        if not openai_key:
            try:
                import license_manager
                st = license_manager.get_current_license_status()
                vk = st.get('vip_api_keys') or {}
                if isinstance(vk, dict):
                    openai_key = vk.get('openaiKey') or vk.get('openai_key') or vk.get('api_key')
            except Exception:
                pass

        if not openai_key:
            openai_key = os.environ.get('OPENAI_API_KEY')

    return openai_key, openai_base_url, openai_model


def run_auto_edit_workflow(payload, check_stop_func):
    video_path = payload.get('video_path')
    srt_path = payload.get('srt_path')
    voice_id = payload.get('voice_id', 'ngoc_huyen')
    output_dir = payload.get('output_dir', 'output')
    output_name = payload.get('output_name', 'video_review.mp4')
    
    openai_key, openai_base_url, openai_model = resolve_openai_credentials(payload)
    api_key_openspeaker = payload.get('openspeaker_api_key', '')
    auto_subtitles = payload.get('auto_subtitles', True)
    
    # Advanced Anti-Flicker & Sync Parameters
    enable_scene_detect = payload.get('enable_scene_detect', True)
    snap_threshold = float(payload.get('snap_threshold', 0.6))
    min_clip_duration = float(payload.get('min_clip_duration', 1.2))
    max_speed_ratio_dev = float(payload.get('max_speed_ratio_deviation', 0.15))
    enable_crossfade = payload.get('enable_crossfade', False)
    crossfade_duration = float(payload.get('crossfade_duration', 0.15))
    encoder = payload.get('encoder', 'libx264')

    if not api_key_openspeaker:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        for p in [os.path.join(root_dir, 'api_keys.txt'), 'api_keys.txt']:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('openSpeakerApiKey='):
                            api_key_openspeaker = line.split('=', 1)[1].strip()
                            break
                if api_key_openspeaker:
                    break

    if not openai_key:
        yield "data: 🛑 Lỗi: Chưa tìm thấy OpenAI API Key. Vui lòng vào Cài đặt để nhập Key cá nhân hoặc bấm [Lấy API Cấp Sẵn] nếu bạn dùng gói VIP/1 Năm!\n\n"
        return

    if not srt_path or not os.path.exists(srt_path):
        yield "data: 🛑 Lỗi: Không tìm thấy file SRT đầu vào. Phải có SRT gốc để GPT làm việc!\n\n"
        return
    if not video_path or not os.path.exists(video_path):
        yield "data: 🛑 Lỗi: Không tìm thấy file Video đầu vào.\n\n"
        return

    # Luôn đọc nội dung SRT đầu vào ngay từ đầu để dùng cho tất cả các bước (kể cả khi dùng cache)
    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()

    # Luôn đảm bảo ffmpeg_path và cấu hình OpenAI sẵn sàng cho toàn bộ workflow
    ffmpeg_path = None
    try:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    except Exception as e:
        yield f"data: 🛑 Lỗi kiểm tra FFmpeg: {e}\n\n"
        return

    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    url = f"{openai_base_url.rstrip('/')}/chat/completions"

    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, 'auto_edit_temp')
    os.makedirs(temp_dir, exist_ok=True)
    
    def log(msg, step=None):
        if step:
            return f"data: [STEP] {step}\n\ndata: {msg}\n\n"
        return f"data: {msg}\n\n"

    use_cache = payload.get('use_cache', False)
    script_txt_path = os.path.join(temp_dir, 'script.txt')
    voice_audio_path = os.path.join(temp_dir, "voice_review.wav")
    voice_srt_path = os.path.join(temp_dir, "voice_review.srt")
    voice_srt_cleaned_path = os.path.join(temp_dir, "voice_review_cleaned.srt")
    json_path = os.path.join(temp_dir, 'timeline.json')
    sanitized_json_path = os.path.join(temp_dir, 'timeline_sanitized.json')

    try:
        # --- BƯỚC 1: LÊN KỊCH BẢN ---
        yield log("Đang đọc SRT và lên kịch bản review (Bước 1)...", step=1)
        yield log("[PROGRESS] 5")
        if check_stop_func(): return
        
        review_script = ""
        if use_cache and os.path.exists(script_txt_path):
            with open(script_txt_path, 'r', encoding='utf-8') as f:
                review_script = f.read()
            yield log(f"💚 Đã tìm thấy kịch bản cũ, tái sử dụng tại {script_txt_path}")
            yield log("[PROGRESS] 20")
        else:
            import prompt_vault
            prompt_script_template = prompt_vault.get_prompt('prompt_script')
            if not prompt_script_template:
                yield log("🛑 Không tìm thấy nội dung kịch bản mẫu prompt_script!")
                return
                
            target_minutes = payload.get('target_minutes', 5)
            target_words = int(target_minutes * 270)
            prompt_script = prompt_script_template.replace("{DÁN_NỘI_DUNG_SRT_VÀO_ĐÂY}", srt_content)\
                                                  .replace("{SỐ_PHÚT}", str(target_minutes))\
                                                  .replace("{SỐ_PHÚT x 270}", f"{target_words:,}".replace(",", "."))\
                                                  .replace("{SỐ_PHÚT x 240}", f"{target_words:,}".replace(",", "."))
            payload_gpt_1 = {
                "model": openai_model,
                "messages": [
                    {"role": "system", "content": "Bạn là chuyên gia review phim."},
                    {"role": "user", "content": prompt_script}
                ]
            }
            
            yield log("🤖 Đang gửi phụ đề tới ChatGPT để viết kịch bản review...")
            res1 = requests.post(url, headers=headers, json=payload_gpt_1, timeout=120)
            if res1.status_code != 200:
                yield log(f"🛑 Lỗi API GPT Bước 1: {res1.text}")
                return
                
            res1_json = res1.json()
            review_script = res1_json['choices'][0]['message']['content']
            u1 = res1_json.get('usage', {})
            token_str1 = f" (🪙 Tiêu thụ: {u1.get('total_tokens', 0):,} tokens - Prompt: {u1.get('prompt_tokens', 0):,}, Output: {u1.get('completion_tokens', 0):,})" if u1 else ""
            with open(script_txt_path, 'w', encoding='utf-8') as f:
                f.write(review_script)
            yield log(f"✅ Đã viết kịch bản xong, lưu tại {script_txt_path}{token_str1}")
            yield log("[PROGRESS] 20")
        
        # --- BƯỚC 2: TẠO GIỌNG ĐỌC (TỪNG CÂU - CHÍNH XÁC TIMESTAMP) ---
        yield log("Đang tạo giọng đọc (Bước 2 - Tách câu TTS)...", step=2)
        if check_stop_func(): return
        
        voice_speed = float(payload.get('voice_speed', 1.0))
        
        if use_cache and os.path.exists(voice_audio_path) and os.path.exists(voice_srt_path):
            yield log("💚 Đã tìm thấy file giọng đọc cũ, tái sử dụng.")
            yield log("[PROGRESS] 40")
        else:
            if is_api_voice(voice_id) and api_key_openspeaker:
                yield log("☁️ Đang gọi OpenSpeaker API tạo giọng đọc và phụ đề 1 lần (with_transcript)...")
                try:
                    temp_aud_raw = os.path.join(temp_dir, 'voice_raw.mp3')
                    ai_dubbing.synthesize_openspeaker_with_transcript(
                        review_script, voice_id, voice_speed, temp_aud_raw, voice_srt_path, api_key_openspeaker
                    )
                    
                    # Convert raw audio sang PCM WAV 24kHz để khớp pipeline
                    cmd_conv = [
                        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                        '-i', temp_aud_raw, '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le',
                        voice_audio_path
                    ]
                    subprocess.run(cmd_conv, check=True)
                    
                    yield log("✅ Đã nhận xong giọng đọc và phụ đề trực tiếp từ API!")
                    yield log("[PROGRESS] 40")
                except Exception as e:
                    yield log(f"⚠️ Lỗi gọi API tạo voice 1 lần ({str(e)}), chuyển sang luồng dự phòng (Tách câu)...")
            
            if not os.path.exists(voice_audio_path) or not os.path.exists(voice_srt_path):
                # Tách kịch bản thành câu riêng biệt (Luồng Local hoặc Fallback)
                sentences = split_text_to_sentences(review_script)
                yield log(f"Đã tách kịch bản thành {len(sentences)} câu.")
                
                if not sentences:
                    yield log("🛑 Lỗi: Kịch bản rỗng sau khi tách câu.")
                    return
                
                # TTS từng câu, concat, tạo SRT chính xác với cập nhật tiến trình %
                yield log(f"Đang tạo giọng đọc cho {len(sentences)} câu (Luồng Local)...")
                final_audio = None
                final_srt = None
                srt_entries = []
                error = None
                
                for msg_type, data in generate_tts_per_sentence_stream(
                    sentences, voice_id, voice_speed, temp_dir, api_key_openspeaker, check_stop_func, start_pct=20, end_pct=40
                ):
                    if msg_type == 'progress':
                        curr_i, total_i, pct, snippet = data
                        yield log(f"🎙️ Đang tạo giọng đọc câu {curr_i}/{total_i} ({pct}%): \"{snippet}\"")
                        yield log(f"[PROGRESS] {pct}")
                    elif msg_type == 'error':
                        error = data
                    elif msg_type == 'done':
                        final_audio, final_srt, srt_entries = data
                
                if error:
                    if error == "STOPPED":
                        return
                    yield log(f"🛑 {error}")
                    return
                if final_audio and final_audio != voice_audio_path and os.path.exists(final_audio):
                    shutil.copy2(final_audio, voice_audio_path)
                if final_srt and final_srt != voice_srt_path and os.path.exists(final_srt):
                    shutil.copy2(final_srt, voice_srt_path)
                
                yield log(f"✅ Đã tạo xong giọng đọc ({len(srt_entries)} block SRT chính xác).")
                yield log("[PROGRESS] 40")
            
        # --- BƯỚC 2.5: CHUẨN HÓA SRT (TỐI ĐA 2 DÒNG / BLOCK) ---
        yield log("Đang chuẩn hóa SRT giọng đọc (tối đa 2 dòng/block)...")
        if check_stop_func(): return
        
        if use_cache and os.path.exists(voice_srt_cleaned_path):
            yield log("💚 Đã tìm thấy file SRT giọng đọc đã chuẩn hóa, tái sử dụng.")
        else:
            # Đọc SRT vừa tạo và enforce max 2 dòng
            raw_entries = parse_srt_entries(voice_srt_path)
            cleaned_entries = enforce_max_2_lines_srt(raw_entries, max_chars_per_line=38)
            
            with open(voice_srt_cleaned_path, 'w', encoding='utf-8') as f:
                for idx, (s, e, txt) in enumerate(cleaned_entries):
                    f.write(f"{idx+1}\n")
                    f.write(f"{format_srt_time(s)} --> {format_srt_time(e)}\n")
                    f.write(f"{txt}\n\n")
            
            yield log(f"✅ Đã chuẩn hóa SRT: {len(raw_entries)} → {len(cleaned_entries)} block (tối đa 2 dòng/block).")
        yield log("[PROGRESS] 42")
        
        # --- BƯỚC 3: PHÂN TÍCH CẢNH (ĐẠO DIỄN / JSON) ---
        yield log("Đang phân tích cảnh bằng GPT (Bước 3)...", step=3)
        yield log("[PROGRESS] 43")
        if check_stop_func(): return
        
        timeline_data = []
        if use_cache and os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                try:
                    timeline_data = json.load(f)
                    yield log("💚 Đã tìm thấy file timeline cũ, tái sử dụng.")
                    yield log("[PROGRESS] 50")
                except Exception:
                    timeline_data = []
        
        if not timeline_data:
            import prompt_vault
            prompt_json_template = prompt_vault.get_prompt('prompt_json')
            if not prompt_json_template:
                yield log("🛑 Không tìm thấy nội dung mẫu prompt_json!")
                return
            
            with open(voice_srt_cleaned_path, 'r', encoding='utf-8') as f:
                voice_srt_content = f.read()
                
            prompt_json_final = prompt_json_template.replace("{DÁN_SRT_PHIM_GỐC_VÀO_ĐÂY}", srt_content).replace("{DÁN_SRT_VOICE_REVIEW_VÀO_ĐÂY}", voice_srt_content)
            
            payload_gpt_2 = {
                "model": openai_model,
                "messages": [
                    {"role": "system", "content": "Bạn là kỹ thuật viên dựng phim. Chỉ trả về mảng JSON, không giải thích gì thêm."},
                    {"role": "user", "content": prompt_json_final}
                ]
            }
            
            yield log("🤖 Đang gửi yêu cầu đạo diễn & khớp cảnh tới ChatGPT...")
            res3 = requests.post(url, headers=headers, json=payload_gpt_2, timeout=120)
            if res3.status_code != 200:
                yield log(f"🛑 Lỗi API GPT Bước 3: {res3.text}")
                return
                
            res3_json = res3.json()
            json_resp = res3_json['choices'][0]['message']['content']
            u3 = res3_json.get('usage', {})
            token_str3 = f" (🪙 Tiêu thụ: {u3.get('total_tokens', 0):,} tokens)" if u3 else ""
            
            # Auto-repair JSON
            if "```json" in json_resp:
                json_resp = json_resp.split("```json")[1].split("```")[0].strip()
            elif "```" in json_resp:
                json_resp = json_resp.split("```")[1].split("```")[0].strip()
                
            try:
                timeline_data = json.loads(json_resp)
            except json.JSONDecodeError as e:
                yield log(f"Cảnh báo: Lỗi định dạng JSON ({e}). Đang thử auto-repair...")
                json_resp = re.sub(r',\s*([\]}])', r'\1', json_resp)
                try:
                    timeline_data = json.loads(json_resp)
                except Exception as e2:
                    yield log(f"🛑 Không thể auto-repair JSON. Lỗi: {e2}\nNội dung trả về: {json_resp}")
                    return
                    
            if not isinstance(timeline_data, list):
                yield log(f"🛑 JSON trả về không phải dạng mảng (Array).")
                return
                
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(timeline_data, f, indent=4)
                
            yield log(f"✅ Đã phân tích xong {len(timeline_data)} phân đoạn sơ bộ.{token_str3}")
            yield log("[PROGRESS] 50")
        
        # --- BƯỚC 3.5: SCENE DETECTION & TIMELINE SANITIZER (CHỐNG NHÁY HÌNH) ---
        scene_cuts = []
        if enable_scene_detect:
            yield log("Đang quét điểm chuyển cảnh phim gốc (Scene Detection)...")
            if check_stop_func(): return
            
            for msg, cuts in timeline_sanitizer.extract_scene_cuts_with_progress(video_path, threshold=27.0, cache_dir=temp_dir, check_stop_func=check_stop_func):
                if check_stop_func(): return
                if msg:
                    yield log(msg)
                    if "Đang quét chuyển cảnh: " in msg:
                        try:
                            detect_pct = int(msg.split("Đang quét chuyển cảnh: ")[1].split("%")[0].strip())
                            overall_pct = int(50 + (8 * detect_pct / 100))
                            yield log(f"[PROGRESS] {overall_pct}")
                        except Exception:
                            pass
                if cuts is not None:
                    scene_cuts = cuts
        else:
            yield log("Bỏ qua quét chuyển cảnh (Scene Sanitizer tắt).")
        
        yield log("Đang tối ưu điểm cắt (Snap & Merge Timeline)...")
        sanitized_timeline, sanitize_logs = timeline_sanitizer.sanitize_timeline(
            timeline_data,
            scene_cuts,
            snap_threshold=snap_threshold,
            min_clip_duration=min_clip_duration,
            max_speed_ratio_deviation=max_speed_ratio_dev
        )
        
        for msg in sanitize_logs:
            yield log(msg)
            
        with open(sanitized_json_path, 'w', encoding='utf-8') as f:
            json.dump(sanitized_timeline, f, indent=4)
            
        yield log(f"✅ Đã lưu timeline tối ưu tại {sanitized_json_path}")
        yield log("[PROGRESS] 60")
        
        # --- BƯỚC 4: CẮT GHÉP & ĐỒNG BỘ ÂM THANH THEO TỪNG CLIP (FFmpeg) ---
        yield log("Đang tiến hành cắt video câm (Bước 4)...", step=4)
        if check_stop_func(): return
        
        silent_clip_files = []
        total_clips = len(sanitized_timeline)
        
        if total_clips == 0:
            yield log("🛑 Lỗi: Timeline sau khi tối ưu rỗng!")
            return

        blur_orig_subs = payload.get('blur_original_subtitles', True)
        blur_sz = max(3, min(40, int(payload.get('blur_intensity', 15))))
        blur_y = float(payload.get('blur_y_pos', 81.5)) / 100.0
        blur_lead_offset = abs(float(payload.get('blur_lead_offset', -180)) / 1000.0)
        blur_padding = float(payload.get('blur_padding', 220)) / 1000.0
        blur_ai_boxes = payload.get('ai_boxes') or []

        orig_sub_entries = parse_srt_entries(srt_path) if blur_orig_subs else []
        if blur_orig_subs and orig_sub_entries and blur_ai_boxes and isinstance(blur_ai_boxes, list):
            enriched = []
            for idx, entry in enumerate(orig_sub_entries):
                s, e = entry[0], entry[1]
                txt = entry[2] if len(entry) >= 3 else ''
                ai_b = blur_ai_boxes[idx] if idx < len(blur_ai_boxes) else None
                if ai_b and isinstance(ai_b, dict) and 'x_pct' in ai_b and 'w_pct' in ai_b:
                    bx = float(ai_b['x_pct']) / 100.0
                    bw = float(ai_b['w_pct']) / 100.0
                    vs = ai_b.get('visual_start')
                    ve = ai_b.get('visual_end')
                    if vs is not None and ve is not None:
                        enriched.append((s, e, txt, bx, bw, float(vs), float(ve)))
                    else:
                        enriched.append((s, e, txt, bx, bw))
                else:
                    enriched.append(entry)
            orig_sub_entries = enriched

        if blur_orig_subs and orig_sub_entries:
            yield log(f"✨ Kích hoạt làm mờ phụ đề gốc theo thời gian ({len(orig_sub_entries)} đoạn phát hiện, độ mờ: {blur_sz}px).")

        for i, clip in enumerate(sanitized_timeline):
            if check_stop_func(): return
            
            v_start = float(clip['start'])
            v_dur = float(clip['duration'])
            
            if v_dur <= 0:
                continue

            progress_pct = int(60 + (30 * (i + 1) / total_clips))
            yield log(f"🎬 [{i+1}/{total_clips}] ({progress_pct}%) Đang cắt clip câm (Video: {v_dur:.1f}s)...")
            yield log(f"[PROGRESS] {progress_pct}")

            # Phát hiện phụ đề gốc trong khoảng thời gian clip này
            active_orig_intervals = []
            if blur_orig_subs and orig_sub_entries:
                v_end_calc = v_start + v_dur
                for item in orig_sub_entries:
                    s, e = item[0], item[1]
                    if e > v_start and s < v_end_calc:
                        rel_s = max(0.0, s - v_start)
                        rel_e = min(v_dur, e - v_start)
                        if rel_e > rel_s:
                            if len(item) == 7:
                                active_orig_intervals.append((rel_s, rel_e, item[2], item[3], item[4], item[5], item[6]))
                            elif len(item) >= 5:
                                active_orig_intervals.append((rel_s, rel_e, item[2], item[3], item[4]))
                            else:
                                active_orig_intervals.append((rel_s, rel_e, item[2] if len(item) >= 3 else ''))

            # Xây dựng filter_complex cho VIDEO CÂM
            clip_silent_path = os.path.join(temp_dir, f"clip_silent_{i}.mp4")
            filter_chain = []
            curr_v = "0:v"

            # Làm mờ động phụ đề gốc (tự co giãn độ dài ôm sát chữ)
            if blur_orig_subs and active_orig_intervals:
                dyn_filters, curr_v = build_dynamic_blur_filter_chain(
                    curr_v, active_orig_intervals,
                    blur_sz=blur_sz,
                    y_ratio=blur_y,
                    h_ratio=0.095,
                    center_x_ratio=0.50,
                    lead_sec=blur_lead_offset,
                    pad_sec=blur_padding
                )
                filter_chain.extend(dyn_filters)

            if not filter_chain:
                vf_filter = "[0:v]null[v]"
            else:
                last = filter_chain[-1]
                filter_chain[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[v]', last)
                vf_filter = ";".join(filter_chain)
                
            cmd_mux = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-ss', str(v_start), '-t', str(v_dur),
                '-i', video_path,
                '-filter_complex', vf_filter,
                '-map', '[v]',
                '-c:v', encoder, '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
                '-an',
                clip_silent_path
            ]
            
            proc_m = subprocess.run(cmd_mux, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc_m.returncode != 0:
                yield log(f"🛑 Lỗi FFmpeg khi dựng clip #{i+1}: {proc_m.stderr}")
                return
                
            if os.path.exists(clip_silent_path):
                silent_clip_files.append(clip_silent_path)

        if not silent_clip_files:
            yield log("🛑 Lỗi: Không dựng được clip nào từ danh sách timeline.")
            return

        yield log("[PROGRESS] 90")

        # --- BƯỚC 5: NỐI TẤT CẢ CÁC CLIP CÂM LẠI ---
        yield log("Đang ghép nối toàn bộ video câm (Bước 5)...")
        yield log("[PROGRESS] 92")
        if check_stop_func(): return
        
        concat_txt = os.path.join(temp_dir, 'concat_silent.txt')
        with open(concat_txt, 'w', encoding='utf-8') as f:
            for c in silent_clip_files:
                f.write(f"file '{os.path.basename(c)}'\n")
                
        concat_silent_path = os.path.join(temp_dir, 'concat_silent.mp4')
        
        cmd_concat = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'concat', '-safe', '0',
            '-i', concat_txt,
            '-c', 'copy',
            concat_silent_path
        ]
        proc_c = subprocess.run(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc_c.returncode != 0:
            yield log(f"🛑 Lỗi ghép nối video: {proc_c.stderr}")
            return
            
        # --- BƯỚC 6: CHÈN AUDIO TỔNG VÀ PHỤ ĐỀ VÀO VIDEO GHÉP ---
        yield log("Đang chèn voice tổng và phụ đề vào video ghép (Bước 6)...")
        yield log("[PROGRESS] 95")
        if check_stop_func(): return

        if not output_name.lower().endswith('.mp4'):
            output_name += '.mp4'
        final_output = os.path.join(output_dir, output_name)

        # Logo Watermark
        logo_data = payload.get('logo') or {}
        logo_enabled = bool(logo_data.get('enabled', False))
        logo_path = logo_data.get('path', '').strip()

        overlay_inputs = ['-i', concat_silent_path, '-i', voice_audio_path]
        v_filters = []
        curr_v = "0:v"

        if auto_subtitles and os.path.exists(voice_srt_cleaned_path):
            escaped_srt = voice_srt_cleaned_path.replace('\\', '/').replace(':', '\\:')
            v_filters.append(f"[{curr_v}]subtitles='{escaped_srt}':force_style='Fontname=Arial,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=25,MarginL=20,MarginR=20,WrapStyle=0'[v_sub]")
            curr_v = "v_sub"

        if logo_enabled and logo_path and os.path.exists(logo_path):
            logo_idx = len(overlay_inputs) // 2
            overlay_inputs.extend(['-i', logo_path])
            x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
            y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
            w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
            h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
            opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

            v_filters.append(f"[{logo_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f}[logo_alpha]")
            v_filters.append(f"[logo_alpha][{curr_v}]scale2ref=w='main_w*{w_pct/100:.4f}':h='main_h*{h_pct/100:.4f}':force_original_aspect_ratio=decrease[logo_scaled][v_ref]")
            v_filters.append(f"[v_ref][logo_scaled]overlay=x='main_w*{x_pct/100:.4f}':y='main_h*{y_pct/100:.4f}'[v_logo]")
            curr_v = "v_logo"

        if not v_filters:
            vf_complex = "[0:v]null[v_out]"
        else:
            v_filters[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[v_out]', v_filters[-1])
            vf_complex = ";".join(v_filters)

        cmd_overlay = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            *overlay_inputs,
            '-filter_complex', vf_complex,
            '-map', '[v_out]', '-map', '1:a',
            '-c:v', encoder, '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            final_output
        ]
        
        proc_overlay = subprocess.run(cmd_overlay, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc_overlay.returncode != 0:
            yield log(f"🛑 Lỗi chèn âm thanh/sub cuối cùng: {proc_overlay.stderr}")
            return
            
        if not os.path.exists(final_output):
            yield log(f"🛑 Không tìm thấy file video đầu ra: {final_output}")
            return
            
        yield log(f"Tất cả đã xong! File được lưu tại: {final_output}", step=5)
        yield log("[PROGRESS] 100")
        
    except Exception as e:
        yield log(f"🛑 Lỗi không xác định trong Auto-Edit: {str(e)} | {traceback.format_exc()}")


def run_narration_workflow(payload, check_stop_func):
    """Chế độ 'Kể lại Video' - Giữ nguyên video gốc, overlay voice-over + phụ đề."""
    video_path = payload.get('video_path')
    srt_path = payload.get('srt_path')
    voice_id = payload.get('voice_id', 'ngoc_huyen')
    voice_speed = float(payload.get('voice_speed', 1.0))
    output_dir = payload.get('output_dir', 'output')
    output_name = payload.get('output_name', 'video_narration.mp4')
    
    openai_key, openai_base_url, openai_model = resolve_openai_credentials(payload)
    api_key_openspeaker = payload.get('openspeaker_api_key', '')
    encoder = payload.get('encoder', 'libx264')
    auto_subtitles = payload.get('auto_subtitles', True)
    blur_orig_subs = payload.get('blur_original_subtitles', True)
    orig_volume = float(payload.get('original_volume', 15)) / 100.0  # 0.0 - 1.0

    if not api_key_openspeaker:
        root_dir = os.path.dirname(os.path.abspath(__file__))
        for p in [os.path.join(root_dir, 'api_keys.txt'), 'api_keys.txt']:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('openSpeakerApiKey='):
                            api_key_openspeaker = line.split('=', 1)[1].strip()
                            break
                if api_key_openspeaker:
                    break

    if not openai_key:
        yield "data: 🛑 Lỗi: Chưa tìm thấy OpenAI API Key. Vui lòng vào Cài đặt để nhập Key cá nhân hoặc bấm [Lấy API Cấp Sẵn] nếu bạn dùng gói VIP/1 Năm!\n\n"
        return

    if not video_path or not os.path.exists(video_path):
        yield "data: 🛑 Lỗi: Không tìm thấy file Video đầu vào.\n\n"
        return
    if not srt_path or not os.path.exists(srt_path):
        yield "data: 🛑 Lỗi: Không tìm thấy file SRT đầu vào. Cần SRT gốc để GPT phân tích!\n\n"
        return

    with open(srt_path, 'r', encoding='utf-8') as f:
        srt_content = f.read()

    ffmpeg_path = None
    try:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    except Exception as e:
        yield f"data: 🛑 Lỗi kiểm tra FFmpeg: {e}\n\n"
        return

    headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
    url = f"{openai_base_url.rstrip('/')}/chat/completions"

    os.makedirs(output_dir, exist_ok=True)
    temp_dir = os.path.join(output_dir, 'narration_temp')
    os.makedirs(temp_dir, exist_ok=True)

    def log(msg, step=None):
        if step:
            return f"data: [STEP] {step}\n\ndata: {msg}\n\n"
        return f"data: {msg}\n\n"

    use_cache = payload.get('use_cache', False)
    script_txt_path = os.path.join(temp_dir, 'narration_script.txt')
    voice_audio_path = os.path.join(temp_dir, 'voice_narration.wav')
    voice_srt_path = os.path.join(temp_dir, 'voice_narration.srt')
    voice_srt_cleaned_path = os.path.join(temp_dir, 'voice_narration_cleaned.srt')

    try:
        # --- BƯỚC 1: ĐỌC VIDEO DURATION & LÊN KỊCH BẢN ---
        yield log("📐 Đang đo thời lượng video gốc...", step=1)
        if check_stop_func(): return

        video_duration = get_video_duration_ffprobe(video_path)
        if video_duration <= 0:
            yield log("🛑 Không thể đo thời lượng video.")
            return

        video_minutes = video_duration / 60.0
        yield log(f"Video gốc: {video_minutes:.1f} phút ({video_duration:.0f} giây).")
        yield log("[PROGRESS] 5")

        narration_script = ""
        if use_cache and os.path.exists(script_txt_path):
            with open(script_txt_path, 'r', encoding='utf-8') as f:
                narration_script = f.read()
            yield log(f"💚 Đã tìm thấy kịch bản cũ, tái sử dụng tại {script_txt_path}")
        else:
            # Đọc prompt narration qua Vault bảo mật
            import prompt_vault
            prompt_template = prompt_vault.get_prompt('prompt_narration')
            if not prompt_template:
                yield log("🛑 Không tìm thấy nội dung mẫu prompt_narration!")
                return

            target_words = int(video_minutes * 200)  # ~200 từ/phút (chậm hơn recap để vừa xem)
            prompt_final = prompt_template.replace("{DÁN_NỘI_DUNG_SRT_VÀO_ĐÂY}", srt_content) \
                                           .replace("{SỐ_PHÚT}", f"{video_minutes:.1f}") \
                                           .replace("{SỐ_GIÂY}", f"{video_duration:.0f}") \
                                           .replace("{SỐ_TỪ}", str(target_words))

            headers = {"Authorization": f"Bearer {openai_key}", "Content-Type": "application/json"}
            url = f"{openai_base_url.rstrip('/')}/chat/completions"

            payload_gpt = {
                "model": openai_model,
                "messages": [
                    {"role": "system", "content": "Bạn là chuyên gia review phim, viết kịch bản voice-over kể lại nội dung phim."},
                    {"role": "user", "content": prompt_final}
                ]
            }

            yield log("Đang gọi AI viết kịch bản kể lại phim...")
            res = requests.post(url, headers=headers, json=payload_gpt, timeout=180)
            if res.status_code != 200:
                yield log(f"🛑 Lỗi API GPT Bước 1: {res.text}")
                return

            res_json = res.json()
            narration_script = res_json['choices'][0]['message']['content']
            u = res_json.get('usage', {})
            token_str = f" (🪙 {u.get('total_tokens', 0):,} tokens)" if u else ""

            with open(script_txt_path, 'w', encoding='utf-8') as f:
                f.write(narration_script)
            yield log(f"✅ Đã viết kịch bản kể lại ({len(narration_script.split())} từ).{token_str}")

        yield log("[PROGRESS] 20")

        # --- BƯỚC 2: TẠO GIỌNG ĐỌC (TỪNG CÂU) ---
        yield log("Đang tạo giọng đọc (Bước 2 - Tách câu TTS)...", step=2)
        if check_stop_func(): return

        if use_cache and os.path.exists(voice_audio_path) and os.path.exists(voice_srt_path):
            yield log("💚 Đã tìm thấy file giọng đọc cũ, tái sử dụng.")
        else:
            if is_api_voice(voice_id) and api_key_openspeaker:
                yield log("☁️ Đang gọi OpenSpeaker API tạo giọng đọc và phụ đề 1 lần (with_transcript)...")
                try:
                    temp_aud_raw = os.path.join(temp_dir, 'voice_raw.mp3')
                    ai_dubbing.synthesize_openspeaker_with_transcript(
                        narration_script, voice_id, voice_speed, temp_aud_raw, voice_srt_path, api_key_openspeaker
                    )
                    
                    # Convert raw audio sang PCM WAV 24kHz để khớp pipeline
                    cmd_conv = [
                        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                        '-i', temp_aud_raw, '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le',
                        voice_audio_path
                    ]
                    subprocess.run(cmd_conv, check=True)
                    
                    yield log("✅ Đã nhận xong giọng đọc và phụ đề trực tiếp từ API!")
                    yield log("[PROGRESS] 50")
                except Exception as e:
                    yield log(f"⚠️ Lỗi gọi API tạo voice 1 lần ({str(e)}), chuyển sang luồng dự phòng (Tách câu)...")

            if not os.path.exists(voice_audio_path) or not os.path.exists(voice_srt_path):
                sentences = split_text_to_sentences(narration_script)
                yield log(f"Đã tách kịch bản thành {len(sentences)} câu.")

                if not sentences:
                    yield log("🛑 Kịch bản rỗng sau khi tách câu.")
                    return

                yield log(f"Đang tạo giọng đọc cho {len(sentences)} câu (Luồng Local)...")
                final_audio = None
                final_srt = None
                srt_entries = []
                error = None

                for msg_type, data in generate_tts_per_sentence_stream(
                    sentences, voice_id, voice_speed, temp_dir, api_key_openspeaker, check_stop_func, start_pct=20, end_pct=50
                ):
                    if msg_type == 'progress':
                        curr_i, total_i, pct, snippet = data
                        yield log(f"🎙️ Đang tạo giọng đọc câu {curr_i}/{total_i} ({pct}%): \"{snippet}\"")
                        yield log(f"[PROGRESS] {pct}")
                    elif msg_type == 'error':
                        error = data
                    elif msg_type == 'done':
                        final_audio, final_srt, srt_entries = data

                if error:
                    if error == "STOPPED": return
                    yield log(f"🛑 {error}")
                    return

                # Di chuyển file về đúng path mong muốn
                if final_audio and final_audio != voice_audio_path and os.path.exists(final_audio):
                    shutil.copy2(final_audio, voice_audio_path)
                if final_srt and final_srt != voice_srt_path and os.path.exists(final_srt):
                    shutil.copy2(final_srt, voice_srt_path)

                yield log(f"✅ Đã tạo xong giọng đọc ({len(srt_entries)} block SRT).")
                yield log("[PROGRESS] 50")

        yield log("[PROGRESS] 50")

        # --- BƯỚC 2.5: CHUẨN HÓA SRT (TỐI ĐA 2 DÒNG) ---
        if use_cache and os.path.exists(voice_srt_cleaned_path):
            yield log("💚 Tái sử dụng SRT chuẩn hóa.")
        else:
            raw_entries = parse_srt_entries(voice_srt_path)
            cleaned_entries = enforce_max_2_lines_srt(raw_entries, max_chars_per_line=38)
            with open(voice_srt_cleaned_path, 'w', encoding='utf-8') as f:
                for idx, (s, e, txt) in enumerate(cleaned_entries):
                    f.write(f"{idx+1}\n")
                    f.write(f"{format_srt_time(s)} --> {format_srt_time(e)}\n")
                    f.write(f"{txt}\n\n")
            yield log(f"✅ Chuẩn hóa SRT: {len(cleaned_entries)} block (tối đa 2 dòng/block).")

        yield log("[PROGRESS] 55")

        # --- BƯỚC 3: OVERLAY VOICE + SUB LÊN VIDEO GỐC ---
        yield log("Đang overlay giọng đọc & phụ đề lên video gốc (Bước 3)...", step=3)
        if check_stop_func(): return

        if not output_name.lower().endswith('.mp4'):
            output_name += '.mp4'

        # Xây dựng filter
        filter_parts = []
        curr_v = "0:v"

        # Làm mờ phụ đề gốc nếu bật
        if blur_orig_subs:
            blur_sz = max(3, min(40, int(payload.get('blur_intensity', 15))))
            blur_y = float(payload.get('blur_y_pos', 81.5)) / 100.0
            blur_lead_offset = abs(float(payload.get('blur_lead_offset', -180)) / 1000.0)
            blur_padding = float(payload.get('blur_padding', 220)) / 1000.0
            blur_ai_boxes = payload.get('ai_boxes') or []

            orig_sub_entries = parse_srt_entries(srt_path)
            if blur_ai_boxes and isinstance(blur_ai_boxes, list):
                enriched = []
                for idx, entry in enumerate(orig_sub_entries):
                    s, e = entry[0], entry[1]
                    txt = entry[2] if len(entry) >= 3 else ''
                    ai_b = blur_ai_boxes[idx] if idx < len(blur_ai_boxes) else None
                    if ai_b and isinstance(ai_b, dict) and 'x_pct' in ai_b and 'w_pct' in ai_b:
                        bx = float(ai_b['x_pct']) / 100.0
                        bw = float(ai_b['w_pct']) / 100.0
                        vs = ai_b.get('visual_start')
                        ve = ai_b.get('visual_end')
                        if vs is not None and ve is not None:
                            enriched.append((s, e, txt, bx, bw, float(vs), float(ve)))
                        else:
                            enriched.append((s, e, txt, bx, bw))
                    else:
                        enriched.append(entry)
                orig_sub_entries = enriched

            if orig_sub_entries:
                yield log(f"✨ Làm mờ {len(orig_sub_entries)} đoạn phụ đề gốc (Độ mờ: {blur_sz}px)...")
                dyn_filters, curr_v = build_dynamic_blur_filter_chain(
                    curr_v, orig_sub_entries,
                    blur_sz=blur_sz,
                    y_ratio=blur_y,
                    h_ratio=0.095,
                    center_x_ratio=0.50,
                    lead_sec=blur_lead_offset,
                    pad_sec=blur_padding
                )
                filter_parts.extend(dyn_filters)

        # Burn-in subtitle mới
        if auto_subtitles and os.path.exists(voice_srt_cleaned_path):
            escaped_srt = voice_srt_cleaned_path.replace('\\', '/').replace(':', '\\:')
            filter_parts.append(f"[{curr_v}]subtitles='{escaped_srt}':force_style='Fontname=Arial,Fontsize=18,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=1,Outline=2,Alignment=2,MarginV=25,MarginL=20,MarginR=20,WrapStyle=0'[v_sub]")
            curr_v = "v_sub"

        # Inputs cho FFmpeg
        inputs_list = ['-i', video_path, '-i', voice_audio_path]

        # Logo Watermark cho Narration
        logo_data = payload.get('logo') or {}
        logo_enabled = bool(logo_data.get('enabled', False))
        logo_path = logo_data.get('path', '').strip()
        if logo_enabled and logo_path and os.path.exists(logo_path):
            logo_idx = len(inputs_list) // 2
            inputs_list.extend(['-i', logo_path])
            x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
            y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
            w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
            h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
            opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

            filter_parts.append(f"[{logo_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f}[logo_alpha]")
            filter_parts.append(f"[logo_alpha][{curr_v}]scale2ref=w='main_w*{w_pct/100:.4f}':h='main_h*{h_pct/100:.4f}':force_original_aspect_ratio=decrease[logo_scaled][v_ref]")
            filter_parts.append(f"[v_ref][logo_scaled]overlay=x='main_w*{x_pct/100:.4f}':y='main_h*{y_pct/100:.4f}'[v_logo]")
            curr_v = "v_logo"

        # Hoàn tất video filter
        if not filter_parts:
            video_filter = f"[0:v]null[vout]"
        else:
            last = filter_parts[-1]
            filter_parts[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[vout]', last)
            video_filter = ";".join(filter_parts)

        # Kiểm tra xem video gốc có kênh âm thanh hay không
        has_orig_audio = True
        try:
            p_cmd = [ffmpeg_path, '-i', video_path]
            p_proc = subprocess.run(p_cmd, stderr=subprocess.PIPE, stdout=subprocess.PIPE, text=True, encoding='utf-8', errors='replace')
            has_orig_audio = 'Audio:' in p_proc.stderr
        except Exception:
            pass

        # AI Stem Separation (Lọc bỏ lời thoại cũ, giữ lại hiệu ứng SFX)
        stem_sep_data = payload.get('stem_separation', {})
        stem_enabled = bool(stem_sep_data.get('enabled', False) or payload.get('remove_original_vocals', False))
        sfx_idx = None
        if stem_enabled and has_orig_audio:
            yield log("🎛️ Đang chạy AI Stem Separator để lọc sạch lời thoại cũ & bảo lưu tiếng động hiện trường (SFX)...")
            try:
                import audio_separator
                stem_mode = stem_sep_data.get('mode', 'ai_neural')
                sep_res = audio_separator.separate_audio_stems(video_path, output_dir=temp_dir, mode=stem_mode)
                if sep_res.get('cleaned_path') and os.path.exists(sep_res.get('cleaned_path')):
                    sfx_idx = len(inputs_list) // 2
                    inputs_list.extend(['-i', sep_res.get('cleaned_path')])
            except Exception as e:
                yield log(f"⚠️ Lỗi tách âm thanh: {e} (Tiếp tục với âm thanh gốc)")

        # Audio mix: giảm volume gốc / SFX (nếu có audio) + overlay voice
        orig_audio_src = f"[{sfx_idx}:a]" if sfx_idx is not None else "[0:a]"
        if has_orig_audio and orig_volume > 0.01:
            audio_filter = f"{orig_audio_src}volume={orig_volume:.2f}[a_orig];[1:a]volume=2.5[a_voice];[a_orig][a_voice]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        else:
            audio_filter = f"[1:a]volume=2.5[aout]"

        full_filter = f"{video_filter};{audio_filter}"

        # BGM
        bgm_enabled = payload.get('bgm', {}).get('enabled', False)
        bgm_file = None
        if bgm_enabled:
            bgm_dir = 'backgroundmusic'
            if os.path.exists(bgm_dir):
                bgm_files = [os.path.join(bgm_dir, f) for f in os.listdir(bgm_dir) if f.endswith(('.mp3', '.m4a'))]
                if bgm_files:
                    bgm_file = random.choice(bgm_files)

        # Lệnh FFmpeg cuối
        temp_no_bgm = os.path.join(temp_dir, 'narration_no_bgm.mp4')
        render_target = temp_no_bgm if bgm_file else os.path.join(output_dir, output_name)

        cmd = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'info',
            *inputs_list,
            '-filter_complex', full_filter,
            '-map', '[vout]', '-map', '[aout]',
            '-c:v', encoder, '-preset', 'veryfast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-c:a', 'aac', '-b:a', '192k',
            '-shortest',
            render_target
        ]

        yield log(f"🎬 Đang render video gốc với giọng đọc và phụ đề ({video_duration:.0f}s)...")
        render_success = yield from run_ffmpeg_with_progress_yield(
            cmd,
            total_duration=video_duration,
            start_pct=55,
            end_pct=90,
            desc="Render video",
            check_stop_func=check_stop_func
        )
        if not render_success or not os.path.exists(render_target):
            yield log("🛑 Không thể hoàn tất render video.")
            return

        yield log("[PROGRESS] 90")

        # --- BƯỚC 4: THÊM BGM (NẾU BẬT) ---
        final_output = os.path.join(output_dir, output_name)

        if bgm_file:
            yield log(f"🎵 Đang mix nhạc nền: {os.path.basename(bgm_file)}...", step=4)
            bgm_vol = int(payload.get('bgm', {}).get('volume', 10)) / 100.0
            cmd_bgm = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-i', temp_no_bgm, '-i', bgm_file,
                '-filter_complex', f"[0:a]volume=1.0[a0];[1:a]volume={bgm_vol:.2f}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac',
                final_output
            ]
            proc_bgm = subprocess.run(cmd_bgm, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc_bgm.returncode != 0:
                yield log(f"⚠️ Lỗi mix BGM, sử dụng bản không nhạc nền: {proc_bgm.stderr[:200]}")
                shutil.copy2(temp_no_bgm, final_output)
        else:
            if bgm_enabled:
                yield log("Không tìm thấy nhạc nền, bỏ qua.")

        yield log("[PROGRESS] 95")

        if not os.path.exists(final_output):
            yield log(f"🛑 Không tìm thấy file đầu ra: {final_output}")
            return

        yield log(f"🎉 HOÀN THÀNH! Video kể lại phim đã lưu tại: {final_output}", step=5)
        yield log("[PROGRESS] 100")

    except Exception as e:
        yield log(f"🛑 Lỗi không xác định trong Narration: {str(e)} | {traceback.format_exc()}")
