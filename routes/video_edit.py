from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, shutil, collections, gc, hashlib
from routes.state import *
from routes.security import is_path_allowed, parse_bool, safe_join, register_user_path
from werkzeug.utils import secure_filename
import asr_manager
import ffmpeg_installer
from ocr_module import get_editor_temp_dir
from export_job_manager import get_export_job_manager, JobStage, JobState, ExportJob

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


def compute_tts_fingerprint(subtitles, voice_id, speed, video_duration, voice_profile=None):
    """Tạo mã băm SHA-256 fingerprint đại diện cho toàn bộ kịch bản và thông số lồng tiếng."""
    import custom_voices
    if not voice_profile:
        voice_profile = custom_voices.resolve_voice_profile(voice_id)
    h = hashlib.sha256()
    h.update(str(voice_id or '').strip().encode('utf-8'))
    h.update(f"{float(speed or 1.0):.3f}".encode('utf-8'))
    h.update(f"{round(float(video_duration or 0.0), 1)}".encode('utf-8'))
    h.update(str(voice_profile.get('gender', '')).lower().encode('utf-8'))
    h.update(str(voice_profile.get('lang', '')).lower().encode('utf-8'))
    h.update(str(voice_profile.get('provider', '')).lower().encode('utf-8'))
    h.update(str(voice_profile.get('version', 1)).encode('utf-8'))
    for s in (subtitles or []):
        txt = str(s.get('translation') or s.get('text') or '').strip()
        st = round(float(s.get('startSeconds', 0)), 2)
        et = round(float(s.get('endSeconds', 0)), 2)
        h.update(f"{st}-{et}:{txt}\n".encode('utf-8'))
    return h.hexdigest()


def is_tts_manifest_valid(temp_dir, current_fingerprint):
    """Kiểm tra xem track dubbed_timeline.wav có khớp fingerprint và hợp lệ không."""
    if not temp_dir or not os.path.isdir(temp_dir) or not current_fingerprint:
        return False
    manifest_file = os.path.join(temp_dir, 'tts_manifest.json')
    wav_file = os.path.join(temp_dir, 'dubbed_timeline.wav')
    if not os.path.exists(manifest_file) or not os.path.exists(wav_file):
        return False
    if os.path.getsize(wav_file) < 1000:
        return False
    try:
        with open(manifest_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        saved_fp = data.get('fingerprint')
        return bool(saved_fp and saved_fp == current_fingerprint)
    except Exception:
        return False


def save_tts_manifest(temp_dir, fingerprint, voice_id, speed, video_duration, sub_count):
    """Lưu manifest để nhận diện tái dùng track TTS khi retry encode mà không tạo lại 1213 câu."""
    try:
        manifest_file = os.path.join(temp_dir, 'tts_manifest.json')
        data = {
            'fingerprint': fingerprint,
            'voice_id': str(voice_id),
            'speed': float(speed),
            'video_duration': float(video_duration),
            'sub_count': int(sub_count),
            'updated_at': time.time()
        }
        with open(manifest_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logging.getLogger(__name__).warning(f"[TTSManifest] Không thể lưu manifest: {e}")

_filter_script_flag = None

def get_filter_script_flag(ffmpeg_exe):
    """
    Phát hiện tùy chọn truyền filter graph qua tệp tin phù hợp với phiên bản FFmpeg:
    - FFmpeg 7.0+ / 8.0+: Hỗ trợ cú pháp chuẩn -/filter_complex <tệp>
    - FFmpeg cũ (< 7.0): Hỗ trợ -filter_complex_script <tệp>
    """
    global _filter_script_flag
    if _filter_script_flag is not None:
        return _filter_script_flag
    try:
        import tempfile
        t_file = os.path.join(tempfile.gettempdir(), f'_probe_fc_{os.getpid()}.txt')
        with open(t_file, 'w', encoding='utf-8') as f:
            f.write('nullsrc=s=16x16:d=0.1[v]')
        r = subprocess.run(
            [ffmpeg_exe, '-y', '-/filter_complex', t_file, '-map', '[v]', '-f', 'null', '-'],
            capture_output=True,
            timeout=5,
            **ffmpeg_installer.get_stealth_subprocess_kwargs()
        )
        if os.path.exists(t_file):
            try:
                os.remove(t_file)
            except Exception:
                pass
        if r.returncode == 0:
            _filter_script_flag = '-/filter_complex'
            return _filter_script_flag
    except Exception:
        pass
    _filter_script_flag = '-filter_complex_script'
    return _filter_script_flag

def format_ass_time(sec: float) -> str:
    """Format seconds into ASS time format: H:MM:SS.cs"""
    sec = max(0.0, float(sec))
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int(round((sec - int(sec)) * 100))
    if cs >= 100:
        cs = 99
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


class OutputGeometry:
    def __init__(self, out_w: int, out_h: int, content_x: float, content_y: float, content_w: float, content_h: float):
        self.out_w = out_w
        self.out_h = out_h
        self.content_x = content_x
        self.content_y = content_y
        self.content_w = content_w
        self.content_h = content_h


def compute_output_geometry(src_w: int, src_h: int, out_w: int, out_h: int) -> OutputGeometry:
    if src_w <= 0 or src_h <= 0 or out_w <= 0 or out_h <= 0:
        return OutputGeometry(out_w, out_h, 0.0, 0.0, float(out_w), float(out_h))
    src_ar = float(src_w) / float(src_h)
    out_ar = float(out_w) / float(out_h)
    if abs(src_ar - out_ar) < 0.001:
        return OutputGeometry(out_w, out_h, 0.0, 0.0, float(out_w), float(out_h))
    if src_ar > out_ar:
        content_w = float(out_w)
        content_h = round(float(out_w) / src_ar)
    else:
        content_h = float(out_h)
        content_w = round(float(out_h) * src_ar)
    return OutputGeometry(out_w, out_h, (out_w - content_w) / 2.0, (out_h - content_h) / 2.0, content_w, content_h)


def remap_blur_entries_to_output_frame(orig_blur_entries, geometry, cur_out_w, cur_out_h, video_speed=1.0, mirror=False):
    speed = max(0.01, float(video_speed))

    def map_box(box_x, box_w, box_y, box_h):
        if mirror:
            box_x = 1.0 - box_x - box_w
        return (
            (geometry.content_x + geometry.content_w * box_x) / cur_out_w,
            (geometry.content_w * box_w) / cur_out_w,
            (geometry.content_y + geometry.content_h * box_y) / cur_out_h,
            (geometry.content_h * box_h) / cur_out_h,
        )

    result = []
    for item in orig_blur_entries:
        if isinstance(item, dict):
            s = float(item.get('start', item.get('startSeconds', 0))) / speed
            e = float(item.get('end', item.get('endSeconds', 0))) / speed
            txt = str(item.get('text', ''))
            box = item.get('box') or item
            if isinstance(box, dict) and 'x_pct' in box and 'w_pct' in box:
                bx, bw, by, bh = map_box(
                    float(box['x_pct']) / 100.0, float(box['w_pct']) / 100.0,
                    float(box.get('y_pct', 81.5)) / 100.0, float(box.get('h_pct', 9.5)) / 100.0,
                )
                rem_box = {
                    'x_pct': bx * 100.0, 'w_pct': bw * 100.0,
                    'y_pct': by * 100.0, 'h_pct': bh * 100.0,
                    'visual_start': (float(box['visual_start']) / speed) if box.get('visual_start') is not None else None,
                    'visual_end': (float(box['visual_end']) / speed) if box.get('visual_end') is not None else None,
                }
            else:
                rem_box = box
            result.append({'start': s, 'end': e, 'text': txt, 'box': rem_box})
            continue
        if isinstance(item, (list, tuple)) and len(item) >= 3:
            s, e, txt = float(item[0]) / speed, float(item[1]) / speed, item[2]
            bx = float(item[3]) if len(item) > 3 and item[3] is not None else None
            bw = float(item[4]) if len(item) > 4 and item[4] is not None else None
            if len(item) >= 9:
                by = float(item[5]) if item[5] is not None else 0.815
                bh = float(item[6]) if item[6] is not None else 0.095
                vs = float(item[7]) / speed if item[7] is not None else None
                ve = float(item[8]) / speed if item[8] is not None else None
            else:
                by, bh = 0.815, 0.095
                vs = float(item[5]) / speed if len(item) > 5 and item[5] is not None else None
                ve = float(item[6]) / speed if len(item) > 6 and item[6] is not None else None
            if bx is not None and bw is not None:
                ox, ow, oy, oh = map_box(bx, bw, by, bh)
                result.append((s, e, txt, ox, ow, oy, oh, vs, ve))
            else:
                result.append((s, e, txt))
    return result


def generate_styled_ass(srt_source_path: str, ass_dest_path: str, cur_out_w: int, cur_out_h: int, subtitle_style: dict, geometry=None, speed=1.0) -> str:
    """Chuyển đổi file SRT sang ASS với hệ quy chiếu PlayResX/PlayResY chuẩn xác 1:1 với kích thước video xuất.
    Tính toán font size, viền (outline), lề (MarginL, MarginR, MarginV) và WrapStyle chuẩn chống dồn chữ/vỡ dòng.
    """
    from auto_edit_pipeline import parse_srt_entries

    if geometry is None:
        geometry = OutputGeometry(cur_out_w, cur_out_h, 0.0, 0.0, float(cur_out_w), float(cur_out_h))
    entries = parse_srt_entries(srt_source_path)
    font_name = re.sub(r'[^\w .-]', '', str(subtitle_style.get('font', 'Montserrat')))[:80] or 'Montserrat'

    base_font_size = max(8, min(120, int(subtitle_style.get('size', 24))))
    font_size = max(12, int(round(base_font_size * (geometry.content_h / 720.0))))

    def hex_to_ass(hex_val, default='&H00FFFFFF'):
        if not hex_val:
            return default
        h = str(hex_val).lstrip('#')
        if len(h) == 6:
            return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()
        return default

    primary_col = hex_to_ass(subtitle_style.get('color'), '&H00FFFFFF')
    outline_col = hex_to_ass(subtitle_style.get('outline_color'), '&H00000000')

    raw_outline = subtitle_style.get('outline')
    if raw_outline is not None and int(raw_outline) == 0:
        outline_w = 0
    else:
        outline_val = int(raw_outline) if raw_outline is not None else 1
        outline_w = max(0, min(15, int(round(outline_val * (geometry.content_h / 720.0)))))

    bold_flag = -1 if parse_bool(subtitle_style.get('bold'), False) else 0
    italic_flag = -1 if parse_bool(subtitle_style.get('italic'), False) else 0
    is_uppercase = parse_bool(subtitle_style.get('uppercase'), False)

    sub_region = subtitle_style.get('region') or {}
    sub_align = str(subtitle_style.get('align') or 'center').lower()
    sub_x = float(sub_region.get('x', 10.0))
    sub_y = float(sub_region.get('y', 81.5))
    sub_w = float(sub_region.get('w', 80.0))
    sub_h = float(sub_region.get('h', 9.5))

    box_x = geometry.content_x + geometry.content_w * sub_x / 100.0
    box_y = geometry.content_y + geometry.content_h * sub_y / 100.0
    box_w = max(10.0, geometry.content_w * sub_w / 100.0)
    box_h = max(10.0, geometry.content_h * sub_h / 100.0)
    center_x = box_x + box_w / 2.0
    center_y = box_y + box_h / 2.0
    if sub_align == 'left':
        ass_align, an_tag, pos_x = 4, r'\an4', round(box_x)
    elif sub_align == 'right':
        ass_align, an_tag, pos_x = 6, r'\an6', round(box_x + box_w)
    else:
        ass_align, an_tag, pos_x = 5, r'\an5', round(center_x)
    pos_y = round(center_y)
    margin_v = max(5, int(round(cur_out_h - (box_y + box_h))))
    margin_l = max(5, int(round(box_x)))
    margin_r = max(5, int(round(cur_out_w - (box_x + box_w))))

    header = (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {cur_out_w}\n"
        f"PlayResY: {cur_out_h}\n"
        "ScaledBorderAndShadow: yes\n"
        "WrapStyle: 0\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Default,{font_name},{font_size},{primary_col},&H000000FF,{outline_col},&H80000000,"
        f"{bold_flag},{italic_flag},0,0,100,100,0,0,1,{outline_w},0,"
        f"{ass_align},{margin_l},{margin_r},{margin_v},1\n"
        "\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )

    spd = max(0.01, float(speed))
    events = []
    override_tag = f"{{{an_tag}\\pos({pos_x},{pos_y})}}"
    for s, e, txt in entries:
        t_start = format_ass_time(s / spd)
        t_end = format_ass_time(e / spd)
        txt_display = txt.upper() if is_uppercase else txt
        txt_display = txt_display.replace('\\N', ' ').replace('\n', '\\N')
        events.append(f"Dialogue: 0,{t_start},{t_end},Default,,0,0,0,,{override_tag}{txt_display}\n")

    with open(ass_dest_path, 'w', encoding='utf-8') as f:
        f.write(header + "".join(events))

    return ass_dest_path



def validate_export_payload(data: dict):
    """Xác thực toàn bộ tham số xuất video trước khi khởi chạy job."""
    if not isinstance(data, dict):
        return jsonify({'success': False, 'error': 'Payload JSON không hợp lệ'}), 400
    try:
        source_tool = str(data.get('source_tool') or 'editor').strip()
        export_run_id = str(data.get('export_run_id') or f"run_{int(time.time()*1000)}_{os.urandom(4).hex()}").strip()
        mode = str(data.get('mode', 'none'))
        input_video = str(data.get('inputVideo') or '').strip(' "\'')
        output_dir = str(data.get('outputDir') or os.path.join(ROOT_DIR, 'output')).strip()
        save_to_source_dir = parse_bool(data.get('save_to_source_dir') or data.get('saveToSourceDir'), False)
        if (save_to_source_dir or output_dir in ('__source__', '__same_as_video__', '__source_dir__')) and input_video:
            resolved_in = os.path.abspath(input_video)
            if os.path.exists(resolved_in):
                output_dir = os.path.dirname(resolved_in)
                register_user_path(output_dir)
        output_name = secure_filename(str(data.get('outputName') or 'video_tom_tat.mp4'))
        manual_audio = str(data.get('manualAudio') or '').strip()
        manual_srt = str(data.get('manualSrt') or '').strip()
        dubbing = data.get('dubbing') or {}
        subtitles = data.get('subtitles') or []
        subtitles_enabled = parse_bool(data.get('subtitles_enabled'), True)
        subtitle_style = data.get('subtitle_style') or {}
        blur_original_subtitles = parse_bool(data.get('blur_original_subtitles'), False)
        if not subtitles_enabled and not parse_bool(data.get('force_blur_without_sub'), False):
            blur_original_subtitles = False
        blur_intensity = max(5, min(30, int(data.get('blur_intensity', 15))))
        original_srt_path = str(data.get('original_srt_path') or '').strip()
        ocr_region = data.get('ocr_region') or {}
        blur_lead_offset = max(-2.0, min(2.0, float(data.get('blur_lead_offset', -180)) / 1000.0))
        blur_padding = max(0.0, min(2.0, float(data.get('blur_padding', 220)) / 1000.0))
        blur_use_ai_scan = parse_bool(data.get('blur_use_ai_scan'), False)
        use_cache = parse_bool(data.get('use_cache'), False)

        video_speed = float(data.get('video_speed', 1.0))
        video_zoom = float(data.get('video_zoom', 1.0))
        if video_zoom > 5.0:
            video_zoom = video_zoom / 100.0
        video_pan_x = float(data.get('video_pan_x', 0.0))
        video_pan_y = float(data.get('video_pan_y', 0.0))
        rotation = int(data.get('rotation', 0)) % 360
        fit_mode = str(data.get('fit_mode', 'contain')).lower()
        aspect_ratio = str(data.get('aspect_ratio', 'original'))
        mirror_flip = parse_bool(data.get('mirror_flip'), False)
        trim_enabled = parse_bool(data.get('trim_enabled'), False)
        trim_start = str(data.get('trim_start', '')).strip()
        trim_end = str(data.get('trim_end', '')).strip()
        encoder = str(data.get('encoder') or 'libx264')
        resolution = str(data.get('resolution') or 'original')
        bitrate = int(data.get('bitrate', 10000))
        bitrate_mode = str(data.get('bitrate_mode', 'VBR')).upper()
        threads_raw = str(data.get('threads', 'auto')).strip().lower()
        preset = str(data.get('preset', 'faster')).strip().lower()
        export_profile = str(data.get('export_profile', '')).strip().lower()
    except (TypeError, ValueError) as exc:
        return jsonify({'success': False, 'error': f'Tham số xuất video không hợp lệ: {exc}'}), 400

    if mode not in {'none', 'tts', 'manual', 'api'} or not isinstance(dubbing, dict) or not isinstance(subtitles, list):
        return jsonify({'success': False, 'error': 'Cấu hình mode/dubbing/subtitles không hợp lệ'}), 400
    if len(subtitles) > 50000:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề quá lớn'}), 413
    if not 0.25 <= video_speed <= 4.0 or not 0.2 <= video_zoom <= 5.0 or not -1200 <= video_pan_x <= 1200 or not -1200 <= video_pan_y <= 1200:
        return jsonify({'success': False, 'error': 'Thông số tốc độ/zoom/pan nằm ngoài giới hạn'}), 400
    if aspect_ratio not in {'original', '9:16', '16:9', '1:1', '4:3', '21:9'} or resolution not in {'original', '720p', '1080p', '4k'}:
        return jsonify({'success': False, 'error': 'Tỉ lệ hoặc độ phân giải không hợp lệ'}), 400
    if fit_mode not in {'contain', 'cover', 'fill'}:
        return jsonify({'success': False, 'error': 'Chế độ fit_mode không hợp lệ'}), 400
    if encoder not in {'auto', 'libx264', 'h264_nvenc', 'hevc_nvenc', 'av1_nvenc', 'h264_mf', 'h264_amf', 'h264_qsv'} or bitrate_mode not in {'VBR', 'CBR'} or not 500 <= bitrate <= 100000:
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
        dubbing['threads'] = max(1, min(32, int(dubbing.get('threads', 16))))
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

    return None


def execute_export_pipeline(job: ExportJob, data: dict):
    """
    Hàm thực thi pipeline xuất video độc lập được điều phối bởi ExportJobManager.
    Chạy trong worker thread riêng biệt, không phụ thuộc vào kết nối HTTP SSE.
    """
    global current_export_process, _export_active, STOP_EXPORT_FLAG
    _export_active = True
    STOP_EXPORT_FLAG = False
    blurred_temp_video = None
    process = None
    export_succeeded = False
    filter_script_path = None
    dyn_blur_mask_path = None
    temp_srt_path = None

    export_start_time = time.time()
    source_tool = str(data.get('source_tool') or 'editor').strip()
    export_run_id = str(data.get('export_run_id') or job.export_run_id).strip()
    mode = str(data.get('mode', 'none'))
    input_video = str(data.get('inputVideo') or '').strip(' "\'')
    output_dir = str(data.get('outputDir') or os.path.join(ROOT_DIR, 'output')).strip()
    save_to_source_dir = parse_bool(data.get('save_to_source_dir') or data.get('saveToSourceDir'), False)
    if (save_to_source_dir or output_dir in ('__source__', '__same_as_video__', '__source_dir__')) and input_video:
        resolved_in = os.path.abspath(input_video)
        if os.path.exists(resolved_in):
            output_dir = os.path.dirname(resolved_in)
            register_user_path(output_dir)
    output_name = secure_filename(str(data.get('outputName') or 'video_tom_tat.mp4'))
    manual_audio = str(data.get('manualAudio') or '').strip()
    manual_srt = str(data.get('manualSrt') or '').strip()
    dubbing = data.get('dubbing') or {}
    subtitles = data.get('subtitles') or data.get('subtitles_for_dubbing') or []
    subtitles_enabled = parse_bool(data.get('subtitles_enabled'), True)
    subtitle_style = data.get('subtitle_style') or {}
    blur_original_subtitles = parse_bool(data.get('blur_original_subtitles'), False)
    if not subtitles_enabled and not parse_bool(data.get('force_blur_without_sub'), False):
        blur_original_subtitles = False
    blur_intensity = max(5, min(30, int(data.get('blur_intensity', 15))))
    original_srt_path = str(data.get('original_srt_path') or '').strip()
    ocr_region = data.get('ocr_region') or {}
    blur_lead_offset = max(-2.0, min(2.0, float(data.get('blur_lead_offset', -180)) / 1000.0))
    blur_padding = max(0.0, min(2.0, float(data.get('blur_padding', 220)) / 1000.0))
    blur_use_ai_scan = parse_bool(data.get('blur_use_ai_scan'), False)
    fresh_run = parse_bool(data.get('fresh_run'), False)
    use_cache = False if fresh_run else parse_bool(data.get('use_cache'), False)
    target_lang = str(data.get('target_lang') or data.get('targetLang') or 'vi').strip()

    video_speed = float(data.get('video_speed', 1.0))
    video_zoom = float(data.get('video_zoom', 1.0))
    if video_zoom > 5.0:
        video_zoom = video_zoom / 100.0
    video_pan_x = float(data.get('video_pan_x', 0.0))
    video_pan_y = float(data.get('video_pan_y', 0.0))
    rotation = int(data.get('rotation', 0)) % 360
    fit_mode = str(data.get('fit_mode', 'contain')).lower()
    aspect_ratio = str(data.get('aspect_ratio', 'original'))
    mirror_flip = parse_bool(data.get('mirror_flip'), False)
    trim_enabled = parse_bool(data.get('trim_enabled'), False)
    trim_start = str(data.get('trim_start', '')).strip()
    trim_end = str(data.get('trim_end', '')).strip()
    encoder = str(data.get('encoder') or 'libx264')
    resolution = str(data.get('resolution') or 'original')
    bitrate = int(data.get('bitrate', 10000))
    bitrate_mode = str(data.get('bitrate_mode', 'VBR')).upper()
    threads_raw = str(data.get('threads', 'auto')).strip().lower()
    preset = str(data.get('preset', 'faster')).strip().lower()
    export_profile = str(data.get('export_profile', '')).strip().lower()

    if export_profile not in {'fast_gpu', 'balanced', 'master'}:
        if preset in {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'p1', 'p2'}:
            export_profile = 'fast_gpu'
        elif preset in {'slow', 'slower', 'veryslow', 'p6', 'p7'}:
            export_profile = 'master'
        else:
            export_profile = 'balanced'

    valid_presets = {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow', 'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7'}
    if preset not in valid_presets:
        preset = 'p2' if export_profile == 'fast_gpu' else ('p4' if export_profile == 'balanced' else 'p6')

    if threads_raw == 'auto' or not threads_raw.isdigit():
        ffmpeg_thread_arg = '0'
        thread_display_label = f"Tối đa CPU ({os.cpu_count() or 'đa'} luồng)"
    else:
        t_num = max(1, min(64, int(threads_raw)))
        ffmpeg_thread_arg = str(t_num)
        thread_display_label = f"{t_num} luồng"

    editor_temp_dir = get_editor_temp_dir(output_dir, input_video)
    os.makedirs(editor_temp_dir, exist_ok=True)

    if fresh_run:
        # Dọn sạch toàn bộ artifact cũ để fresh run chạy lại từ đầu 100%
        for old_fn in ['dubbed_timeline.wav', 'stem_cleaned.wav', 'ai_blur_boxes.json', 'tts_manifest.json', 'editor_subtitles.srt', 'rendered_subtitles.ass']:
            old_f = os.path.join(editor_temp_dir, old_fn)
            if os.path.exists(old_f):
                try:
                    os.remove(old_f)
                except Exception:
                    pass
        d_temp = os.path.join(editor_temp_dir, 'dubbing_temp')
        if os.path.exists(d_temp):
            try:
                shutil.rmtree(d_temp, ignore_errors=True)
            except Exception:
                pass

    def emit(msg):
        if not msg:
            return
        clean = str(msg).strip()
        if clean.startswith("data:"):
            clean = clean[5:].strip()
        if clean.startswith("[EVENT:SUCCESS]"):
            try:
                ev = json.loads(clean.replace("[EVENT:SUCCESS]", "").strip())
                job.set_success(ev.get('path'), ev.get('size_mb'), ev.get('history_id'))
            except Exception:
                job.set_success(final_output_path, file_size_mb, history_id)
            return
        if clean.startswith("[EVENT:FAILED]"):
            try:
                ev = json.loads(clean.replace("[EVENT:FAILED]", "").strip())
                job.set_failed(ev.get('reason', 'Xuất video thất bại'), ev)
            except Exception:
                job.set_failed(clean)
            return
        if clean.startswith("[EVENT:CANCELLED]"):
            job.set_cancelled(clean)
            return
        if "🛑" in clean or "[LỖI" in clean or "ERROR:" in clean:
            job.emit_log(clean, 'error')
        elif "⚠️" in clean:
            job.emit_log(clean, 'warning')
        elif "⏳ [Tiến độ:" in clean:
            m_pct = re.search(r'Tiến độ:\s*(\d+)%', clean)
            pct = float(m_pct.group(1)) if m_pct else job.stage_progress
            m_speed = re.search(r'\|\s*([0-9.]+)x', clean)
            speed = float(m_speed.group(1)) if m_speed else None
            m_eta = re.search(r'Còn lại:\s*([0-9:]+)', clean)
            eta = m_eta.group(1) if m_eta else None
            job.emit_progress(job.stage, pct, clean, speed=speed, eta=eta)
        else:
            job.emit_log(clean, 'info')

    blurred_temp_video = None
    process = None
    export_succeeded = False
    filter_script_path = None
    dyn_blur_mask_path = None
    temp_srt_path = None
    part_output_path = None
    try:
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
        
        if not input_video or not os.path.exists(input_video):
            emit(f"🛑 ERROR: Không tìm thấy video đầu vào: {input_video}")
            return

        if not use_cache and os.path.exists(editor_temp_dir):
            for item in os.listdir(editor_temp_dir):
                try:
                    ip = os.path.join(editor_temp_dir, item)
                    if os.path.isfile(ip) or os.path.islink(ip):
                        os.unlink(ip)
                    elif os.path.isdir(ip):
                        shutil.rmtree(ip, ignore_errors=True)
                except Exception:
                    pass
        os.makedirs(editor_temp_dir, exist_ok=True)

        # Helper to probe video duration, dimensions and audio track
        def probe_video_info(v_path):
            d_sec = 0.0
            has_aud = True
            vw = 1920
            vh = 1080
            try:
                ffprobe_path = ffmpeg_path.replace('ffmpeg.exe', 'ffprobe.exe') if 'ffmpeg.exe' in ffmpeg_path else 'ffprobe'
                if os.path.exists(ffprobe_path) or ffprobe_path == 'ffprobe':
                    cmd_probe = [
                        ffprobe_path, '-v', 'error', '-show_entries', 'format=duration:stream=codec_type,width,height',
                        '-of', 'json', v_path
                    ]
                    res_p = subprocess.run(cmd_probe, capture_output=True, text=True, timeout=30, **ffmpeg_installer.get_stealth_subprocess_kwargs())
                    if res_p.returncode == 0:
                        info_p = json.loads(res_p.stdout)
                        d_sec = float(info_p.get('format', {}).get('duration', 0.0))
                        streams = info_p.get('streams', [])
                        has_aud = any(s.get('codec_type') == 'audio' for s in streams)
                        for s in streams:
                            if s.get('codec_type') == 'video':
                                w_val = int(s.get('width', 0) or 0)
                                h_val = int(s.get('height', 0) or 0)
                                if w_val > 0 and h_val > 0:
                                    vw, vh = w_val, h_val
                                    break
                        if d_sec > 0:
                            return d_sec, has_aud, vw, vh
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
                m_dim = re.search(r'Stream.*Video:.*?(\d{2,5})x(\d{2,5})', proc.stderr)
                if m_dim:
                    vw, vh = int(m_dim.group(1)), int(m_dim.group(2))
                if d_sec > 0:
                    return d_sec, has_aud, vw, vh
            except Exception:
                pass

            # Fallback to cv2
            try:
                import cv2
                cap = cv2.VideoCapture(v_path)
                if cap.isOpened():
                    fps = cap.get(cv2.CAP_PROP_FPS)
                    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                    cw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
                    ch = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
                    if cw > 0 and ch > 0:
                        vw, vh = cw, ch
                    cap.release()
                    if fps > 0 and frames > 0:
                        d_sec = float(frames / fps)
            except Exception:
                pass

            return d_sec, has_aud, vw, vh

        video_duration, has_orig_audio, src_vw, src_vh = probe_video_info(input_video)

        # --- Generate temp SRT from subtitles array for Burn-In (ƯU TIÊN CHỮ DỊCH TIẾNG VIỆT) ---
        temp_srt_path = None
        filter_script_path = None
        if subtitles_enabled and subtitles and isinstance(subtitles, list) and len(subtitles) > 0:
            import subtitle_postprocessor
            is_val, v_errs, inv_ids = subtitle_postprocessor.validate_subtitles_for_export(subtitles, target_lang=target_lang)
            if not is_val:
                emit(f"🛑 [LỖI PHỤ ĐỀ] Không thể burn-in phụ đề: Phát hiện câu chưa dịch hoặc không đạt chuẩn (ID: {', '.join(inv_ids)}). Dừng xuất video.")
                job.set_failed(f"Phụ đề câu {', '.join(inv_ids)} chưa được dịch hợp lệ", {"invalid_ids": inv_ids})
                return

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
                        raw_st = sub.get('startSeconds') if sub.get('startSeconds') is not None else sub.get('start_sec', sub.get('start', 0))
                        raw_et = sub.get('endSeconds') if sub.get('endSeconds') is not None else sub.get('end_sec', sub.get('end', 0))
                        t_start = format_srt_time(float(subtitle_postprocessor.time_to_seconds(raw_st)))
                        t_end = format_srt_time(float(subtitle_postprocessor.time_to_seconds(raw_et)))
                        translated_txt = str(sub.get('translation') or '').strip()
                        orig_txt = str(sub.get('text') or sub.get('original_text') or '').strip()
                        display_text = translated_txt if translated_txt else orig_txt
                        if parse_bool(subtitle_style.get('uppercase'), False):
                            display_text = display_text.upper()
                        f.write(f"{i}\n{t_start} --> {t_end}\n{display_text}\n\n")
                try:
                    shutil.copyfile(temp_srt_path, os.path.join(editor_temp_dir, 'editor_subtitles.srt'))
                except Exception:
                    pass
            except Exception as e:
                emit(f"⚠️ Lỗi tạo file phụ đề tạm: {str(e)}")
                temp_srt_path = None

        # ═══════════════════════════════════════════════════════
        # 1. DYNAMIC BLUR: Chuẩn bị bộ lọc làm mờ (ƯU TIÊN CHỮ GỐC)
        # ═══════════════════════════════════════════════════════
        custom_layers = data.get('custom_overlay_layers') or []
        # Kiểm tra xem người dùng đã tạo custom blur che khu vực phụ đề hay chưa để tránh Double Blur
        has_custom_sub_blur = False
        if isinstance(custom_layers, list):
            for _layer in custom_layers:
                if _layer.get('type') == 'blur' and _layer.get('visible') is not False:
                    # Nếu vùng làm mờ nằm ở nửa dưới video (y >= 60%) và chiều rộng đủ lớn (> 40%)
                    _ly = float(_layer.get('y_pct', 0))
                    _lw = float(_layer.get('w_pct', 0))
                    if _ly >= 60.0 and _lw >= 35.0:
                        has_custom_sub_blur = True
                        break

        orig_blur_entries = []
        dyn_blur_pending = False
        dyn_blur_mask_path = None
        if blur_original_subtitles and input_video and os.path.exists(input_video):
            if has_custom_sub_blur:
                emit("ℹ️ [Dynamic Blur] Phát hiện bạn đã có vùng làm mờ thủ công (Custom Blur) ở khu vực phụ đề. Tự động tắt Dynamic Blur tự động để tránh bị làm mờ 2 lần (Double Blur)!")
            else:
                # 1.1 Tạo danh sách câu phụ đề làm mờ ưu tiên CHỮ GỐC của phim
                has_live_preview_boxes = False
                
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
                            if blur_use_ai_scan and ai_box and isinstance(ai_box, dict) and 'x_pct' in ai_box and 'w_pct' in ai_box:
                                has_live_preview_boxes = True
                                box_x_r = float(ai_box['x_pct']) / 100.0
                                box_w_r = float(ai_box['w_pct']) / 100.0
                                box_y_r = float(ai_box.get('y_pct', ocr_region.get('y', 81.5))) / 100.0
                                box_h_r = float(ai_box.get('h_pct', ocr_region.get('h', 9.5))) / 100.0
                                vis_s = ai_box.get('visual_start') or sub.get('visual_start')
                                vis_e = ai_box.get('visual_end') or sub.get('visual_end')
                                if vis_s is not None and vis_e is not None:
                                    orig_blur_entries.append((s_start, s_end, orig_txt, box_x_r, box_w_r, box_y_r, box_h_r, float(vis_s), float(vis_e)))
                                else:
                                    orig_blur_entries.append((s_start, s_end, orig_txt, box_x_r, box_w_r, box_y_r, box_h_r, s_start, s_end))
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

                cached_ai_boxes_path = os.path.join(editor_temp_dir, 'ai_blur_boxes.json')
                loaded_blur_cache = False
                # Box đang hiển thị trong preview là nguồn dữ liệu mới nhất; cache chỉ
                # được dùng khi request không mang theo box nào.
                if blur_use_ai_scan and use_cache and not has_live_preview_boxes and os.path.exists(cached_ai_boxes_path) and os.path.getsize(cached_ai_boxes_path) > 10:
                    try:
                        with open(cached_ai_boxes_path, 'r', encoding='utf-8') as f:
                            raw_boxes = json.load(f)
                        if isinstance(raw_boxes, list) and len(raw_boxes) > 0:
                            parsed_entries = []
                            for item in raw_boxes:
                                if isinstance(item, (list, tuple)):
                                    parsed_entries.append(tuple(item))
                                elif isinstance(item, dict):
                                    s_s = float(item.get('start', item.get('startSeconds', 0)))
                                    s_e = float(item.get('end', item.get('endSeconds', 0)))
                                    t_str = str(item.get('text', ''))
                                    b = item.get('box') or item
                                    if b and isinstance(b, dict) and 'x_pct' in b and 'w_pct' in b:
                                        b_x = float(b['x_pct']) / 100.0
                                        b_w = float(b['w_pct']) / 100.0
                                        b_y = float(b.get('y_pct', ocr_region.get('y', 81.5))) / 100.0
                                        b_h = float(b.get('h_pct', ocr_region.get('h', 9.5))) / 100.0
                                        v_s = b.get('visual_start')
                                        v_e = b.get('visual_end')
                                        if v_s is not None and v_e is not None:
                                            parsed_entries.append((s_s, s_e, t_str, b_x, b_w, b_y, b_h, float(v_s), float(v_e)))
                                        else:
                                            parsed_entries.append((s_s, s_e, t_str, b_x, b_w, b_y, b_h, s_s, s_e))
                                    else:
                                        parsed_entries.append((s_s, s_e, t_str))
                            if parsed_entries:
                                orig_blur_entries = parsed_entries
                                loaded_blur_cache = True
                                emit(f"💚 [Dynamic Blur] Đã tìm thấy tọa độ quét AI Pixel từ lần chạy trước ({len(orig_blur_entries)} câu), tái sử dụng ngay không cần quét lại!")
                    except Exception:
                        loaded_blur_cache = False

                if not loaded_blur_cache and orig_blur_entries:
                    already_scanned = len(orig_blur_entries) > 0 and all(len(item) >= 5 for item in orig_blur_entries)
                    if already_scanned:
                        emit(f"🎯 [Dynamic Blur] Đã nạp thành công tọa độ AI Pixel từ Preview cho {len(orig_blur_entries)} câu phụ đề!")
                        try:
                            with open(cached_ai_boxes_path, 'w', encoding='utf-8') as f:
                                json.dump(orig_blur_entries, f, ensure_ascii=False)
                        except Exception:
                            pass
                    elif blur_use_ai_scan:
                        emit(f"🚀 [Dynamic Blur] Kích hoạt AI quét tọa độ (AI Scan)...")
                        try:
                            from ocr_module import scan_subtitles_pixel_boxes_generator
                            for status, data_payload in scan_subtitles_pixel_boxes_generator(input_video, ocr_region, orig_blur_entries):
                                if status == "progress":
                                    emit(f"✨ {data_payload}")
                                elif status == "done":
                                    orig_blur_entries = data_payload
                                try:
                                    with open(cached_ai_boxes_path, 'w', encoding='utf-8') as f:
                                        json.dump(orig_blur_entries, f, ensure_ascii=False)
                                except Exception:
                                    pass
                        except Exception as e:
                            emit(f"⚠️ [AI Scan Lỗi] {str(e)}. Fallback về tính toán độ rộng mặc định...")
                    else:
                        emit(f"✨ [Dynamic Blur] Phát hiện {len(orig_blur_entries)} đoạn phụ đề. Đang tính toán độ rộng làm mờ tự động theo CHỮ GỐC của video...")

                # Dựng filter sau scale/pad để dùng chung hệ tọa độ với Preview.
                if orig_blur_entries:
                    dyn_blur_pending = True
                else:
                    emit("⚠️ [Dynamic Blur] Không tìm thấy phụ đề gốc để xác định thời gian và vị trí làm mờ. Bỏ qua blur.")
            
        # ═══════════════════════════════════════════════════════
        # 2. AI DUBBING: Tạo track lồng tiếng AI từ phụ đề
        # ═══════════════════════════════════════════════════════
        dub_track = None
        is_dubbing_enabled = dubbing.get('enabled', False)
        dubbing_mode = dubbing.get('mode', 'tts')
        
        # Ưu tiên lấy phụ đề từ data.get('subtitles_for_dubbing'), sau đó đến subtitles gửi lên; nếu trống hoặc dính chữ Hán, tự động phục hồi từ editor_subtitles.srt đã dịch
        subs_for_dubbing = data.get('subtitles_for_dubbing') or subtitles or []
        editor_sub_file = os.path.join(editor_temp_dir, 'editor_subtitles.srt')
        
        # Kiểm tra xem danh sách hiện tại có bị trống hoặc toàn chữ Hán chưa dịch không
        needs_translation_recovery = (not subs_for_dubbing) or (
            len(subs_for_dubbing) > 0 and all(
                any(0x4E00 <= ord(c) <= 0x9FFF for c in str(s.get('translation', '') or s.get('text', '')))
                for s in subs_for_dubbing[:min(20, len(subs_for_dubbing))]
            )
        )

        if is_dubbing_enabled and dubbing_mode == 'tts' and needs_translation_recovery:
            # 1. Thử đọc từ editor_subtitles.srt vừa tạo trong editor_temp_dir
            if os.path.exists(editor_sub_file) and os.path.getsize(editor_sub_file) > 100:
                try:
                    from auto_edit_pipeline import parse_srt_entries
                    saved_entries = parse_srt_entries(editor_sub_file)
                    if saved_entries and not any(0x4E00 <= ord(c) <= 0x9FFF for c in saved_entries[0][2]):
                        subs_for_dubbing = [{"text": txt, "translation": txt, "startSeconds": s, "endSeconds": e} for s, e, txt in saved_entries]
                except Exception:
                    pass

            # 2. Thử đọc từ temp_srt_path
            if (not subs_for_dubbing or any(0x4E00 <= ord(c) <= 0x9FFF for c in str(subs_for_dubbing[0].get('text', '')))) and temp_srt_path and os.path.exists(temp_srt_path):
                try:
                    from auto_edit_pipeline import parse_srt_entries
                    saved_entries = parse_srt_entries(temp_srt_path)
                    if saved_entries and not any(0x4E00 <= ord(c) <= 0x9FFF for c in saved_entries[0][2]):
                        subs_for_dubbing = [{"text": txt, "translation": txt, "startSeconds": s, "endSeconds": e} for s, e, txt in saved_entries]
                except Exception:
                    pass

            # 3. Fallback sang manual_srt hoặc original_srt_path nếu vẫn chưa có
            if not subs_for_dubbing:
                srt_candidate = manual_srt or original_srt_path
                if srt_candidate and os.path.exists(srt_candidate):
                    try:
                        from auto_edit_pipeline import parse_srt_entries
                        raw_entries = parse_srt_entries(srt_candidate)
                        subs_for_dubbing = [{"text": txt, "startSeconds": s, "endSeconds": e} for s, e, txt in raw_entries]
                    except Exception:
                        pass

        if is_dubbing_enabled:
            cached_dub_file = os.path.join(editor_temp_dir, 'dubbed_timeline.wav')
            if dubbing_mode == 'tts':
                voice_id = dubbing.get('voice_id') or 'local_minh_duc'
                speed_dub = float(dubbing.get('speed', 1.1))
                tts_fingerprint = compute_tts_fingerprint(subs_for_dubbing, voice_id, speed_dub, video_duration)
                is_manifest_match = False if (fresh_run or not use_cache) else is_tts_manifest_valid(editor_temp_dir, tts_fingerprint)

                if not subs_for_dubbing:
                    emit("🛑 [LỖI LỒNG TIẾNG] Danh sách phụ đề trống! Vui lòng nạp hoặc dịch phụ đề trước khi xuất video có lồng tiếng.")
                    job.set_failed("Danh sách phụ đề trống, không thể tạo lồng tiếng AI", {})
                    return
                elif not fresh_run and use_cache and is_manifest_match:
                    dub_track = cached_dub_file
                    emit(f"💚 [AI Dubbing] Đã tìm thấy track lồng tiếng AI hoàn chỉnh từ lần chạy trước ({os.path.basename(dub_track)}) khớp kịch bản, tái sử dụng ngay lập tức (0s)!")
                    job.set_stage(JobStage.TTS_GENERATING, 100, "Đã tái sử dụng track lồng tiếng AI")
                else:
                    voice_id = dubbing.get('voice_id') or 'local_minh_duc'
                    speed_dub = float(dubbing.get('speed', 1.1))
                    emit(f"🎙️ Đang tiến hành tạo giọng lồng tiếng AI cho {len(subs_for_dubbing)} câu phụ đề (Giọng: {voice_id})...")
                    import ai_dubbing
                    
                    open_speaker_key = ''
                    api_keys_file = API_KEYS_FILE
                    if os.path.exists(api_keys_file):
                        with open(api_keys_file, 'r', encoding='utf-8') as f:
                            for line in f:
                                if line.startswith('openSpeakerApiKey='):
                                    open_speaker_key = line.split('=', 1)[1].strip()
                                    
                    dub_threads = int(dubbing.get('threads') or 0)
                    if dub_threads <= 0:
                        dub_threads = 32 if str(voice_id).startswith('edge_') else 4
                    elif str(voice_id).startswith('edge_') and dub_threads < 32:
                        # Tự động nâng luồng Edge-TTS lên 32 luồng tối đa nếu người dùng chọn giọng Edge
                        dub_threads = 32
                    temp_dub_dir = os.path.join(editor_temp_dir, 'dubbing_temp')
                    os.makedirs(temp_dub_dir, exist_ok=True)
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
                                emit("🛑 Đã dừng tiến trình lồng tiếng theo yêu cầu khẩn cấp.")
                                return
                            if event_type == 'progress':
                                emit(f"{msg}")
                            elif event_type == 'done':
                                dub_track = msg
                                
                        if STOP_EXPORT_FLAG:
                            emit("🛑 Đã dừng tiến trình xuất video.")
                            return
                        if dub_track and os.path.exists(dub_track):
                            emit("✅ Đã tạo và đồng bộ xong track âm thanh lồng tiếng AI!")
                            if dub_track != cached_dub_file:
                                try:
                                    shutil.copyfile(dub_track, cached_dub_file)
                                except Exception:
                                    pass
                            save_tts_manifest(editor_temp_dir, tts_fingerprint, voice_id, speed_dub, video_duration, len(subs_for_dubbing))
                            job.set_stage(JobStage.TTS_GENERATING, 100, "Đã tạo xong track lồng tiếng AI")
                            time.sleep(0.2)
                            gc.collect()
                        else:
                            emit("🛑 [LỖI LỒNG TIẾNG] Không tạo được track âm thanh lồng tiếng AI! Vui lòng kiểm tra lại giọng đọc hoặc API key.")
                            job.set_failed("Không tạo được track âm thanh lồng tiếng AI", {"voice_id": voice_id})
                            return
                    except Exception as e:
                        emit(f"🛑 [LỖI LỒNG TIẾNG] Lỗi ngoại lệ: {str(e)}")
                        job.set_failed(f"Lỗi tạo giọng đọc lồng tiếng AI: {str(e)}", {"voice_id": voice_id})
                        return
            elif dubbing_mode == 'manual' and (dubbing.get('manual_audio') or manual_audio):
                dub_track = dubbing.get('manual_audio') or manual_audio
                if os.path.exists(dub_track):
                    emit(f"🎵 Sử dụng file âm thanh lồng tiếng có sẵn: {os.path.basename(dub_track)}")
                else:
                    emit(f"🛑 [LỖI ÂM THANH] File âm thanh thủ công không tồn tại: {dub_track}")
                    dub_track = None

        # ═══════════════════════════════════════════════════════
        # 3. VIDEO & AUDIO PIPELINE EXPORT (FFMPEG ENGINE)
        # ═══════════════════════════════════════════════════════
        os.makedirs(output_dir, exist_ok=True)
        out_file_name = output_name if output_name.lower().endswith('.mp4') else f"{output_name}.mp4"
        final_output_path = safe_join(output_dir, out_file_name, extensions={'.mp4'})
        if input_video and os.path.abspath(final_output_path) == os.path.abspath(input_video):
            stem, ext = os.path.splitext(out_file_name)
            out_file_name = f"{stem}_edited{ext or '.mp4'}"
            final_output_path = safe_join(output_dir, out_file_name, extensions={'.mp4'})
        part_output_path = final_output_path + f".part_{os.getpid()}_{int(time.time()*1000)}.mp4"
        
        emit(f"⚙️ Đang thiết lập cấu hình xuất video ({encoder} | Đa luồng: {thread_display_label} | Preset: {preset} | Profile: {export_profile.upper()})...")
        job.set_stage(JobStage.BUILDING_FILTERS, 0, "Đang thiết lập cấu hình bộ lọc...")

        # ═══════════════════════════════════════════════════════
        # 3.0 STREAM-COPY / SMART-CUT BYPASS
        # CHỈ kích hoạt khi video không có bất kỳ filter nào cần re-encode.
        # TUYỆT ĐỐI KHÔNG dùng khi: burn-in sub, blur, overlay/logo, zoom/pan, mirror, audio mix.
        # ═══════════════════════════════════════════════════════
        logo_data = data.get('logo') or {}
        logo_enabled = parse_bool(logo_data.get('enabled'), False)
        logo_path = str(logo_data.get('path') or '').strip()
        has_logo = logo_enabled and bool(logo_path) and os.path.exists(logo_path)

        stem_enabled = is_dubbing_enabled and (
            parse_bool(dubbing.get('remove_original_vocals'), False) or (
                isinstance(dubbing.get('stem_separation'), dict)
                and parse_bool(dubbing.get('stem_separation', {}).get('enabled'), False)
            )
        )
        voice_vol = float(dubbing.get('voice_volume', 1.0))
        orig_vol = float(dubbing.get('original_volume', 0.45 if is_dubbing_enabled else 1.0))

        can_stream_copy = (
            not subtitles_enabled
            and not dyn_blur_pending
            and not has_logo
            and not custom_layers
            and abs(video_speed - 1.0) < 0.001
            and abs(video_zoom - 1.0) < 0.001
            and video_pan_x == 0
            and video_pan_y == 0
            and rotation == 0
            and fit_mode == 'contain'
            and not mirror_flip
            and aspect_ratio == 'original'
            and resolution == 'original'
            and mode == 'none'
            and not dub_track
            and not stem_enabled
            and (not is_dubbing_enabled or (abs(orig_vol - 1.0) < 0.001 and abs(voice_vol - 0.0) < 0.001))
        )

        if can_stream_copy:
            emit("⚡ [STREAM-COPY] Video không có hiệu ứng filter hình ảnh hoặc âm thanh cần encode lại.")
            emit("🚀 Kích hoạt chế độ sao chép luồng siêu tốc trực tiếp (Direct Lossless Stream-Copy)...")
            cmd_sc = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'info']
            if trim_enabled and trim_start:
                cmd_sc.extend(['-ss', trim_start])
            if trim_enabled and trim_end:
                cmd_sc.extend(['-to', trim_end])
            cmd_sc.extend([
                '-i', input_video,
                '-c', 'copy',
                '-avoid_negative_ts', 'make_zero',
                part_output_path
            ])
            proc_sc = subprocess.Popen(
                cmd_sc,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=ROOT_DIR,
                encoding='utf-8',
                errors='replace',
                **ffmpeg_installer.get_stealth_subprocess_kwargs()
            )
            job.register_process(proc_sc)
            with _export_lock:
                current_export_process = proc_sc
            for sc_line in iter(proc_sc.stdout.readline, ''):
                if job.is_stopped() or STOP_EXPORT_FLAG:
                    break
                if sc_line and ('size=' in sc_line or 'time=' in sc_line or 'speed=' in sc_line):
                    emit(f"⏳ [Stream-Copy] {sc_line.strip()}")
            proc_sc.stdout.close()
            rc_sc = proc_sc.wait()
            job.unregister_process(proc_sc)
            if rc_sc == 0 and os.path.exists(part_output_path) and os.path.getsize(part_output_path) > 1000:
                if os.path.exists(final_output_path):
                    try:
                        os.replace(part_output_path, final_output_path)
                    except Exception:
                        os.remove(final_output_path)
                        os.rename(part_output_path, final_output_path)
                else:
                    os.rename(part_output_path, final_output_path)
                export_succeeded = True
                sz_mb = os.path.getsize(final_output_path) / (1024 * 1024)
                history_id = None
                try:
                    from export_history import get_export_history_service
                    service = get_export_history_service()
                    history_id = service.record_export(
                        output_path=final_output_path,
                        source_tool=source_tool,
                        source_kind='editor',
                        export_run_id=export_run_id,
                        params={
                            'mode': 'stream_copy',
                            'input_video': input_video
                        }
                    )
                except Exception as he:
                    logging.getLogger(__name__).error(f"[ExportHistory] Error recording stream-copy export: {he}")
                try:
                    from telegram_notifier import get_telegram_notifier
                    notifier = get_telegram_notifier()
                    if notifier.enabled and notifier.notify_per_video:
                        video_title = os.path.basename(input_video) if input_video else output_name
                        notifier.notify_task_success(
                            task_type='editor',
                            task_title='Biên Tập Phim (Sao Chép Luồng)',
                            video_title=video_title,
                            output_path=final_output_path,
                            duration_sec=time.time() - export_start_time,
                            file_size_mb=sz_mb
                        )
                except Exception as te:
                    logging.getLogger(__name__).warning(f"[Telegram] Error sending stream-copy notification: {te}")
                emit(f"✅ [XUẤT THÀNH CÔNG] Video đã được sao chép luồng tại: {final_output_path} ({sz_mb:.1f} MB)")
                emit(f"[EVENT:SUCCESS] {json.dumps({'path': final_output_path, 'size_mb': round(sz_mb, 2), 'history_id': history_id})}")
                emit(f"--- HOÀN THÀNH QUÁ TRÌNH TẠO ---")
                return
            else:
                emit("⚠️ [Stream-Copy] Thất bại, tự động chuyển về quy trình biên mã thông thường...")

        # Construct Video Filter Complex
        v_filters = []
        curr_v = "0:v"

        # 3.0 Video Zoom & Crop
        if video_zoom > 1.01:
            crop_w = f"trunc(iw/{video_zoom:.4f}/2)*2"
            crop_h = f"trunc(ih/{video_zoom:.4f}/2)*2"
            crop_x = f"(iw-{crop_w})/2 - ({video_pan_x:.1f}*(iw/800))"
            crop_y = f"(ih-{crop_h})/2 - ({video_pan_y:.1f}*(ih/450))"
            v_filters.append(f"[{curr_v}]crop=w={crop_w}:h={crop_h}:x='max(0,min(iw-ow,trunc(({crop_x})/2)*2))':y='max(0,min(ih-oh,trunc(({crop_y})/2)*2))',scale={src_vw}:{src_vh}:flags=lanczos[v_cropped]")
            curr_v = "v_cropped"

        # 3.1 Speed
        if abs(video_speed - 1.0) > 0.01:
            v_filters.append(f"[{curr_v}]setpts=PTS/{video_speed:.4f}[v_speed]")
            curr_v = "v_speed"

        # 3.1.5 Rotation
        if rotation == 90:
            v_filters.append(f"[{curr_v}]transpose=1[v_rot]")
            curr_v = "v_rot"
        elif rotation == 180:
            v_filters.append(f"[{curr_v}]hflip,vflip[v_rot]")
            curr_v = "v_rot"
        elif rotation == 270:
            v_filters.append(f"[{curr_v}]transpose=2[v_rot]")
            curr_v = "v_rot"

        # 3.2 Mirror Flip
        if mirror_flip:
            v_filters.append(f"[{curr_v}]hflip[v_flip]")
            curr_v = "v_flip"

        # 3.3 Aspect Ratio & Resolution
        cur_out_w, cur_out_h = src_vw, src_vh
        target_w, target_h = None, None
        if aspect_ratio == '9:16':
            target_w, target_h = 1080, 1920
        elif aspect_ratio == '16:9':
            target_w, target_h = 1920, 1080
        elif aspect_ratio == '1:1':
            target_w, target_h = 1080, 1080
        elif aspect_ratio == '4:3':
            target_w, target_h = 1440, 1080
        elif aspect_ratio == '21:9':
            target_w, target_h = 1920, 822
        elif resolution == '1080p':
            target_w, target_h = 1920, 1080
        elif resolution == '720p':
            target_w, target_h = 1280, 720
        elif resolution == '4k':
            target_w, target_h = 3840, 2160

        if target_w and target_h:
            cur_out_w, cur_out_h = target_w, target_h
            if fit_mode == 'cover':
                v_filters.append(f"[{curr_v}]scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}[v_aspect]")
            elif fit_mode == 'fill':
                v_filters.append(f"[{curr_v}]scale={target_w}:{target_h}[v_aspect]")
            else:
                v_filters.append(f"[{curr_v}]scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black[v_aspect]")
            curr_v = "v_aspect"

        output_geometry = compute_output_geometry(src_vw, src_vh, cur_out_w, cur_out_h)
        if dyn_blur_pending:
            try:
                from auto_edit_pipeline import build_dynamic_blur_filter_chain
                remapped_blur_entries = remap_blur_entries_to_output_frame(
                    orig_blur_entries, output_geometry, cur_out_w, cur_out_h,
                    video_speed=video_speed, mirror=mirror_flip,
                )
                blur_mode = str(data.get('blur_mode', 'fixed')).lower()
                region_x = float(data.get('blur_x', ocr_region.get('x', 20.0))) / 100.0
                region_y = float(data.get('blur_y', ocr_region.get('y', 81.5))) / 100.0
                region_w = float(data.get('blur_w', ocr_region.get('w', 60.0))) / 100.0
                region_h = float(data.get('blur_h', ocr_region.get('h', 9.5))) / 100.0
                if mirror_flip:
                    region_x = 1.0 - region_x - region_w
                mapped_x = (output_geometry.content_x + output_geometry.content_w * region_x) / cur_out_w
                mapped_y = (output_geometry.content_y + output_geometry.content_h * region_y) / cur_out_h
                mapped_w = (output_geometry.content_w * region_w) / cur_out_w
                mapped_h = (output_geometry.content_h * region_h) / cur_out_h

                if blur_mode == 'fixed':
                    # Chế độ làm mờ cố định siêu tốc 10x - 14x:
                    # Chỉ crop đúng dải phụ đề đáy (mapped_x, mapped_y, mapped_w, mapped_h), blur và overlay.
                    # Hoàn toàn tránh maskedmerge và split=3 trên toàn bộ 1080p frame!
                    fw = max(0.05, min(1.0, mapped_w))
                    fh = max(0.02, min(0.40, mapped_h))
                    fx = max(0.0, min(1.0 - fw, mapped_x))
                    fy = max(0.0, min(1.0 - fh, mapped_y))
                    blur_sz = max(5, min(30, blur_intensity))
                    next_v = "v_fixblur"
                    v_filters.append(f"[{curr_v}]split[v_base_fb][v_crop_fb]")
                    v_filters.append(
                        f"[v_crop_fb]crop=w='trunc(iw*{fw:.6f}/2)*2':"
                        f"h='trunc(ih*{fh:.6f}/2)*2':"
                        f"x='trunc(iw*{fx:.6f}/2)*2':"
                        f"y='trunc(ih*{fy:.6f}/2)*2',"
                        f"avgblur=sizeX={blur_sz}:sizeY={blur_sz},eq=brightness=-0.03[v_blur_fb]"
                    )
                    v_filters.append(
                        f"[v_base_fb][v_blur_fb]overlay=x='trunc(main_w*{fx:.6f}/2)*2':y='trunc(main_h*{fy:.6f}/2)*2'[{next_v}]"
                    )
                    curr_v = next_v
                    emit(f"⚡ [Làm Mờ Cố Định] Kích hoạt dải mờ cố định siêu tốc ({fw*100:.1f}% x {fh*100:.1f}%), bứt phá tốc độ xuất 10x – 14x!")
                else:
                    dyn_blur_filters, curr_v = build_dynamic_blur_filter_chain(
                        curr_v, remapped_blur_entries,
                        blur_sz=max(5, min(30, blur_intensity)),
                        y_ratio=mapped_y, h_ratio=mapped_h,
                        center_x_ratio=mapped_x + mapped_w / 2.0,
                        lead_sec=abs(blur_lead_offset) / max(video_speed, 0.01),
                        pad_sec=blur_padding / max(video_speed, 0.01),
                        manual_mode=not blur_use_ai_scan, manual_w=mapped_w,
                        engine='auto' if not blur_use_ai_scan else 'mask', temp_dir=editor_temp_dir,
                        frame_w=cur_out_w, frame_h=cur_out_h, content_h=output_geometry.content_h,
                    )
                    v_filters.extend(dyn_blur_filters)
                    import auto_edit_pipeline
                    dyn_blur_mask_path = getattr(auto_edit_pipeline, '_last_dynamic_blur_mask_file', None)
            except Exception as e:
                emit(f"⚠️ [Dynamic Blur] Lỗi: {str(e)}. Tiếp tục với video gốc...")

        # 3.5 Subtitles (Hardcode / Burn-In)
        if subtitles_enabled:
            srt_target = temp_srt_path or manual_srt or original_srt_path
            if srt_target and os.path.exists(srt_target):
                try:
                    # Sinh file ASS chuẩn xác 1:1 với tọa độ video đầu ra cur_out_w x cur_out_h
                    ass_target = os.path.join(editor_temp_dir, 'rendered_subtitles.ass')
                    generate_styled_ass(srt_target, ass_target, cur_out_w, cur_out_h, subtitle_style, geometry=output_geometry, speed=video_speed)
                    escaped_ass = ass_target.replace('\\', '/').replace(':', '\\:')
                    fonts_dir = os.path.join(ROOT_DIR, 'resources', 'fonts')
                    escaped_fonts = fonts_dir.replace('\\', '/').replace(':', '\\:')
                    if os.path.isdir(fonts_dir):
                        v_filters.append(f"[{curr_v}]subtitles=filename='{escaped_ass}':fontsdir='{escaped_fonts}'[v_sub]")
                    else:
                        v_filters.append(f"[{curr_v}]subtitles=filename='{escaped_ass}'[v_sub]")
                    curr_v = "v_sub"
                except Exception as e_ass:
                    # Fallback nếu gặp lỗi sinh ASS
                    escaped_srt = srt_target.replace('\\', '/').replace(':', '\\:')
                    v_filters.append(f"[{curr_v}]subtitles='{escaped_srt}'[v_sub]")
                    curr_v = "v_sub"
        else:
            emit("ℹ️ [Phụ đề] Tùy chọn chèn phụ đề đang TẮT -> Video xuất ra hoàn toàn KHÔNG có phụ đề (không burn-in, không gắn filter subtitles/ass).")
            v_filters = [
                f for f in v_filters
                if ('dynamic_blur_mask' in f or 'v_b_mask' in f) or ('subtitles=' not in f and not f.startswith('[v_sub'))
            ]

        # Inputs initialization
        inputs = ['-i', input_video]
        dub_input_idx = None
        if dub_track and os.path.exists(dub_track):
            dub_input_idx = len(inputs) // 2
            inputs.extend(['-i', dub_track])

        # 3.5 Logo Watermark Overlay
        if has_logo:
            logo_input_idx = len(inputs) // 2
            inputs.extend(['-i', logo_path])

            x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
            y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
            w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
            h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
            opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

            box_w = max(2, (int(round(cur_out_w * (w_pct / 100.0))) // 2) * 2)
            box_h = max(2, (int(round(cur_out_h * (h_pct / 100.0))) // 2) * 2)
            box_x = max(0, int(round(cur_out_w * (x_pct / 100.0))))
            box_y = max(0, int(round(cur_out_h * (y_pct / 100.0))))

            v_filters.append(f"[{logo_input_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f},scale=w={box_w}:h={box_h}:force_original_aspect_ratio=decrease:force_divisible_by=2[logo_scaled]")
            v_filters.append(f"[{curr_v}][logo_scaled]overlay=x='{box_x}+({box_w}-overlay_w)/2':y='{box_y}+({box_h}-overlay_h)/2'[v_logo]")
            curr_v = "v_logo"

        # 3.5.5 Custom Multi-Region Blur & Dynamic Text Overlays
        #
        # ═══════ COORDINATE REMAPPING FOR PADDED FRAMES ═══════
        # Frontend percentages (x_pct, y_pct, w_pct, h_pct) are RELATIVE
        # to the actual video content area (excluding letterbox padding).
        # When aspect_ratio != 'original', FFmpeg uses scale+pad which
        # creates a padded frame.  We must remap user % into the padded
        # frame so the overlay matches the preview exactly.
        #
        # For 'original' (no pad): content fills entire frame → no remap.
        # ══════════════════════════════════════════════════════════
        if isinstance(custom_layers, list) and custom_layers:
            # Calculate content area within the (possibly padded) output frame
            # Padding exists when output dimensions differ from source aspect ratio
            _has_pad = (src_vw > 0) and (src_vh > 0) and (cur_out_w != src_vw or cur_out_h != src_vh)
            if _has_pad:
                src_ar = src_vw / src_vh
                out_ar = cur_out_w / cur_out_h
                if src_ar > out_ar:
                    _content_w = cur_out_w
                    _content_h = int(round(cur_out_w / src_ar))
                else:
                    _content_h = cur_out_h
                    _content_w = int(round(cur_out_h * src_ar))
                _pad_x = (cur_out_w - _content_w) / 2.0
                _pad_y = (cur_out_h - _content_h) / 2.0
            else:
                _content_w = cur_out_w
                _content_h = cur_out_h
                _pad_x = 0.0
                _pad_y = 0.0

            def _remap_pct(x_p, y_p, w_p, h_p):
                """Convert user percentages (relative to video content) into
                absolute fractions relative to the full output frame."""
                abs_x = (_pad_x + _content_w * x_p / 100.0) / cur_out_w
                abs_y = (_pad_y + _content_h * y_p / 100.0) / cur_out_h
                abs_w = (_content_w * w_p / 100.0) / cur_out_w
                abs_h = (_content_h * h_p / 100.0) / cur_out_h
                return abs_x, abs_y, abs_w, abs_h

            active_custom_layers = [l for l in custom_layers if l.get('visible') is not False]
            if active_custom_layers:
                emit(f"🎨 [Lớp phủ tùy chọn] Đang xử lý {len(active_custom_layers)} vùng làm mờ và chữ động theo mốc thời gian...")

            def parse_time_sec(t_val):
                if isinstance(t_val, (int, float)):
                    return float(t_val)
                if not t_val or not isinstance(t_val, str):
                    return 0.0
                clean = t_val.strip()
                parts = clean.split(':')
                try:
                    if len(parts) == 1:
                        return float(parts[0])
                    elif len(parts) == 2:
                        return int(parts[0]) * 60 + float(parts[1])
                    elif len(parts) == 3:
                        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
                except Exception:
                    return 0.0
                return 0.0

            for idx, layer in enumerate(custom_layers):
                if layer.get('visible') is False:
                    continue
                l_type = layer.get('type', 'blur')
                timing_mode = layer.get('timing_mode', 'all')
                x_pct = max(0.0, min(100.0, float(layer.get('x_pct', 10.0))))
                y_pct = max(0.0, min(100.0, float(layer.get('y_pct', 10.0))))
                w_pct = max(1.0, min(100.0, float(layer.get('w_pct', 30.0))))
                h_pct = max(1.0, min(100.0, float(layer.get('h_pct', 15.0))))

                # Remap user percentages into absolute fractions of the
                # (possibly padded) output frame so crop/overlay/drawbox
                # coordinates match the frontend preview exactly.
                ax, ay, aw, ah = _remap_pct(x_pct, y_pct, w_pct, h_pct)

                # Build enable expression for FFmpeg
                enable_expr = ""
                if timing_mode == 'custom':
                    s_sec = parse_time_sec(layer.get('start_time', 0))
                    e_sec = parse_time_sec(layer.get('end_time', 10))
                    if e_sec > s_sec:
                        enable_expr = f":enable='between(t,{s_sec:.3f},{e_sec:.3f})'"
                elif timing_mode == 'random':
                    dur = max(1.0, float(layer.get('random_duration', 5.0)))
                    interval = max(dur + 1.0, float(layer.get('random_interval', 15.0)))
                    enable_expr = f":enable='lte(mod(t,{interval:.2f}),{dur:.2f})'"

                out_label = f"v_ovl_{idx}"

                if l_type == 'blur':
                    blur_kind = layer.get('blur_type', 'boxblur')
                    if blur_kind == 'color':
                        # Solid color mask overlay
                        color_hex = str(layer.get('mask_color', '#000000')).lstrip('#')
                        if len(color_hex) != 6:
                            color_hex = "000000"
                        col_str = f"0x{color_hex}"
                        # Draw box using drawbox filter — use remapped fractions
                        x_expr = f"iw*{ax:.6f}"
                        y_expr = f"ih*{ay:.6f}"
                        w_expr = f"iw*{aw:.6f}"
                        h_expr = f"ih*{ah:.6f}"
                        v_filters.append(f"[{curr_v}]drawbox=x='{x_expr}':y='{y_expr}':w='{w_expr}':h='{h_expr}':color={col_str}@1.0:t=fill{enable_expr}[{out_label}]")
                        curr_v = out_label
                    else:
                        # Boxblur region: crop + blur + overlay
                        crop_label = f"v_crop_{idx}"
                        blur_label = f"v_bblur_{idx}"
                        base_label = f"v_base_{idx}"
                        v_filters.append(f"[{curr_v}]split[{base_label}][{crop_label}]")
                        # Blur radius — computed on the CONTENT area crop
                        crop_w = max(2, int(_content_w * w_pct / 100.0))
                        crop_h = max(2, int(_content_h * h_pct / 100.0))
                        max_luma_radius = max(1, min(crop_w, crop_h) // 2 - 1)
                        blur_sz = min(25, max(5, max_luma_radius))
                        # Use avgblur instead of boxblur: boxblur has a known chroma plane stride bug
                        # with CUDA hardware decoding (-hwaccel cuda) causing bright green box artifacts!
                        v_filters.append(
                            f"[{crop_label}]crop=w='trunc(iw*{aw:.6f}/2)*2':"
                            f"h='trunc(ih*{ah:.6f}/2)*2':"
                            f"x='trunc(iw*{ax:.6f}/2)*2':"
                            f"y='trunc(ih*{ay:.6f}/2)*2',"
                            f"avgblur=sizeX={blur_sz}:sizeY={blur_sz}[{blur_label}]"
                        )
                        v_filters.append(f"[{base_label}][{blur_label}]overlay=x='trunc(main_w*{ax:.6f}/2)*2':y='trunc(main_h*{ay:.6f}/2)*2'{enable_expr}[{out_label}]")
                        curr_v = out_label

                elif l_type == 'text':
                    text_str = str(layer.get('text', '')).strip()
                    if not text_str:
                        continue
                    
                    # Sanitize text for FFmpeg drawtext
                    clean_text = text_str.replace('\\', '\\\\').replace(':', '\\:').replace("'", "\\'").replace('%', '\\%')
                    
                    # Color
                    t_color = str(layer.get('color', '#ffffff')).lstrip('#')
                    if len(t_color) != 6:
                        t_color = "ffffff"
                    font_color_str = f"0x{t_color}"
                    
                    anim = layer.get('animation', 'none')
                    
                    # Font size: tỉ lệ chuẩn theo chiều cao video đầu ra
                    base_layer_fsize = max(10, int(layer.get('font_size', 24)))
                    f_sz = max(12, int(round(base_layer_fsize * (cur_out_h / 720.0))))
                    
                    # Use remapped fractions for text position
                    x_pos_expr = f"w*{ax:.6f}+10"
                    y_pos_expr = f"h*{ay:.6f}+(h*{ah:.6f}-th)/2"
                    alpha_expr = "1.0"
                    
                    if anim == 'fade':
                        # Fade in/out oscillation: alpha between 0.2 and 1.0
                        alpha_expr = "0.6+0.4*sin(2*PI*t/2.5)"
                    elif anim == 'pulse':
                        # Pulsing size or blinking
                        alpha_expr = "0.7+0.3*sin(2*PI*t/1.5)"
                    elif anim == 'marquee':
                        # Moving horizontally across box
                        x_pos_expr = f"w*{ax:.6f}+(w*{aw:.6f}-mod(t*60,w*{aw:.6f}+tw))"

                    drawtext_filter = (
                        f"drawtext=text='{clean_text}':fontsize={f_sz}:fontcolor={font_color_str}:"
                        f"alpha='{alpha_expr}':x='{x_pos_expr}':y='{y_pos_expr}':"
                        f"borderw=2:bordercolor=black{enable_expr}"
                    )
                    v_filters.append(f"[{curr_v}]{drawtext_filter}[{out_label}]")
                    curr_v = out_label

        # Final video output label
        if not v_filters:
            v_filters.append("[0:v]null[v_final]")
        else:
            v_filters[-1] = re.sub(r'\[[a-zA-Z0-9_]+\]$', '[v_final]', v_filters[-1])

        # 3.6 AI Stem & Vocal Separation (Lọc bỏ giọng thoại cũ, giữ lại hiệu ứng SFX)
        stem_enabled = is_dubbing_enabled and (
            parse_bool(dubbing.get('remove_original_vocals'), False) or (
                isinstance(dubbing.get('stem_separation'), dict)
                and parse_bool(dubbing.get('stem_separation', {}).get('enabled'), False)
            )
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
                job.set_stage(JobStage.STEM_SEPARATING, 0, "Đang tách âm thanh giọng nói (MDX-Net)...")
                cleaned_sfx = None
                if use_cache and precomputed_cleaned_path and os.path.exists(precomputed_cleaned_path) and os.path.getsize(precomputed_cleaned_path) > 1000:
                    cleaned_sfx = precomputed_cleaned_path
                    emit(f"⚡ [Tách âm thanh] Tái sử dụng file âm thanh SFX đã tách sẵn: {cleaned_sfx}")
                else:
                    import audio_separator
                    temp_stem_dir = os.path.join(ROOT_DIR, "output", "temp_stems")
                    emit("🎵 [Tách âm thanh] Bắt đầu tách giọng thoại cũ bằng mô hình AI MDX-Net...")

                    def _stem_progress_cb(pct, msg=""):
                        job.emit_progress(JobStage.STEM_SEPARATING, pct, f"Tách giọng AI: {msg}" if msg else "Đang tách giọng thoại MDX-Net...")

                    def _stem_logger_cb(txt):
                        job.emit_log(f"[MDX-Net] {txt}", 'info')

                    def _stem_cancel_cb():
                        return job.is_stopped() or STOP_EXPORT_FLAG

                    sep_res = audio_separator.separate_audio_stems(
                        input_video,
                        output_dir=temp_stem_dir,
                        mode=stem_mode,
                        device=stem_device,
                        progress_cb=_stem_progress_cb,
                        logger_cb=_stem_logger_cb,
                        cancel_check_cb=_stem_cancel_cb
                    )
                    if job.is_stopped() or STOP_EXPORT_FLAG:
                        emit("[EVENT:CANCELLED] Đã dừng tác vụ trong quá trình tách âm thanh.")
                        return
                    cleaned_sfx = sep_res.get('cleaned_path')

                if cleaned_sfx and os.path.exists(cleaned_sfx):
                    sfx_input_idx = len(inputs) // 2
                    inputs.extend(['-i', cleaned_sfx])
                    emit("✅ [Tách âm thanh] Đã tách giọng thoại cũ thành công, giữ lại nhạc nền & SFX.")
            except Exception as e:
                emit(f"⚠️ [Tách âm thanh] Lỗi tách âm thanh AI: {e}")

        # Construct Audio Filter Complex
        voice_vol = float(dubbing.get('voice_volume', 1.0))
        orig_vol = float(dubbing.get('original_volume', 0.45 if is_dubbing_enabled else 1.0))
        ducking = bool(dubbing.get('audio_ducking', False)) if is_dubbing_enabled else False
        
        a_filters = []
        orig_src = f"[{sfx_input_idx}:a]" if (sfx_input_idx is not None and stem_enabled) else "[0:a]"
        
        if dub_input_idx is not None:
            if has_orig_audio and orig_vol > 0.01:
                if abs(video_speed - 1.0) > 0.01:
                    a_filters.append(f"{orig_src}atempo={video_speed:.4f},volume={orig_vol:.2f}[a_orig]")
                else:
                    a_filters.append(f"{orig_src}volume={orig_vol:.2f}[a_orig]")
                if ducking:
                    # Dùng apad để đảm bảo luồng voice không bị ngắt sớm làm sidechaincompress kết thúc
                    # và làm tắt tiếng video gốc khi phụ đề kết thúc ở phút thứ 30
                    a_filters.append(f"[{dub_input_idx}:a]volume={voice_vol:.2f},apad[a_voice_padded]")
                    a_filters.append(f"[a_voice_padded]asplit=2[a_voice_ctrl][a_voice_mix]")
                    a_filters.append(f"[a_orig][a_voice_ctrl]sidechaincompress=threshold=0.08:ratio=5:attack=20:release=350[a_orig_ducked]")
                    a_filters.append(f"[a_orig_ducked][a_voice_mix]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_final]")
                else:
                    a_filters.append(f"[{dub_input_idx}:a]volume={voice_vol:.2f}[a_voice]")
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

        # ── Encoder Selection with Hardware Probe & Hardware Decoding ──
        hw_caps = ffmpeg_installer.get_hardware_capabilities(ffmpeg_path)
        gpu_model = hw_caps.get('gpu_model') or hw_caps.get('gpu_name') or 'GPU'
        driver_version = hw_caps.get('driver_version') or 'N/A'
        nvenc_supported = hw_caps.get('nvenc_supported', False)
        supported_encoders = hw_caps.get('supported_encoders') or (['libx264', 'h264_nvenc'] if nvenc_supported else ['libx264'])
        hardware_decoders = hw_caps.get('hardware_decoders') or []
        hw_dec_dict = hw_caps.get('hw_decoders') or {}

        # Tự động chọn encoder GPU nhanh nhất nếu người dùng để 'auto' hoặc rỗng
        if encoder in {'auto', '', 'default'}:
            if nvenc_supported or 'h264_nvenc' in supported_encoders:
                active_encoder = 'h264_nvenc'
            elif hw_caps.get('mf_supported') or 'h264_mf' in supported_encoders:
                active_encoder = 'h264_mf'
            elif hw_caps.get('amf_supported') or 'h264_amf' in supported_encoders:
                active_encoder = 'h264_amf'
            elif hw_caps.get('qsv_supported') or 'h264_qsv' in supported_encoders:
                active_encoder = 'h264_qsv'
            else:
                active_encoder = 'libx264'
        else:
            active_encoder = encoder

        is_nvenc_requested = 'nvenc' in active_encoder.lower()

        if is_nvenc_requested and not nvenc_supported and 'h264_nvenc' not in supported_encoders:
            emit(f"⚠️ [CẢNH BÁO GPU] Bộ mã hóa NVIDIA NVENC không khả dụng trên hệ thống (GPU: {gpu_model}, Driver: {driver_version}).")
            emit("📋 Nguyên nhân: Driver NVIDIA hiện tại không tương thích với phiên bản NVENC API của bộ nhị phân FFmpeg.")
            emit("🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...")
            active_encoder = 'libx264'
        elif 'mf' in active_encoder.lower() and not hw_caps.get('mf_supported') and 'h264_mf' not in supported_encoders:
            emit("⚠️ [CẢNH BÁO GPU] Bộ mã hóa MediaFoundation không hoạt động trên máy này.")
            emit("🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...")
            active_encoder = 'libx264'
        elif 'amf' in active_encoder.lower() and not hw_caps.get('amf_supported') and 'h264_amf' not in supported_encoders:
            emit(f"⚠️ [CẢNH BÁO GPU] Bộ mã hóa AMD AMF không hoạt động trên máy này (GPU: {gpu_model}).")
            emit("🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...")
            active_encoder = 'libx264'
        elif 'qsv' in active_encoder.lower() and not hw_caps.get('qsv_supported') and 'h264_qsv' not in supported_encoders:
            emit(f"⚠️ [CẢNH BÁO GPU] Bộ mã hóa Intel QSV không hoạt động trên máy này (GPU: {gpu_model}).")
            emit("🔄 Tự động chuyển sang bộ mã hóa CPU (libx264) để đảm bảo xuất video thành công...")
            active_encoder = 'libx264'

        # Kiểm tra xem có thể dùng phần cứng giải mã (NVDEC/CUDA) hay không
        can_hw_decode = (
            'nvenc' in active_encoder.lower()
            and (hw_dec_dict.get('cuda_hwaccel') or 'cuda' in hardware_decoders or any('cuvid' in d for d in hardware_decoders))
        )
        decoder_label = f"NVIDIA NVDEC (CUDA)" if can_hw_decode else "CPU Native"

        # Base FFmpeg command structure
        cmd_base = [ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'info']
        if trim_enabled and trim_start:
            cmd_base.extend(['-ss', trim_start])
        if trim_enabled and trim_end:
            cmd_base.extend(['-to', trim_end])

        # Nếu hỗ trợ phần cứng giải mã, thêm -hwaccel cuda trước video đầu vào chính
        if can_hw_decode and len(inputs) >= 2 and inputs[0] == '-i':
            cmd_base.extend(['-hwaccel', 'cuda'])
        cmd_base.extend(inputs)

        # Ghi filter_complex ra tệp script để tránh lỗi WinError 206 dòng lệnh quá dài
        try:
            filter_script_path = os.path.join(editor_temp_dir, f'filter_graph_{int(time.time()*1000)}.txt')
            with open(filter_script_path, 'w', encoding='utf-8') as f_fc:
                f_fc.write(full_filter_complex)
            fc_flag = get_filter_script_flag(ffmpeg_path)
            cmd_base.extend([fc_flag, filter_script_path])
        except Exception as e_fc:
            print(f"[Export Pipeline] Cảnh báo tạo file script bộ lọc: {e_fc}. Fallback về CLI inline.")
            cmd_base.extend(['-filter_complex', full_filter_complex])
        cmd_base.extend(['-map', '[v_final]', '-map', '[a_final]'])

        export_bitrate_k = max(1000, bitrate)

        def build_encoder_args(enc_name):
            args = []
            args.extend(['-threads', ffmpeg_thread_arg])
            args.extend(['-filter_complex_threads', '0'])
            is_nv = 'nvenc' in enc_name.lower()

            if is_nv:
                # NVENC Presets: p1 (nhanh nhất) đến p7 (chất lượng cao nhất)
                if preset in {'p1', 'p2', 'p3', 'p4', 'p5', 'p6', 'p7'}:
                    nv_preset = preset
                elif preset in {'ultrafast', 'superfast'}:
                    nv_preset = 'p1'
                elif preset in {'veryfast', 'faster'}:
                    nv_preset = 'p2'
                elif preset in {'fast', 'medium'}:
                    nv_preset = 'p4'
                elif preset in {'slow', 'slower'}:
                    nv_preset = 'p6'
                elif preset == 'veryslow':
                    nv_preset = 'p7'
                elif export_profile == 'fast_gpu':
                    nv_preset = 'p2'
                elif export_profile == 'master':
                    nv_preset = 'p6'
                else:
                    nv_preset = 'p4'

                cq_val = '22' if export_profile == 'fast_gpu' else ('17' if export_profile == 'master' else '19')

                if bitrate_mode == 'CBR':
                    args.extend([
                        '-c:v', enc_name, '-preset', nv_preset, '-tune', 'hq',
                        '-b:v', f'{export_bitrate_k}k', '-maxrate', f'{export_bitrate_k}k',
                        '-bufsize', f'{export_bitrate_k * 2}k'
                    ])
                else:
                    args.extend([
                        '-c:v', enc_name, '-preset', nv_preset, '-tune', 'hq',
                        '-rc', 'vbr', '-cq', cq_val,
                        '-b:v', f'{export_bitrate_k}k', '-maxrate', f'{int(export_bitrate_k * 1.5)}k',
                        '-bufsize', f'{export_bitrate_k * 2}k', '-spatial-aq', '1'
                    ])
            elif 'mf' in enc_name.lower():
                args.extend(['-c:v', 'h264_mf', '-b:v', f'{export_bitrate_k}k'])
            elif 'amf' in enc_name.lower():
                amf_qual = 'speed' if export_profile == 'fast_gpu' else ('quality' if export_profile == 'master' else 'balanced')
                args.extend(['-c:v', 'h264_amf', '-quality', amf_qual, '-b:v', f'{export_bitrate_k}k'])
            elif 'qsv' in enc_name.lower():
                qsv_pre = 'veryfast' if export_profile == 'fast_gpu' else ('medium' if export_profile == 'master' else 'faster')
                qsv_gq = '22' if export_profile == 'fast_gpu' else ('17' if export_profile == 'master' else '19')
                args.extend(['-c:v', 'h264_qsv', '-preset', qsv_pre, '-global_quality', qsv_gq, '-b:v', f'{export_bitrate_k}k'])
            else:
                # CPU libx264
                if preset in {'ultrafast', 'superfast', 'veryfast', 'faster', 'fast', 'medium', 'slow', 'slower', 'veryslow'}:
                    cpu_preset = preset
                elif export_profile == 'fast_gpu':
                    cpu_preset = 'veryfast'
                elif export_profile == 'master':
                    cpu_preset = 'slow'
                else:
                    cpu_preset = 'faster'

                crf_val = '22' if export_profile == 'fast_gpu' else ('17' if export_profile == 'master' else '19')
                if bitrate_mode == 'CBR':
                    args.extend([
                        '-c:v', 'libx264', '-preset', cpu_preset,
                        '-b:v', f'{export_bitrate_k}k', '-maxrate', f'{export_bitrate_k}k',
                        '-bufsize', f'{export_bitrate_k * 2}k'
                    ])
                else:
                    args.extend(['-c:v', 'libx264', '-preset', cpu_preset, '-crf', crf_val])
            return args

        encoders_to_try = [active_encoder]
        if active_encoder != 'libx264':
            encoders_to_try.append('libx264')

        export_succeeded = False
        log_buffer = collections.deque(maxlen=100)
        diagnostic_keywords = (
            'error', 'warning', 'failed', 'invalid', 'cannot', 'not within',
            'could not', 'no such', 'denied', 'unsupported', 'terminat', 'abort',
            'exception', 'broken'
        )

        for enc_idx, current_enc in enumerate(encoders_to_try):
            if STOP_EXPORT_FLAG:
                break

            is_gpu_mode = (current_enc != 'libx264')
            hw_type_label = "⚡ GPU TĂNG TỐC" if is_gpu_mode else "⚪ CPU ĐA LUỒNG"
            encoder_label = f"GPU {current_enc.upper()} ({gpu_model})" if is_gpu_mode else f"CPU {current_enc}"
            hw_badge = "⚡ GPU" if is_gpu_mode else "⚪ CPU"

            if is_gpu_mode:
                emit(f"⚡ [CHẾ ĐỘ PHẦN CỨNG: GPU TĂNG TỐC] Đang xuất bằng GPU: {gpu_model} ({current_enc}) | Giải mã: {decoder_label} | Driver: {driver_version}")
            else:
                emit(f"⚪ [CHẾ ĐỘ PHẦN CỨNG: CPU] Đang xuất bằng CPU đa luồng (libx264) | Luồng: {thread_display_label}")

            emit(f"🚀 Cấu hình phần cứng: {gpu_model} (Driver: {driver_version}) | Decoder: {decoder_label} | Encoder: {encoder_label} | Profile: {export_profile.upper()} | Luồng: {thread_display_label}")
            emit(f"🎬 Đang xuất video chất lượng cao (Thiết bị: {hw_type_label}, Bộ mã hóa: {encoder_label}, Âm lượng lồng tiếng: {int(voice_vol*100)}%, Âm lượng gốc: {int(orig_vol*100)}%)...")

            cmd_export = list(cmd_base)
            # Nếu đây là fallback sang CPU, loại bỏ -hwaccel cuda nếu đã lỡ thêm
            if current_enc == 'libx264' and '-hwaccel' in cmd_export:
                hw_idx = cmd_export.index('-hwaccel')
                cmd_export.pop(hw_idx + 1)
                cmd_export.pop(hw_idx)

            cmd_export.extend(build_encoder_args(current_enc))
            cmd_export.extend([
                '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-b:a', '320k',
                part_output_path
            ])

            job.set_stage(JobStage.ENCODING, 0, f"Đang xuất video ({current_enc})...")
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
            job.register_process(process)
            with _export_lock:
                current_export_process = process

            time_regex = re.compile(r'time=(\d+):(\d+):([0-9.]+)')
            log_buffer.clear()

            for line in iter(process.stdout.readline, ''):
                if job.is_stopped() or STOP_EXPORT_FLAG:
                    break
                if line:
                    l_str = line.strip()
                    log_buffer.append(l_str)
                    if 'frame=' in l_str or 'time=' in l_str or 'size=' in l_str or 'speed=' in l_str:
                        time_match = time_regex.search(l_str)
                        speed_match = re.search(r'speed=\s*([0-9.]+)x', l_str)
                        if time_match and video_duration > 0:
                            hrs = int(time_match.group(1))
                            mins = int(time_match.group(2))
                            secs = float(time_match.group(3))
                            cur_sec = hrs * 3600 + mins * 60 + secs
                            pct = min(99, int((cur_sec / video_duration) * 100))
                            speed_val = float(speed_match.group(1)) if speed_match else 0.0
                            eta_text = ""
                            if speed_val > 0.05:
                                rem_sec = max(0, (video_duration - cur_sec) / speed_val)
                                m_eta, s_eta = divmod(int(rem_sec), 60)
                                h_eta, m_eta = divmod(m_eta, 60)
                                eta_text = f" | Còn lại: {h_eta:02d}:{m_eta:02d}:{s_eta:02d}"
                            speed_text = f" | {speed_val:.1f}x" if speed_val > 0 else ""
                            emit(f"⏳ [Tiến độ: {pct}% | {hw_badge}{speed_text}{eta_text}] {l_str}")
                        else:
                            emit(f"⏳ [{hw_badge}] {l_str}")
                    elif any(kw in l_str.lower() for kw in diagnostic_keywords):
                        emit(f"ℹ️ [{hw_badge}] {l_str}")

            process.stdout.close()
            return_code = process.wait()
            job.unregister_process(process)

            # Phân loại nguyên nhân lỗi chính xác từ stderr FFmpeg (Ưu tiên 2)
            log_text = "\n".join(log_buffer).lower()
            is_oom = ('cannot allocate memory' in log_text or 'out of memory' in log_text or return_code == -1073741571)
            is_filter_err = ('error initializing filter' in log_text or 'no such filter' in log_text or ('invalid argument' in log_text and 'filter' in log_text))
            is_disk_full = ('no space left on device' in log_text or 'disk full' in log_text)
            is_perm_denied = ('permission denied' in log_text or 'access is denied' in log_text)

            if return_code == 0 and os.path.exists(part_output_path) and os.path.getsize(part_output_path) > 1000:
                if os.path.exists(final_output_path):
                    try:
                        os.replace(part_output_path, final_output_path)
                    except Exception:
                        os.remove(final_output_path)
                        os.rename(part_output_path, final_output_path)
                else:
                    os.rename(part_output_path, final_output_path)
                export_succeeded = True
                file_size_mb = os.path.getsize(final_output_path) / (1024 * 1024)
                history_id = None
                try:
                    from export_history import get_export_history_service
                    service = get_export_history_service()
                    history_id = service.record_export(
                        output_path=final_output_path,
                        source_tool=source_tool,
                        source_kind='editor',
                        export_run_id=export_run_id,
                        params={
                            'mode': 'encode',
                            'encoder': current_enc,
                            'preset': preset,
                            'resolution': resolution,
                            'input_video': input_video
                        }
                    )
                except Exception as he:
                    logging.getLogger(__name__).error(f"[ExportHistory] Error recording encode export: {he}")
                try:
                    from telegram_notifier import get_telegram_notifier
                    notifier = get_telegram_notifier()
                    if notifier.enabled and notifier.notify_per_video:
                        video_title = os.path.basename(input_video) if input_video else output_name
                        notifier.notify_task_success(
                            task_type='editor',
                            task_title='Biên Tập Phim',
                            video_title=video_title,
                            output_path=final_output_path,
                            duration_sec=time.time() - export_start_time,
                            file_size_mb=file_size_mb,
                            extra_info={'Preset': preset, 'Encoder': current_enc}
                        )
                except Exception as te:
                    logging.getLogger(__name__).warning(f"[Telegram] Error sending encode notification: {te}")
                emit(f"✅ [XUẤT THÀNH CÔNG] Video đã được lưu tại: {final_output_path} ({file_size_mb:.1f} MB)")
                emit(f"[EVENT:SUCCESS] {json.dumps({'path': final_output_path, 'size_mb': round(file_size_mb, 2), 'history_id': history_id})}")
                emit(f"--- HOÀN THÀNH QUÁ TRÌNH TẠO ---")
                break
            else:
                if is_oom:
                    emit(f"🛑 [LỖI BỘ NHỚ] FFmpeg không thể cấp phát bộ nhớ (Cannot allocate memory / ENOMEM).")
                    emit(f"📋 Chi tiết: Hệ thống thiếu RAM vật lý hoặc bộ nhớ ảo Windows (Pagefile commit limit) bị đầy.")
                    emit(f"💡 Gợi ý: Hãy tăng kích thước Pagefile trong Windows Settings, đóng bớt ứng dụng nặng hoặc giảm độ phân giải xuất.")
                    break
                elif is_filter_err:
                    emit(f"🛑 [LỖI BỘ LỌC] Khởi tạo đồ thị bộ lọc FFmpeg (filter graph) thất bại.")
                    emit(f"💡 Gợi ý: Kiểm tra lại các tùy chọn làm mờ, lồng phụ đề hoặc lớp phủ overlay.")
                    break
                elif is_disk_full:
                    emit(f"🛑 [LỖI Ổ ĐĨA] Ổ đĩa đích đã đầy (No space left on device).")
                    emit(f"💡 Gợi ý: Giải phóng dung lượng ổ đĩa {os.path.splitdrive(output_dir)[0]} và thử lại.")
                    break
                elif is_perm_denied:
                    emit(f"🛑 [LỖI QUYỀN TRUY CẬP] Bị từ chối quyền ghi file hoặc file video đang bị mở bởi phần mềm khác.")
                    emit(f"💡 Gợi ý: Đóng các phần mềm đang phát video đầu ra hoặc chạy ứng dụng với quyền Administrator.")
                    break
                elif enc_idx < len(encoders_to_try) - 1 and not STOP_EXPORT_FLAG:
                    diag_snippet = "\n".join(list(log_buffer)[-15:])
                    emit(f"⚠️ [CẢNH BÁO GPU] Bộ mã hóa {current_enc} gặp sự cố phần cứng/driver (Mã lỗi: {return_code}).")
                    emit(f"📋 Chi tiết lỗi từ FFmpeg:\n{diag_snippet[:400]}")
                    emit(f"🔄 Tự động kích hoạt cơ chế dự phòng: chuyển sang bộ mã hóa CPU (libx264 | Luồng: {thread_display_label}) để tiếp tục...")
                    if os.path.exists(part_output_path):
                        try:
                            os.remove(part_output_path)
                        except Exception:
                            pass
                    continue


        if not export_succeeded and not STOP_EXPORT_FLAG:
            emit(f"🛑 [LỖI XUẤT VIDEO] FFmpeg không thể tạo được video đầu ra.")
            emit(f"📋 Chi tiết chẩn đoán từ FFmpeg:")
            for err_line in list(log_buffer)[-20:]:
                emit(f"🛑 [FFmpeg] {err_line}")

            # Gợi ý ngữ cảnh chính xác
            if is_oom:
                emit(f"💡 Gợi ý: Lỗi tràn bộ nhớ (RAM/Pagefile). Vui lòng cấu hình lại Windows Virtual Memory.")
            elif is_disk_full:
                emit(f"💡 Gợi ý: Ổ đĩa đã đầy. Vui lòng dọn dẹp dung lượng ổ đĩa.")
            elif is_perm_denied:
                emit(f"💡 Gợi ý: Không có quyền ghi file hoặc file video đang bị khóa bởi trình phát khác.")
            else:
                emit(f"💡 Gợi ý: Kiểm tra dung lượng ổ đĩa, đường dẫn file hoặc quyền ghi thư mục.")

            # Lưu tệp nhật ký chẩn đoán chi tiết để phục vụ tái hiện lỗi
            try:
                diag_file = os.path.join(editor_temp_dir, f'export_failure_diagnostic_{int(time.time()*1000)}.log')
                with open(diag_file, 'w', encoding='utf-8') as f_diag:
                    f_diag.write("=== NOVACUT EXPORT FAILURE DIAGNOSTIC ===\n")
                    f_diag.write(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f_diag.write(f"FFmpeg Path: {ffmpeg_path}\n")
                    f_diag.write(f"Encoder Tried: {current_enc}\n")
                    f_diag.write(f"Exit Code: {return_code}\n")
                    f_diag.write(f"Filter Script: {filter_script_path}\n")
                    f_diag.write(f"Mask ASS File: {dyn_blur_mask_path}\n")
                    f_diag.write(f"Command:\n{' '.join(cmd_export)}\n\n")
                    f_diag.write("=== LAST 100 FFMPEG LOG LINES ===\n")
                    f_diag.write("\n".join(log_buffer))
                emit(f"📝 Đã lưu hồ sơ chẩn đoán kỹ thuật tại: {diag_file}")
            except Exception:
                pass

            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video:
                    video_title = os.path.basename(input_video) if input_video else output_name
                    notifier.notify_task_failure(
                        task_type='editor',
                        task_title='Biên Tập Phim',
                        video_title=video_title,
                        error_message=f"FFmpeg export failed (Exit code: {return_code})",
                        duration_sec=time.time() - export_start_time
                    )
            except Exception as te:
                pass
            emit(f"[EVENT:FAILED] {json.dumps({'reason': 'FFmpeg export failed', 'return_code': return_code})}")
        elif STOP_EXPORT_FLAG:
            emit(f"[EVENT:CANCELLED] {json.dumps({'reason': 'User stopped export'})}")

    except GeneratorExit:
        _terminate_process_tree(process)
    except Exception as ex:
        emit(f"🛑 [LỖI HỆ THỐNG]: {str(ex)}")
        emit(f"[EVENT:FAILED] {json.dumps({'reason': str(ex)})}")
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
        # Chỉ dọn dẹp file kịch bản bộ lọc và mặt nạ khi xuất THÀNH CÔNG
        # để bảo tồn bằng chứng kỹ thuật phục vụ chẩn đoán khi có lỗi
        if export_succeeded:
            if filter_script_path and os.path.exists(filter_script_path):
                try:
                    os.remove(filter_script_path)
                except Exception:
                    pass
            if dyn_blur_mask_path and os.path.exists(dyn_blur_mask_path):
                try:
                    os.remove(dyn_blur_mask_path)
                except Exception:
                    pass
        if temp_srt_path and os.path.exists(temp_srt_path):
            try:
                os.remove(temp_srt_path)
            except Exception:
                pass
        if not export_succeeded and part_output_path and os.path.exists(part_output_path):
            try:
                os.remove(part_output_path)
            except Exception:
                pass



# ═══════════════════════════════════════════════════════
# EXPORT API ROUTES (DECOUPLED JOB ARCHITECTURE)
# ═══════════════════════════════════════════════════════

@video_edit_bp.route('/api/start', methods=['POST'])
def start_generation():
    """Endpoint xuất video tương thích ngược: tạo job và trả về SSE stream đăng ký."""
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    val_err = validate_export_payload(data)
    if val_err:
        return val_err

    manager = get_export_job_manager()
    active_job = manager.get_active_job()
    if active_job and not active_job.is_terminal():
        client_run_id = str(data.get('export_run_id') or '').strip()
        if client_run_id and client_run_id == active_job.export_run_id:
            return Response(active_job.stream_events(start_seq=0), mimetype='text/event-stream')
        return jsonify({'success': False, 'error': 'Một tác vụ xuất video khác đang chạy'}), 409

    source_tool = str(data.get('source_tool') or 'editor').strip()
    export_run_id = str(data.get('export_run_id') or f"run_{int(time.time()*1000)}_{os.urandom(4).hex()}").strip()

    job = manager.create_job(
        params=data,
        run_fn=lambda j: execute_export_pipeline(j, data),
        source_tool=source_tool,
        export_run_id=export_run_id
    )

    return Response(job.stream_events(start_seq=0), mimetype='text/event-stream')


@video_edit_bp.route('/api/export/jobs', methods=['POST'])
def create_export_job():
    """Tạo tác vụ xuất video nền độc lập, trả về 202 Accepted và job_id."""
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    val_err = validate_export_payload(data)
    if val_err:
        return val_err

    manager = get_export_job_manager()
    active_job = manager.get_active_job()
    if active_job and not active_job.is_terminal():
        client_run_id = str(data.get('export_run_id') or '').strip()
        if client_run_id and client_run_id == active_job.export_run_id:
            return jsonify({'success': True, 'job_id': active_job.job_id, 'state': active_job.state, 'reused': True}), 200
        return jsonify({'success': False, 'error': 'Một tác vụ xuất video khác đang chạy'}), 409

    source_tool = str(data.get('source_tool') or 'editor').strip()
    export_run_id = str(data.get('export_run_id') or f"run_{int(time.time()*1000)}_{os.urandom(4).hex()}").strip()

    job = manager.create_job(
        params=data,
        run_fn=lambda j: execute_export_pipeline(j, data),
        source_tool=source_tool,
        export_run_id=export_run_id
    )

    return jsonify({'success': True, 'job_id': job.job_id, 'state': job.state}), 202


@video_edit_bp.route('/api/export/jobs/<job_id>', methods=['GET'])
def get_export_job(job_id):
    """Tra cứu trạng thái chi tiết của một job xuất video (reconciliation)."""
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    manager = get_export_job_manager()
    job = manager.get_job(job_id)
    if not job:
        return jsonify({'success': False, 'error': 'Không tìm thấy tác vụ'}), 404
    info = job.to_dict() if hasattr(job, 'to_dict') else job
    return jsonify({'success': True, 'job': info})


@video_edit_bp.route('/api/export/jobs/<job_id>/events', methods=['GET'])
def get_export_job_events(job_id):
    """Đăng ký nhận luồng SSE của job, hỗ trợ bù sự kiện qua tham số ?after=<seq>."""
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    manager = get_export_job_manager()
    job = manager.get_job(job_id)
    if not job or not hasattr(job, 'stream_events'):
        return jsonify({'success': False, 'error': 'Không tìm thấy tác vụ đang chạy'}), 404
    after_seq = int(request.args.get('after', 0))
    return Response(job.stream_events(start_seq=after_seq), mimetype='text/event-stream')


@video_edit_bp.route('/api/export/jobs/<job_id>/cancel', methods=['POST'])
def cancel_export_job(job_id):
    """Hủy một job xuất video cụ thể."""
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    manager = get_export_job_manager()
    stopped = manager.cancel_job(job_id, reason="Người dùng bấm hủy tác vụ")
    return jsonify({'success': True, 'stopped': stopped, 'message': 'Đã gửi yêu cầu dừng tác vụ'})


@video_edit_bp.route('/api/stop_export', methods=['POST'])
@video_edit_bp.route('/api/stop', methods=['POST'])
def stop_export_process():
    """Hủy tác vụ xuất video hiện tại (tương thích các nút Dừng khẩn cấp)."""
    global current_export_process, STOP_EXPORT_FLAG
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    STOP_EXPORT_FLAG = True
    manager = get_export_job_manager()
    stopped = manager.cancel_job(reason="Người dùng yêu cầu dừng khẩn cấp")
    with _export_lock:
        process = current_export_process
    if process:
        _terminate_process_tree(process)
    return jsonify({
        'success': True,
        'stopped': stopped,
        'message': 'Đã gửi yêu cầu dừng tác vụ xuất video hiện tại.'
    })


@video_edit_bp.route('/api/export_status', methods=['GET'])
def get_export_status():
    """Trả về trạng thái tác vụ xuất video với thông tin chi tiết đầy đủ."""
    global _export_active
    manager = get_export_job_manager()
    active_job = manager.get_active_job()
    if active_job:
        return jsonify({
            'active': True,
            'job_id': active_job.job_id,
            'state': active_job.state,
            'stage': active_job.stage,
            'progress': active_job.stage_progress,
            'message': active_job.stage_message,
            'error': active_job.error,
            'output_path': active_job.output_path
        })
    return jsonify({'active': bool(_export_active)})
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
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if device not in {'cpu', 'cuda', 'auto'} or not isinstance(region, dict):
        return jsonify({'success': False, 'error': 'Device hoặc vùng OCR không hợp lệ'}), 400
    if not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        from routes.core import find_media_on_system
        resolved = find_media_on_system(video_path)
        if resolved and is_path_allowed(resolved, must_exist=True, extensions=_VIDEO_EXTENSIONS):
            video_path = resolved
        else:
            return jsonify({'success': False, 'error': 'Video OCR không hợp lệ hoặc chưa được cho phép'}), 400
    with _ocr_lock:
        if _ocr_active:
            return jsonify({'success': False, 'error': 'Một tác vụ OCR khác đang chạy'}), 409
        _ocr_active = True
        STOP_OCR_FLAG = False

    ocr_start_time = time.time()
    def generate():
        global _ocr_active
        import importlib
        import ocr_module
        importlib.reload(ocr_module)
        primary_srt_result = None
        try:
            for msg in ocr_module.process_ocr(video_path, region, fps, threads, device, lambda: STOP_OCR_FLAG, output_dir=output_dir):
                if '[RESULT_SRT]' in msg:
                    primary_srt_result = msg.split('[RESULT_SRT]')[1].strip()
                yield msg

            # Gửi thông báo Telegram khi OCR hoàn tất
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video and not STOP_OCR_FLAG:
                    notifier.notify_task_success(
                        task_type='ocr',
                        task_title='Trích Xuất Phụ Đề OCR',
                        video_title=os.path.basename(video_path),
                        output_path=primary_srt_result or '',
                        duration_sec=time.time() - ocr_start_time,
                        extra_info={'FPS quét': fps, 'Thiết bị': device.upper()}
                    )
            except Exception as _te:
                logging.getLogger(__name__).warning(f"[Telegram] Error sending OCR notification: {_te}")

        except Exception as e:
            yield f"data: Lỗi xử lý OCR: {str(e)}\n\n"
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video and not STOP_OCR_FLAG:
                    notifier.notify_task_failure(
                        task_type='ocr',
                        task_title='Trích Xuất Phụ Đề OCR',
                        video_title=os.path.basename(video_path),
                        error_message=str(e),
                        duration_sec=time.time() - ocr_start_time
                    )
            except Exception:
                pass
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
        from routes.core import find_media_on_system
        resolved = find_media_on_system(video_path)
        if resolved and is_path_allowed(resolved, must_exist=True, extensions=_VIDEO_EXTENSIONS):
            video_path = resolved
        else:
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
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))

    if not video_path or not is_path_allowed(video_path, must_exist=True, extensions=_VIDEO_EXTENSIONS):
        from routes.core import find_media_on_system
        resolved = find_media_on_system(video_path)
        if resolved and is_path_allowed(resolved, must_exist=True, extensions=_VIDEO_EXTENSIONS):
            video_path = resolved
        else:
            return jsonify({'success': False, 'error': 'Vui lòng cung cấp đường dẫn video'}), 400
    if not isinstance(region, dict) or not isinstance(subtitles, list) or len(subtitles) > 50000:
        return jsonify({'success': False, 'error': 'Danh sách phụ đề không hợp lệ hoặc quá lớn'}), 400

    editor_temp_dir = get_editor_temp_dir(output_dir, video_path)
    try:
        os.makedirs(editor_temp_dir, exist_ok=True)
    except Exception:
        pass
    ai_boxes_path = os.path.join(editor_temp_dir, 'ai_blur_boxes.json')

    # Lưu editor_subtitles.srt nếu chưa có trong thư mục tạm
    srt_cache_file = os.path.join(editor_temp_dir, 'editor_subtitles.srt')
    if subtitles and (not os.path.exists(srt_cache_file) or os.path.getsize(srt_cache_file) < 10):
        try:
            with open(srt_cache_file, 'w', encoding='utf-8') as sf:
                for i, s in enumerate(subtitles, 1):
                    ts = ocr_module.format_time(float(s.get('startSeconds', 0)))
                    te = ocr_module.format_time(float(s.get('endSeconds', 0)))
                    tx = s.get('text', '') or s.get('original_text', '')
                    sf.write(f"{i}\n{ts} --> {te}\n{tx}\n\n")
        except Exception:
            pass

    def generate():
        try:
            for event in ocr_module.scan_preview_boxes_generator(video_path, region, subtitles, save_cache_path=ai_boxes_path):
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

@video_edit_bp.route('/api/editor/check_cache', methods=['POST'])
def editor_check_cache():
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    input_video = str(data.get('input_video') or '').strip().strip('"\'')
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if not is_path_allowed(output_dir):
        return jsonify({'success': False, 'error': 'Thư mục output chưa được cho phép'}), 403

    # Nếu không có video đầu vào hoặc video không tồn tại thì không có cache hợp lệ
    if not input_video or not os.path.exists(input_video):
        return jsonify({
            "success": True,
            "has_cache": False,
            "files": [],
            "details": {}
        })

    editor_temp_dir = get_editor_temp_dir(output_dir, input_video)

    fresh_run = parse_bool(data.get('fresh_run'), False)
    if fresh_run:
        # Xóa sạch các artifact cache cũ để fresh run 100%
        if os.path.exists(editor_temp_dir):
            for stale_fname in ['dubbed_timeline.wav', 'stem_cleaned.wav', 'ai_blur_boxes.json', 'tts_manifest.json', 'editor_subtitles.srt', 'ocr_subtitles.srt']:
                stale_path = os.path.join(editor_temp_dir, stale_fname)
                if os.path.exists(stale_path):
                    try:
                        os.remove(stale_path)
                    except OSError:
                        pass
        return jsonify({
            "success": True,
            "has_cache": False,
            "files": [],
            "details": {}
        })

    dubbing = data.get('dubbing')
    has_dubbing_param = isinstance(dubbing, dict)
    is_dubbing_enabled = parse_bool(dubbing.get('enabled'), False) if has_dubbing_param else True

    has_blur_param = 'blur_original_subtitles' in data
    subtitles_enabled = parse_bool(data.get('subtitles_enabled'), True) if 'subtitles_enabled' in data else True
    blur_enabled = parse_bool(data.get('blur_original_subtitles'), False) if has_blur_param else True
    if not subtitles_enabled and not parse_bool(data.get('force_blur_without_sub'), False):
        blur_enabled = False

    is_export_check = has_dubbing_param or has_blur_param

    cached_files = []
    found_details = {}

    if os.path.exists(editor_temp_dir):
        # 1. Track lồng tiếng AI
        dub_track = os.path.join(editor_temp_dir, 'dubbed_timeline.wav')
        if os.path.exists(dub_track) and os.path.getsize(dub_track) > 1000:
            found_details['dubbed_track'] = dub_track
            if not is_export_check or is_dubbing_enabled:
                cached_files.append('Track lồng tiếng AI (dubbed_timeline.wav)')

        # 2. Nhạc nền tách giọng
        stem_audio = os.path.join(editor_temp_dir, 'stem_cleaned.wav')
        if os.path.exists(stem_audio) and os.path.getsize(stem_audio) > 1000:
            found_details['stem_audio'] = stem_audio
            if not is_export_check or (is_dubbing_enabled and (dubbing.get('remove_original_vocals') or dubbing.get('stem_separation', {}).get('enabled'))):
                cached_files.append('Nhạc nền tách giọng (stem_cleaned.wav)')

        # 3. Tọa độ quét làm mờ AI Pixel
        ai_boxes = os.path.join(editor_temp_dir, 'ai_blur_boxes.json')
        if os.path.exists(ai_boxes) and os.path.getsize(ai_boxes) > 10:
            count = 0
            try:
                with open(ai_boxes, 'r', encoding='utf-8') as f:
                    b_data = json.load(f)
                if isinstance(b_data, list):
                    count = sum(1 for item in b_data if (isinstance(item, dict) and item.get('box')) or (isinstance(item, (list, tuple)) and len(item) >= 5)) or len(b_data)
            except Exception:
                pass
            found_details['ai_boxes'] = ai_boxes
            found_details['ai_boxes_count'] = count
            if not is_export_check or blur_enabled:
                cached_files.append(f'Tọa độ quét làm mờ AI Pixel ({count} câu)')

        # 4. Phụ đề đã biên tập / OCR
        cached_srt = os.path.join(editor_temp_dir, 'editor_subtitles.srt')
        ocr_srt = os.path.join(editor_temp_dir, 'ocr_subtitles.srt')
        if os.path.exists(cached_srt) and os.path.getsize(cached_srt) > 10:
            found_details['cached_srt'] = cached_srt
            if not is_export_check:
                cached_files.append('Phụ đề đã biên tập (editor_subtitles.srt)')
        elif os.path.exists(ocr_srt) and os.path.getsize(ocr_srt) > 10:
            found_details['cached_srt'] = ocr_srt
            if not is_export_check:
                cached_files.append('Phụ đề OCR trích xuất (ocr_subtitles.srt)')

    # Quét thêm file phụ đề .srt tương ứng khớp đúng với tên video (chỉ nạp cho phần biên tập, không đưa vào danh sách cảnh báo xuất video)
    v_dir = os.path.dirname(input_video)
    v_name = os.path.splitext(os.path.basename(input_video))[0]
    for candidate in [
        os.path.join(v_dir, f"{v_name}_vi.srt"),
        os.path.join(v_dir, f"{v_name}_translated.srt"),
        os.path.join(v_dir, f"{v_name}_ocr.srt"),
        os.path.join(v_dir, f"{v_name}.srt"),
        os.path.join(v_dir, f"{v_name}_subtitles.srt"),
        os.path.join(output_dir, f"{v_name}_ocr.srt"),
        os.path.join(output_dir, f"{v_name}.srt")
    ]:
        if os.path.exists(candidate) and os.path.getsize(candidate) > 10:
            name_display = os.path.basename(candidate)
            tag = f'File phụ đề có sẵn ({name_display})'
            found_details['video_srt'] = candidate
            if not is_export_check and tag not in cached_files:
                cached_files.append(tag)
            break

    return jsonify({
        "success": True,
        "has_cache": len(cached_files) > 0,
        "files": cached_files,
        "details": found_details
    })

@video_edit_bp.route('/api/editor/cache_ai_boxes', methods=['GET', 'POST'])
def editor_cache_ai_boxes():
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) if request.method == 'POST' else request.args
    data = data or {}
    input_video = str(data.get('video_path') or data.get('input_video') or '').strip().strip('"\'')
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    editor_temp_dir = get_editor_temp_dir(output_dir, input_video)
    ai_boxes = os.path.join(editor_temp_dir, 'ai_blur_boxes.json')
    if not os.path.exists(ai_boxes) or os.path.getsize(ai_boxes) <= 10:
        return jsonify({'success': False, 'boxes': []})
    try:
        with open(ai_boxes, 'r', encoding='utf-8') as f:
            boxes_data = json.load(f)
        return jsonify({'success': True, 'boxes': boxes_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e), 'boxes': []})

@video_edit_bp.route('/api/editor/clear_cache_boxes', methods=['POST'])
def editor_clear_cache_boxes():
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    input_video = str(data.get('video_path') or data.get('input_video') or '').strip().strip('"\'')
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    editor_temp_dir = get_editor_temp_dir(output_dir, input_video)
    ai_boxes = os.path.join(editor_temp_dir, 'ai_blur_boxes.json')
    if os.path.exists(ai_boxes):
        try:
            os.remove(ai_boxes)
        except Exception:
            pass
    return jsonify({'success': True})

@video_edit_bp.route('/api/editor/save_cache_subtitles', methods=['POST'])
def editor_save_cache_subtitles():
    permission_error = _require_permission('can_access_editor')
    if permission_error:
        return permission_error
    import ocr_module
    data = request.get_json(silent=True) or {}
    input_video = str(data.get('video_path') or data.get('input_video') or '').strip().strip('"\'')
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    subtitles = data.get('subtitles') or []
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    editor_temp_dir = get_editor_temp_dir(output_dir, input_video)
    os.makedirs(editor_temp_dir, exist_ok=True)
    srt_path = os.path.join(editor_temp_dir, 'editor_subtitles.srt')
    try:
        with open(srt_path, 'w', encoding='utf-8') as f:
            for i, sub in enumerate(subtitles, 1):
                t_start = ocr_module.format_time(float(sub.get('startSeconds', 0)))
                t_end = ocr_module.format_time(float(sub.get('endSeconds', 0)))
                txt = sub.get('translation') or sub.get('text') or sub.get('original_text') or ''
                f.write(f"{i}\n{t_start} --> {t_end}\n{txt}\n\n")
        return jsonify({'success': True, 'path': srt_path})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

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
    video_path = str(data.get('video_path') or '').strip().strip(' "\'')
    if not video_path or not os.path.exists(video_path):
        return jsonify({"has_cache": False, "files": []})

    import auto_edit_pipeline
    temp_dir = auto_edit_pipeline.get_review_temp_dir(output_dir, video_path)
    
    if not os.path.exists(temp_dir):
        return jsonify({"has_cache": False, "files": []})
        
    cached_files = []
    cached_script = ""
    script_p = os.path.join(temp_dir, 'script.txt')
    if not os.path.exists(script_p):
        script_p = os.path.join(temp_dir, 'narration_script.txt')
    if os.path.exists(script_p) and os.path.getsize(script_p) > 20:
        cached_files.append('Kịch bản tóm tắt (script.txt)')
        try:
            with open(script_p, 'r', encoding='utf-8') as sf:
                cached_script = sf.read()
        except Exception:
            pass
    if os.path.exists(os.path.join(temp_dir, 'voice_review.wav')) and os.path.getsize(os.path.join(temp_dir, 'voice_review.wav')) > 1000:
        cached_files.append('Giọng đọc AI (voice_review.wav)')
    if os.path.exists(os.path.join(temp_dir, 'voice_review_cleaned.srt')) and os.path.getsize(os.path.join(temp_dir, 'voice_review_cleaned.srt')) > 20:
        cached_files.append('Phụ đề giọng đọc (voice_review_cleaned.srt)')
    if os.path.exists(os.path.join(temp_dir, 'timeline.json')) and os.path.getsize(os.path.join(temp_dir, 'timeline.json')) > 20:
        cached_files.append('Phân đoạn video (timeline.json)')
    if os.path.exists(os.path.join(temp_dir, 'timeline_sanitized.json')) and os.path.getsize(os.path.join(temp_dir, 'timeline_sanitized.json')) > 20:
        cached_files.append('Timeline tối ưu cắt cảnh (timeline_sanitized.json)')
    
    return jsonify({
        "has_cache": len(cached_files) > 0,
        "files": cached_files,
        "cached_script": cached_script
    })

@video_edit_bp.route('/api/review/save_script', methods=['POST'])
def review_save_script():
    permission_error = _require_permission('can_access_review')
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    video_path = str(data.get('video_path') or '').strip()
    output_dir = str(data.get('output_dir') or os.path.join(ROOT_DIR, 'output')).strip()
    script_text = str(data.get('script') or '').strip()
    mode = str(data.get('mode', 'api')).lower()
    
    if not video_path:
        return jsonify({'success': False, 'error': 'Chưa chọn video'}), 400
    if not script_text:
        return jsonify({'success': False, 'error': 'Nội dung kịch bản rỗng'}), 400
        
    import auto_edit_pipeline
    temp_dir = auto_edit_pipeline.get_review_temp_dir(output_dir, video_path)
    os.makedirs(temp_dir, exist_ok=True)
    fname = 'narration_script.txt' if mode == 'narration' else 'script.txt'
    save_path = os.path.join(temp_dir, fname)
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(script_text)
    return jsonify({'success': True, 'path': save_path})

@video_edit_bp.route('/api/bgm/list', methods=['GET'])
def bgm_list():
    preset_dir = os.path.join(ROOT_DIR, 'backgroundmusic')
    custom_dir = os.path.join(USER_DATA_DIR, 'bgm')
    os.makedirs(custom_dir, exist_ok=True)
    
    tracks = []
    # 1. Presets
    if os.path.exists(preset_dir):
        for f in sorted(os.listdir(preset_dir)):
            if f.lower().endswith(('.mp3', '.m4a', '.wav', '.aac')):
                full_path = os.path.join(preset_dir, f)
                base_name = os.path.splitext(f)[0]
                lower_name = f.lower()
                
                # Phân loại phong cách & nhãn an toàn bản quyền
                is_safe = False
                genre = 'Điện ảnh / Thư giãn'
                clean_title = base_name
                
                if 'kevin macleod' in lower_name:
                    is_safe = True
                    # Bỏ tiền tố Kevin MacLeod cho gọn
                    clean_title = base_name.replace('Kevin MacLeod - ', '').strip()
                    if 'sneaky' in lower_name:
                        genre = 'Hài hước / Hóm hỉnh'
                    elif 'monkeys' in lower_name:
                        genre = 'Vui nhộn / TikTok viral'
                    elif 'scheming' in lower_name:
                        genre = 'Mưu mô / Cà khịa'
                    elif 'complex' in lower_name:
                        genre = 'Kịch tính / Hồi hộp'
                    elif 'hitman' in lower_name:
                        genre = 'Hành động / Điệp viên'
                    elif 'volatile' in lower_name:
                        genre = 'Gay cấn / Dồn dập'
                    elif 'heartbreaking' in lower_name:
                        genre = 'Tình cảm / Lắng đọng'
                    elif 'carefree' in lower_name:
                        genre = 'Tươi sáng / Nhẹ nhàng'
                    else:
                        genre = 'Royalty-Free YouTube'
                elif 'blade runner' in lower_name:
                    genre = 'Sci-Fi / Bí ẩn'
                elif 'la lecon' in lower_name:
                    genre = 'Hoài niệm / Sâu lắng'
                elif 'paris' in lower_name:
                    genre = 'Lãng mạn / Êm dịu'
                elif 'reality' in lower_name:
                    genre = 'Cảm xúc / Kịch tính'
                elif 'stay with me' in lower_name:
                    genre = 'Piano nhẹ nhàng'

                display_title = f"🛡️ [No-Copyright] {clean_title}" if is_safe else clean_title

                tracks.append({
                    'id': f'preset_{f}',
                    'name': display_title,
                    'title': display_title,
                    'filename': f,
                    'type': 'preset',
                    'path': full_path,
                    'genre': genre,
                    'is_safe': is_safe,
                    'size_mb': round(os.path.getsize(full_path) / (1024 * 1024), 2)
                })
    # 2. Custom uploads
    if os.path.exists(custom_dir):
        for f in sorted(os.listdir(custom_dir)):
            if f.lower().endswith(('.mp3', '.m4a', '.wav', '.aac')):
                full_path = os.path.join(custom_dir, f)
                tracks.append({
                    'id': f'custom_{f}',
                    'name': os.path.splitext(f)[0],
                    'title': os.path.splitext(f)[0],
                    'filename': f,
                    'type': 'custom',
                    'path': full_path,
                    'genre': 'Tải lên riêng',
                    'is_safe': True,
                    'size_mb': round(os.path.getsize(full_path) / (1024 * 1024), 2)
                })
                
    return jsonify({
        'success': True,
        'status': 'success',
        'tracks': tracks,
        'files': tracks
    })


@video_edit_bp.route('/api/bgm/upload', methods=['POST'])
def bgm_upload():
    if 'audio_file' not in request.files:
        return jsonify({'success': False, 'error': 'Vui lòng chọn file âm thanh'}), 400
    file = request.files['audio_file']
    if not file or not file.filename:
        return jsonify({'success': False, 'error': 'Tên file rỗng'}), 400
        
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in {'.mp3', '.m4a', '.wav', '.aac'}:
        return jsonify({'success': False, 'error': 'Chỉ chấp nhận định dạng .mp3, .m4a, .wav, .aac'}), 400
        
    custom_dir = os.path.join(USER_DATA_DIR, 'bgm')
    os.makedirs(custom_dir, exist_ok=True)
    
    clean_name = secure_filename(file.filename)
    if not clean_name:
        clean_name = f"bgm_{int(time.time())}{ext}"
        
    save_path = safe_join(custom_dir, clean_name, extensions=_AUDIO_EXTENSIONS)
    file.save(save_path)
    
    # Check max size 50MB
    if os.path.getsize(save_path) > 50 * 1024 * 1024:
        os.remove(save_path)
        return jsonify({'success': False, 'error': 'File quá lớn (tối đa 50MB)'}), 400
        
    return jsonify({
        'success': True,
        'track': {
            'id': f'custom_{clean_name}',
            'name': os.path.splitext(clean_name)[0],
            'filename': clean_name,
            'type': 'custom',
            'path': save_path,
            'size_mb': round(os.path.getsize(save_path) / (1024 * 1024), 2)
        }
    })

@video_edit_bp.route('/api/bgm/stream', methods=['GET'])
def bgm_stream():
    path = request.args.get('path', '').strip()
    if not path or not os.path.isabs(path):
        raw_name = request.args.get('filename') or request.args.get('file') or ''
        filename = secure_filename(raw_name)
        track_type = request.args.get('type', '')
        custom_candidate = os.path.join(USER_DATA_DIR, 'bgm', filename) if filename else ''
        preset_candidate = os.path.join(ROOT_DIR, 'backgroundmusic', filename) if filename else ''
        if track_type == 'custom' or (not os.path.exists(preset_candidate) and os.path.exists(custom_candidate)):
            path = custom_candidate
        else:
            path = preset_candidate
            
    if not is_path_allowed(path, must_exist=True, extensions=_AUDIO_EXTENSIONS):
        return jsonify({'error': 'File âm thanh không hợp lệ hoặc không được phép'}), 403
        
    mime, _ = mimetypes.guess_type(path)
    return send_file(path, mimetype=mime or 'audio/mpeg')

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
    # Removed the _review_lock check to fix 409 error
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
        openai_model = data.get('openai_model')
        if not openai_model:
            try:
                from routes.subtitles import _resolve_openai_credentials
                _, _, openai_model = _resolve_openai_credentials()
            except Exception:
                openai_model = 'gpt-5.6-luna-pro-batch'
        srt_path = data.get('srt_path')
        
        # Cập nhật lại vào data để pipeline nhận
        data['openai_model'] = openai_model
        data['openai_base_url'] = openai_base_url
        
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


def sanitize_filter_complex_graph(v_filters, subtitles_enabled=True):
    """
    Loại bỏ triệt để bất kỳ filter burn-in subtitles/ass nào khi subtitles_enabled=False.
    Hỗ trợ cả list các filter hoặc chuỗi filter_complex graph.
    """
    if subtitles_enabled:
        return v_filters
    if isinstance(v_filters, list):
        return [
            f for f in v_filters
            if ('dynamic_blur_mask' in f or 'v_b_mask' in f) or ('subtitles=' not in f and 'ass=' not in f and not f.startswith('[v_sub'))
        ]
    if isinstance(v_filters, str):
        # Tách từng filter block
        blocks = [b.strip() for b in v_filters.split(';') if b.strip()]
        cleaned = [
            b for b in blocks
            if ('dynamic_blur_mask' in b or 'v_b_mask' in b) or ('subtitles=' not in b and 'ass=' not in b and not b.startswith('[v_sub'))
        ]
        return ';'.join(cleaned)
    return v_filters

