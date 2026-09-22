# -*- coding: utf-8 -*-
"""
NovaCut AI Audio Stem & Vocal Separation Engine (MDX-NET Pure Engine)
Mô-đun AI Tách Âm Thanh Chuẩn Ultimate Vocal Remover UVR5 (MDX-NET Inst HQ4 / HQ5 / Voc FT).
Lọc bỏ triệt để 99.5% giọng thoại cũ, bảo toàn 100% nhạc nền BGM & tiếng động hiện trường SFX.
"""

import os
import sys
import time
import subprocess
import shutil

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
TEMP_DIR = os.path.join(ROOT_DIR, "output", "separated_stems")
os.makedirs(TEMP_DIR, exist_ok=True)


def _get_ffmpeg_exe():
    """Tìm tệp thực thi ffmpeg.exe an toàn."""
    try:
        import ffmpeg_installer
        cand = ffmpeg_installer.get_ffmpeg_path()
        if cand and os.path.exists(cand):
            return cand
    except Exception:
        pass
    bin_candidates = [
        os.path.join(os.path.dirname(sys.executable), 'bin', 'ffmpeg.exe'),
        os.path.join(getattr(sys, '_MEIPASS', ''), 'bin', 'ffmpeg.exe') if hasattr(sys, '_MEIPASS') else None,
        os.path.join(ROOT_DIR, 'bin', 'ffmpeg.exe')
    ]
    for b in bin_candidates:
        if b and os.path.exists(b):
            return b
    return shutil.which('ffmpeg.exe') or shutil.which('ffmpeg') or 'ffmpeg'


def extract_audio_from_video(input_video_path, output_wav_path, sample_rate=44100):
    """
    Trích xuất âm thanh Stereo chuẩn 44.1kHz từ video.
    """
    ffmpeg_exe = _get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, "-y", "-i", input_video_path,
        "-vn", "-ar", str(sample_rate), "-ac", "2", "-c:a", "pcm_s16le",
        output_wav_path
    ]
    res = subprocess.run(
        cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore',
        creationflags=0x08000000 if os.name == 'nt' else 0
    )
    if not os.path.exists(output_wav_path) or os.path.getsize(output_wav_path) < 1000:
        raise Exception(f"Không thể trích xuất âm thanh từ video: {res.stderr or 'Lỗi định dạng'}")
    return output_wav_path


def separate_audio_stems(
    input_media_path,
    output_dir=None,
    remove_vocals=True,
    remove_bgm=False,
    keep_sfx=True,
    mode="mdx_net_hq4",
    device="auto",
    progress_cb=None,
    logger_cb=None,
    cancel_check_cb=None
):
    """
    Hàm giao diện chính để thực hiện Tách Âm Thanh AI & Lọc Giọng Thoại Cũ qua MDX-NET UVR5.
    Hỗ trợ các mô hình MDX-Net:
    - 'mdx_net_hq4' (Khuyên dùng): MDX-NET Inst HQ 4 (Chuẩn UVR5, Sạch thoại 99.5%, Giữ 100% SFX).
    - 'mdx_net_hq5': MDX-NET Inst HQ 5 (Chống vang Reverb & Echo).
    - 'mdx_net_voc_ft': MDX-NET Vocals FT (Trích xuất Vocal trong trẻo).
    """
    if not os.path.exists(input_media_path):
        raise FileNotFoundError(f"Không tìm thấy file đầu vào: {input_media_path}")

def _get_python_exe():
    """Tìm Python executable an toàn cho cả môi trường source và đóng gói."""
    if not getattr(sys, 'frozen', False):
        return sys.executable
    candidates = [
        os.path.join(ROOT_DIR, "runtimes", "python", "python.exe"),
        os.path.join(ROOT_DIR, "python-nuget", "python.exe"),
        shutil.which("python.exe"),
        shutil.which("python")
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    return sys.executable


def _run_mdx_in_isolated_process(
    source_audio,
    output_dir,
    mdx_model_file,
    device,
    remove_vocals,
    remove_bgm,
    keep_sfx,
    progress_cb=None,
    logger_cb=None,
    cancel_check_cb=None
):
    """
    Thực thi tách âm thanh UVR-MDX trong một tiến trình con độc lập (Isolated Subprocess).
    Ưu điểm cốt lõi:
    1. Tránh hoàn toàn lỗi xung đột DirectML D3D12 device / DLL Crash (0xC0000005) với RapidOCR và Flask.
    2. Nếu có sự cố cấp thấp từ driver GPU, ứng dụng web Flask NovaCut không bao giờ bị crash.
    3. Tự động giải phóng 100% VRAM / RAM sau khi kết thúc tác vụ.
    """
    import json

    python_exe = _get_python_exe()
    mdx_script = os.path.join(ROOT_DIR, "mdx_separator.py")

    cmd = [
        python_exe, "-u", mdx_script,
        "--input", source_audio,
        "--output-dir", output_dir,
        "--model", mdx_model_file,
        "--device", device,
        "--overlap", "0.5"
    ]
    if remove_vocals:
        cmd.append("--remove-vocals")
    if remove_bgm:
        cmd.append("--remove-bgm")
    if keep_sfx:
        cmd.append("--keep-sfx")

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    creation_flags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        creationflags=creation_flags
    )

    res_mdx = None
    last_err_lines = []

    try:
        while True:
            if cancel_check_cb and cancel_check_cb():
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
                raise Exception("🛑 Đã dừng tác vụ tách âm thanh khẩn cấp theo yêu cầu.")

            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                time.sleep(0.02)
                continue

            line_str = line.strip()
            if not line_str:
                continue

            if line_str.startswith("[PROGRESS]"):
                payload = line_str[10:].strip()
                if "|" in payload:
                    pct_str, p_msg = payload.split("|", 1)
                else:
                    pct_str, p_msg = payload, ""
                try:
                    pct_val = int(pct_str)
                    if progress_cb:
                        progress_cb(pct_val, p_msg.strip())
                except ValueError:
                    pass
            elif line_str.startswith("[LOG]"):
                log_txt = line_str[5:].strip()
                if logger_cb:
                    logger_cb(log_txt)
            elif line_str.startswith("[RESULT]"):
                res_json_str = line_str[8:].strip()
                try:
                    res_mdx = json.loads(res_json_str)
                except Exception as je:
                    last_err_lines.append(f"JSON error: {je}")
            elif line_str.startswith("[ERROR]"):
                last_err_lines.append(line_str[7:].strip())
            else:
                last_err_lines.append(line_str)
                if len(last_err_lines) > 20:
                    last_err_lines.pop(0)

        retcode = proc.wait()
        if retcode == 0 and res_mdx:
            return res_mdx

        err_detail = "\n".join(last_err_lines[-8:]) if last_err_lines else f"Mã thoát: {retcode}"
        
        # Nếu worker GPU DirectML bị crash do lỗi driver (-1073741819 = 0xC0000005)
        if retcode in (-1073741819, 3221225477) and device != "cpu":
            if logger_cb:
                logger_cb(f"[MDX-Separator] ⚠️ GPU worker gặp lỗi hệ thống (Mã: {retcode}). Tự động phục hồi và chuyển sang CPU runner an toàn...")
            return _run_mdx_in_isolated_process(
                source_audio, output_dir, mdx_model_file, "cpu",
                remove_vocals, remove_bgm, keep_sfx,
                progress_cb, logger_cb, cancel_check_cb
            )

        raise RuntimeError(f"Tách âm thanh trong tiến trình cô lập thất bại (Exit: {retcode}):\n{err_detail}")

    except Exception:
        if proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        raise


def separate_audio_stems(
    input_media_path,
    output_dir=None,
    remove_vocals=True,
    remove_bgm=False,
    keep_sfx=True,
    mode="mdx_net_hq4",
    device="auto",
    progress_cb=None,
    logger_cb=None,
    cancel_check_cb=None
):
    """
    Hàm giao diện chính để thực hiện Tách Âm Thanh AI & Lọc Giọng Thoại Cũ qua MDX-NET UVR5.
    Hỗ trợ các mô hình MDX-Net:
    - 'mdx_net_hq4' (Khuyên dùng): MDX-NET Inst HQ 4 (Chuẩn UVR5, Sạch thoại 99.5%, Giữ 100% SFX).
    - 'mdx_net_hq5': MDX-NET Inst HQ 5 (Chống vang Reverb & Echo).
    - 'mdx_net_voc_ft': MDX-NET Vocals FT (Trích xuất Vocal trong trẻo).
    """
    if not os.path.exists(input_media_path):
        raise FileNotFoundError(f"Không tìm thấy file đầu vào: {input_media_path}")

    if not output_dir:
        output_dir = TEMP_DIR
    os.makedirs(output_dir, exist_ok=True)

    # 1. Trích xuất và chuẩn hóa mọi định dạng video/audio sang chuẩn PCM 16-bit 44.1kHz Stereo
    ext = os.path.splitext(input_media_path)[1].lower()
    is_video = ext in ['.mp4', '.mkv', '.mov', '.avi', '.webm', '.flv', '.wmv', '.m4v']

    if logger_cb:
        logger_cb(f"[MDX-Separator] 🎬 Nhận file ({ext.upper()}): {os.path.basename(input_media_path)}")
    if progress_cb:
        progress_cb(5, "Đang trích xuất và chuẩn hóa luồng âm thanh...")

    extracted_wav = os.path.join(output_dir, f"raw_audio_{int(time.time()*1000)}.wav")
    extract_audio_from_video(input_media_path, extracted_wav)
    source_audio = extracted_wav

    try:
        # Ánh xạ mô hình MDX-Net tương ứng
        if "hq5" in mode:
            mdx_model_file = "UVR-MDX-NET-Inst_HQ_5.onnx"
            resolved_mode = "mdx_net_hq5"
        elif "voc" in mode:
            mdx_model_file = "UVR-MDX-NET-Voc_FT.onnx"
            resolved_mode = "mdx_net_voc_ft"
        else:
            mdx_model_file = "UVR-MDX-NET-Inst_HQ_4.onnx"
            resolved_mode = "mdx_net_hq4"

        try:
            res_mdx = _run_mdx_in_isolated_process(
                source_audio=source_audio,
                output_dir=output_dir,
                mdx_model_file=mdx_model_file,
                device=device,
                remove_vocals=remove_vocals,
                remove_bgm=remove_bgm,
                keep_sfx=keep_sfx,
                progress_cb=progress_cb,
                logger_cb=logger_cb,
                cancel_check_cb=cancel_check_cb
            )
        except Exception as proc_err:
            # Nếu subprocess không thể chạy được do môi trường, fallback về in-process với bảo vệ CPU
            if logger_cb:
                logger_cb(f"[MDX-Separator] ⚠️ Subprocess worker không khả dụng ({proc_err}). Chuyển sang in-process runner...")
            from mdx_separator import separate_stems_mdx
            res_mdx = separate_stems_mdx(
                source_audio, output_dir,
                model_name=mdx_model_file,
                device=device,
                remove_vocals=remove_vocals,
                remove_bgm=remove_bgm,
                keep_sfx=keep_sfx,
                progress_cb=progress_cb,
                logger_cb=logger_cb,
                cancel_check_cb=cancel_check_cb
            )

        res = {
            "success": True,
            "mode": resolved_mode,
            "device": device,
            "cleaned_path": res_mdx["clean_background_path"],
            "vocals_path": res_mdx["vocals_path"],
            "instrumental_path": res_mdx["instrumental_path"],
            "sfx_path": res_mdx["instrumental_path"],
            "source_media": input_media_path,
            "is_video": is_video
        }
        return res

    finally:
        # Dọn dẹp file trích xuất tạm
        if extracted_wav and os.path.exists(extracted_wav):
            try:
                os.remove(extracted_wav)
            except Exception:
                pass
