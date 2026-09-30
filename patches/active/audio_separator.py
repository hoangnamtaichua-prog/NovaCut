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


def _clean_child_env():
    """Loại bỏ triệt để các biến môi trường PyInstaller để tiến trình con không bị trỏ vào _internal."""
    env = os.environ.copy()
    for var in ["PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "_MEIPASS", "_MEIPASS2"]:
        env.pop(var, None)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _test_python_torch(py_path):
    """Kiểm tra xem executable có thể nạp torch và torchaudio thành công không."""
    if not py_path or not os.path.exists(py_path):
        return False
    try:
        res = subprocess.run(
            [py_path, "-c", "import torch, torchaudio; print('TORCH_OK')"],
            capture_output=True, text=True, timeout=12, env=_clean_child_env(),
            creationflags=0x08000000 if os.name == "nt" else 0
        )
        return "TORCH_OK" in (res.stdout or "")
    except Exception:
        return False


def _has_nvidia_gpu():
    """Kiểm tra máy có GPU NVIDIA khả dụng để tải bản PyTorch CUDA tương ứng."""
    try:
        res = subprocess.run(
            ["nvidia-smi"],
            capture_output=True, text=True, timeout=5,
            creationflags=0x08000000 if os.name == "nt" else 0
        )
        return res.returncode == 0
    except Exception:
        return False


def _find_or_prepare_mdx_python(progress_cb=None, logger_cb=None):
    """
    Tìm hoặc tự động chuẩn bị môi trường Python có sẵn PyTorch (torch + torchaudio).
    Nếu trên máy chưa có bất kỳ môi trường nào hỗ trợ PyTorch:
    Tự động tải và cài đặt phiên bản PyTorch phù hợp (NVIDIA CUDA cu124 hoặc CPU) cho người dùng.
    """
    # 1. Thu thập tất cả các ứng viên Python trên máy
    candidates = []

    # Ưu tiên các runtime chuyên dụng / nội bộ
    runtime_candidates = [
        os.path.join(ROOT_DIR, "runtimes", "vieneu_gpu", "Scripts", "python.exe"),
        os.path.join(ROOT_DIR, ".asr_venv", "Scripts", "python.exe"),
        os.path.join(ROOT_DIR, "runtimes", "mdx_runtime", "Scripts", "python.exe"),
        os.path.join(ROOT_DIR, "runtimes", "python", "python.exe"),
        os.path.join(ROOT_DIR, "rvc_env", "python.exe"),
        os.path.join(ROOT_DIR, "python-nuget", "tools", "python.exe"),
        os.path.join(ROOT_DIR, "python-nuget", "python.exe"),
    ]
    for c in runtime_candidates:
        if os.path.exists(c) and c not in candidates:
            candidates.append(c)

    # Nếu không phải ứng dụng đóng gói EXE, kiểm tra chính sys.executable
    if not getattr(sys, 'frozen', False):
        if sys.executable and sys.executable not in candidates:
            candidates.append(sys.executable)

    # Các Python chuẩn đã cài đặt trên hệ thống Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    prog_files = os.environ.get("ProgramFiles", "")
    if local_app_data:
        for py_ver in ["Python312", "Python311", "Python310"]:
            p = os.path.join(local_app_data, "Programs", "Python", py_ver, "python.exe")
            if os.path.exists(p) and p not in candidates:
                candidates.append(p)
    if prog_files:
        for py_ver in ["Python312", "Python311", "Python310"]:
            p = os.path.join(prog_files, py_ver, "python.exe")
            if os.path.exists(p) and p not in candidates:
                candidates.append(p)

    # Thử py launcher hoặc python trong biến môi trường PATH
    for cmd in ["python.exe", "python"]:
        found = shutil.which(cmd)
        if found and os.path.exists(found) and "WindowsApps" not in found and found not in candidates:
            candidates.append(found)

    # 2. Kiểm tra xem ứng viên nào đã có sẵn torch & torchaudio
    for py_exe in candidates:
        if _test_python_torch(py_exe):
            if logger_cb:
                logger_cb(f"[MDX-Separator] 🎯 Sử dụng môi trường AI sẵn có: {py_exe}")
            return py_exe

    # 3. Nếu chưa có môi trường nào có torch: TỰ ĐỘNG TẢI & CÀI ĐẶT CHO NGƯỜI DÙNG
    if logger_cb:
        logger_cb("[MDX-Separator] ⚙️ Chưa tìm thấy thư viện AI PyTorch. Đang chuẩn bị môi trường tự động cài đặt...")
    if progress_cb:
        progress_cb(5, "Đang chuẩn bị môi trường AI PyTorch...")

    # Tìm Python cơ sở để tạo runtime hoặc cài đặt
    base_python = None
    for py_exe in candidates:
        if os.path.exists(py_exe) and not py_exe.endswith("NovaCut.exe"):
            base_python = py_exe
            break

    if not base_python:
        for cmd in ["python.exe", "python", "py.exe", "py"]:
            found = shutil.which(cmd)
            if found and os.path.exists(found) and not found.endswith("NovaCut.exe"):
                base_python = found
                break

    if not base_python:
        raise RuntimeError("Không tìm thấy Python trên hệ thống để cài đặt PyTorch. Vui lòng cài đặt Python (3.10 - 3.12).")

    # Tạo virtualenv riêng biệt tại runtimes/mdx_runtime để tránh xung đột
    mdx_runtime_dir = os.path.join(ROOT_DIR, "runtimes", "mdx_runtime")
    target_python = os.path.join(mdx_runtime_dir, "Scripts", "python.exe")

    if not os.path.exists(target_python):
        if logger_cb:
            logger_cb("[MDX-Separator] 📦 Đang khởi tạo môi trường AI tách biệt tại runtimes/mdx_runtime...")
        os.makedirs(os.path.dirname(mdx_runtime_dir), exist_ok=True)
        try:
            subprocess.run(
                [base_python, "-m", "venv", mdx_runtime_dir],
                capture_output=True, text=True, timeout=60, env=_clean_child_env(),
                creationflags=0x08000000 if os.name == "nt" else 0
            )
        except Exception as venv_err:
            if logger_cb:
                logger_cb(f"[MDX-Separator] ⚠️ Không thể tạo venv ({venv_err}). Sử dụng trực tiếp {base_python}")
            target_python = base_python

    if not os.path.exists(target_python):
        target_python = base_python

    # Xác định phiên bản CUDA / CPU phù hợp
    has_gpu = _has_nvidia_gpu()
    if has_gpu:
        index_url = "https://download.pytorch.org/whl/cu124"
        hardware_label = "NVIDIA GPU (CUDA cu124)"
    else:
        index_url = "https://download.pytorch.org/whl/cpu"
        hardware_label = "CPU Fallback"

    if logger_cb:
        logger_cb(f"[MDX-Separator] 🚀 Bắt đầu tự động tải PyTorch & Torchaudio cho {hardware_label} (Chỉ tải 1 lần duy nhất)...")
    if progress_cb:
        progress_cb(6, f"Đang tải PyTorch ({hardware_label})...")

    pip_cmd = [
        target_python, "-m", "pip", "install",
        "--no-warn-script-location",
        "torch", "torchaudio", "onnxruntime-directml", "numpy", "soundfile",
        "--index-url", index_url
    ]

    install_proc = subprocess.Popen(
        pip_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=_clean_child_env(),
        creationflags=0x08000000 if os.name == "nt" else 0
    )

    while True:
        line = install_proc.stdout.readline()
        if not line:
            if install_proc.poll() is not None:
                break
            time.sleep(0.1)
            continue
        line_clean = line.strip()
        if not line_clean:
            continue
        if any(keyword in line_clean.lower() for keyword in ["downloading", "collecting", "installing", "successfully installed"]):
            if logger_cb:
                logger_cb(f"[PyTorch-Installer] {line_clean}")
            if "downloading" in line_clean.lower() and progress_cb:
                progress_cb(7, "Đang tải gói dữ liệu AI...")

    ret = install_proc.wait()
    if ret != 0:
        raise RuntimeError(f"Tự động cài đặt PyTorch thất bại (Mã lỗi: {ret}). Vui lòng kiểm tra kết nối mạng.")

    if _test_python_torch(target_python):
        if logger_cb:
            logger_cb("[MDX-Separator] 🎉 Đã cài đặt hoàn tất PyTorch AI thành công! Bắt đầu xử lý âm thanh...")
        return target_python
    else:
        raise RuntimeError("Cài đặt PyTorch hoàn tất nhưng không thể nạp module torch/torchaudio.")


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

    python_exe = _find_or_prepare_mdx_python(progress_cb=progress_cb, logger_cb=logger_cb)
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

    env = _clean_child_env()

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
            if getattr(sys, 'frozen', False):
                raise proc_err
            # Nếu chạy từ source/dev mà subprocess gặp sự cố, thử in-process fallback
            if logger_cb:
                logger_cb(f"[MDX-Separator] ⚠️ Subprocess worker gặp sự cố ({proc_err}). Thử chạy in-process...")
            try:
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
            except Exception as in_proc_err:
                raise RuntimeError(f"Tách âm thanh thất bại: {proc_err}")

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
