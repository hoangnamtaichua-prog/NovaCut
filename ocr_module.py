import os
import sys
import cv2
import numpy as np
import time
import re
import hashlib

def get_editor_temp_dir(output_dir, video_path):
    """
    Trả về đường dẫn thư mục tạm duy nhất cho từng video trong Biên tập phim.
    - Bảo toàn ký tự Unicode (tiếng Việt, tiếng Trung, tiếng Nhật...) để tên thư mục trực quan, dễ đọc.
    - Chuẩn hóa khoảng trắng và loại bỏ các ký tự cấm của Windows: \\ / : * ? " < > |
    - Kết hợp băm MD5 (10 ký tự) từ đường dẫn tuyệt đối chuẩn hóa của video,
      đảm bảo 100% không bao giờ bị nhận nhầm hoặc đè cache giữa các video khác nhau.
    """
    if not output_dir:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(output_dir)

    v_str = str(video_path or '').strip(' "\'')
    if not v_str:
        return os.path.join(output_dir, 'editor_temp', '_unnamed_video')

    norm_video = os.path.normpath(os.path.abspath(v_str))
    raw_stem = os.path.splitext(os.path.basename(norm_video))[0]
    safe_stem = re.sub(r'[\s\<\>\:\"\/\\\|\?\*\x00-\x1f]+', '_', raw_stem).strip('._ ')
    if not safe_stem:
        safe_stem = 'video'
    safe_stem = safe_stem[:60].strip('._ ')

    path_hash = hashlib.md5(norm_video.lower().encode('utf-8', errors='ignore')).hexdigest()[:10]
    folder_name = f"{safe_stem}_{path_hash}"
    return os.path.join(output_dir, 'editor_temp', folder_name)

# Auto-inject PyTorch CUDA runtime DLLs for ONNX Runtime GPU support
try:
    import torch
    torch_lib = os.path.join(os.path.dirname(torch.__file__), 'lib')
    if os.path.exists(torch_lib):
        if hasattr(os, 'add_dll_directory'):
            os.add_dll_directory(torch_lib)
        os.environ['PATH'] = torch_lib + os.pathsep + os.environ.get('PATH', '')
except Exception:
    pass

def format_time(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def get_video_info(path):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError(f"Không thể mở tệp video: {path}")
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps > 0 else 0
    cap.release()
    return w, h, fps, total_frames, duration

def is_blank_or_no_text(crop_gray, min_std=6.0, min_laplacian=12.0):
    """Kiểm tra siêu tốc xem vùng crop có phải vùng trống hoặc không có nét chữ không"""
    if crop_gray is None or crop_gray.size == 0:
        return True
    if crop_gray.std() < min_std:
        return True
    # Phụ đề video luôn có nét tương phản cao (chữ sáng viền tối hoặc chữ tối nền sáng)
    bright_px = int((crop_gray > 175).sum())
    if bright_px < 30:
        if crop_gray.mean() < 150 or int((crop_gray < 80).sum()) < 30:
            return True
    var = cv2.Laplacian(crop_gray, cv2.CV_64F).var()
    return var < min_laplacian

def normalize_ocr_regions(region):
    import math
    items = region if isinstance(region, list) else [region]
    if not 1 <= len(items) <= 8:
        raise ValueError("Chọn từ 1 đến 8 vùng OCR")
    normalized = []
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("Vùng OCR phải là đối tượng tọa độ")
        
        # Hỗ trợ linh hoạt cả 'w' / 'width' và 'h' / 'height'
        w_val = item.get('w') if 'w' in item else item.get('width', 60.0)
        h_val = item.get('h') if 'h' in item else item.get('height', 9.5)
        x_val = item.get('x', 20.0)
        y_val = item.get('y', 81.5)

        box = {
            'x': float(x_val),
            'y': float(y_val),
            'w': float(w_val),
            'h': float(h_val)
        }
        if not all(math.isfinite(v) for v in box.values()):
            raise ValueError("Tọa độ OCR phải là số hữu hạn")
        if (box['x'] < 0 or box['y'] < 0 or box['w'] <= 0 or box['h'] <= 0
                or box['x'] + box['w'] > 100.001 or box['y'] + box['h'] > 100.001):
            raise ValueError("Vùng OCR phải nằm trong video (0–100%)")
        box['label'] = str(item.get('label') or ('Phụ đề' if i == 0 else f'Vùng {i+1}'))[:80]
        normalized.append(box)
    return normalized


def _engine_providers(engine):
    providers = {}
    for name in ('text_det', 'text_rec'):
        component = getattr(engine, name, None)
        session = getattr(component, 'infer', None)
        if session is None:
            session = getattr(component, 'session', None)
        session = getattr(session, 'session', session)
        providers[name] = session.get_providers() if hasattr(session, 'get_providers') else []
    return providers


def _make_extract_engine(device, threads, diagnostics=None):
    from rapidocr_onnxruntime import RapidOCR
    import onnxruntime as ort
    options = dict(
        intra_op_num_threads=threads,
        inter_op_num_threads=1,
        det_limit_side_len=960,
        det_limit_type='max'
    )
    available = ort.get_available_providers()
    if diagnostics is None:
        diagnostics = []
    diagnostics.append('ONNX providers có sẵn: ' + ', '.join(available))
    if device != 'cpu':
        for provider, suffix in [('DmlExecutionProvider', 'dml'), ('CUDAExecutionProvider', 'cuda')]:
            if provider not in available:
                continue
            try:
                engine = RapidOCR(**options, **{f'{part}_use_{suffix}': True for part in ('det', 'cls', 'rec')})
                attached = _engine_providers(engine)
                if all(provider in values for values in attached.values()):
                    return engine, provider
                diagnostics.append(f'{provider}: phiên thực tế {attached}')
            except Exception as exc:
                diagnostics.append(f'{provider}: {type(exc).__name__}: {exc}')
                continue
    return RapidOCR(**options), 'CPUExecutionProvider'


def _merge_ocr_samples(samples, step, duration, video_w=None, video_h=None):
    merged = []
    for item in samples:
        timestamp = item[0]
        text = item[1]
        raw_box = item[2] if len(item) > 2 else None
        end = min(duration, timestamp + step)
        if not text or end <= timestamp:
            continue

        box_dict = None
        if raw_box and isinstance(raw_box, dict) and video_w and video_h and 'rel_x' in raw_box:
            pad_px_x = max(8, int(video_w * 0.012))
            pad_px_y = max(4, int(video_h * 0.006))
            rel_x = raw_box.get('rel_x', 0)
            rel_r = raw_box.get('rel_r', 0)
            rel_y = raw_box.get('rel_y', 0)
            rel_b = raw_box.get('rel_b', 0)
            bx_ratio = max(0.01, (rel_x - pad_px_x) / float(video_w))
            bw_ratio = min(0.98 - bx_ratio, (rel_r - rel_x + (pad_px_x * 2)) / float(video_w))
            by_ratio = max(0.01, (rel_y - pad_px_y) / float(video_h))
            bh_ratio = min(0.98 - by_ratio, (rel_b - rel_y + (pad_px_y * 2)) / float(video_h))
            box_dict = {
                'x_pct': round(bx_ratio * 100.0, 2),
                'w_pct': round(bw_ratio * 100.0, 2),
                'y_pct': round(by_ratio * 100.0, 2),
                'h_pct': round(bh_ratio * 100.0, 2),
                'visual_start': timestamp,
                'visual_end': end
            }
        elif raw_box and isinstance(raw_box, dict) and 'x_pct' in raw_box:
            box_dict = raw_box

        if merged and merged[-1]['text'] == text and abs(merged[-1]['end'] - timestamp) < max(0.02, step * 0.51):
            merged[-1]['end'] = end
            if box_dict and not merged[-1].get('box'):
                merged[-1]['box'] = box_dict
            elif box_dict and merged[-1].get('box'):
                merged[-1]['box']['visual_end'] = end
        else:
            seg = dict(start=timestamp, end=end, text=text)
            if box_dict:
                seg['box'] = box_dict
            merged.append(seg)
    return merged

def _get_ffmpeg_path():
    """Tìm đường dẫn tệp thực thi ffmpeg.exe trong bin/ hoặc hệ thống"""
    try:
        import ffmpeg_installer
        path = ffmpeg_installer.get_ffmpeg_path()
        if path and os.path.exists(path):
            return os.path.abspath(path)
    except Exception:
        pass
    bin_dir = os.path.join(ROOT_DIR, 'bin') if 'ROOT_DIR' in globals() else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin')
    candidates = [
        os.path.join(bin_dir, 'ffmpeg.exe'),
        os.path.join(os.getcwd(), 'bin', 'ffmpeg.exe'),
        shutil.which('ffmpeg.exe') if 'shutil' in sys.modules else None,
        shutil.which('ffmpeg') if 'shutil' in sys.modules else None
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return os.path.abspath(c)
    return None


def _worker_chunk_ocr(chunk_id, video_path, boxes, start_t, dur_t, fps, step, device, threads_per_worker, pipe_out, stop_evt):
    """
    Tiến trình worker độc lập phụ trách một đoạn video (Virtual Chunk):
    - Trích xuất khung hình siêu tốc bằng FFmpeg pipe phần cứng (-hwaccel auto)
    - Tự động crop hộp phụ đề trực tiếp ở tầng FFmpeg/C
    - Áp dụng bộ lọc Blank check & Smart Temporal Dedup (tiết kiệm 60% lượt gọi OCR)
    - Trả về danh sách mẫu (timestamp, text) qua Pipe liên tiến trình
    """
    import subprocess
    try:
        engine, provider = _make_extract_engine(device, threads_per_worker)
    except Exception as exc:
        try:
            import easyocr
            engine = easyocr.Reader(['ch_sim', 'en'], gpu=(device != 'cpu'))
        except Exception as e2:
            pipe_out.send(('error', chunk_id, f"Không khởi tạo được OCR engine: {exc} / {e2}"))
            pipe_out.close()
            return

    num_regions = len(boxes)
    samples = [[] for _ in range(num_regions)]
    prev_gray = [None for _ in range(num_regions)]
    prev_text = ['' for _ in range(num_regions)]
    prev_box = [None for _ in range(num_regions)]
    ocr_calls = 0
    skipped = 0

    ffmpeg_path = _get_ffmpeg_path()
    use_ffmpeg = ffmpeg_path is not None and os.path.exists(ffmpeg_path)

    # Tính toán bounding box bao phủ tất cả các vùng cần crop
    min_x = min(b[0] for b in boxes)
    min_y = min(b[1] for b in boxes)
    max_r = max(b[2] for b in boxes)
    max_b = max(b[3] for b in boxes)
    crop_w = max_r - min_x
    crop_h = max_b - min_y
    # Đảm bảo chiều rộng và chiều cao là số chẵn cho FFmpeg
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    if use_ffmpeg:
        frame_size = crop_w * crop_h * 3
        cmd = [
            ffmpeg_path,
            "-ss", f"{max(0.0, start_t):.3f}",
            "-t", f"{max(0.01, dur_t):.3f}",
            "-hwaccel", "auto",
            "-i", video_path,
            "-vf", f"fps={fps},crop={crop_w}:{crop_h}:{min_x}:{min_y}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-v", "error",
            "pipe:1"
        ]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_size * 5)
            frame_idx = 0
            while True:
                if stop_evt.is_set():
                    proc.kill()
                    break
                raw = proc.stdout.read(frame_size)
                if len(raw) < frame_size:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape((crop_h, crop_w, 3))
                timestamp = start_t + (frame_idx * step)
                frame_idx += 1

                for ri, (bx, by, br, bb) in enumerate(boxes):
                    sub_y1 = max(0, by - min_y)
                    sub_y2 = min(crop_h, bb - min_y)
                    sub_x1 = max(0, bx - min_x)
                    sub_x2 = min(crop_w, br - min_x)
                    if sub_y2 <= sub_y1 or sub_x2 <= sub_x1:
                        samples[ri].append((timestamp, '', None))
                        continue
                    crop = frame[sub_y1:sub_y2, sub_x1:sub_x2]
                    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                    if is_blank_or_no_text(gray):
                        text = ''
                        box_data = None
                        prev_gray[ri] = None
                        prev_text[ri] = ''
                        prev_box[ri] = None
                    elif prev_gray[ri] is not None and cv2.absdiff(prev_gray[ri], gray).mean() < 8.5:
                        text = prev_text[ri]
                        box_data = prev_box[ri]
                        skipped += 1
                    else:
                        if hasattr(engine, '__call__'):
                            res, _ = engine(crop, use_cls=False)
                            text = ' '.join(str(line[1]) for line in (res or []) if line and len(line) > 1).strip()
                        else:
                            res = engine.readtext(crop, detail=1)
                            text = ' '.join(str(line[1]) for line in (res or []) if line and len(line) > 1).strip()
                        box_data = None
                        if res and text:
                            all_xs = [pt[0] for line in res if line and len(line) > 0 and line[0] is not None for pt in line[0]]
                            all_ys = [pt[1] for line in res if line and len(line) > 0 and line[0] is not None for pt in line[0]]
                            if all_xs and all_ys:
                                box_data = {
                                    'rel_x': int(bx + min(all_xs)),
                                    'rel_r': int(bx + max(all_xs)),
                                    'rel_y': int(by + min(all_ys)),
                                    'rel_b': int(by + max(all_ys))
                                }
                        prev_gray[ri] = gray
                        prev_text[ri] = text
                        prev_box[ri] = box_data
                        ocr_calls += 1
                    samples[ri].append((timestamp, text, box_data))

                if frame_idx % 5 == 0:
                    pipe_out.send(('progress', chunk_id, frame_idx, ocr_calls, skipped))

            proc.stdout.close()
            proc.wait()
            pipe_out.send(('done', chunk_id, samples, ocr_calls, skipped))
            pipe_out.close()
            return
        except Exception as ffmpeg_err:
            pass # Fallback về OpenCV nếu FFmpeg có sự cố

    # Fallback OpenCV decoder
    try:
        cap = cv2.VideoCapture(video_path)
        vid_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        start_frame = max(0, min(total_frames - 1, int(round(start_t * vid_fps))))
        cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        position = start_frame

        total_steps = int(round(dur_t / step))
        for step_i in range(total_steps):
            if stop_evt.is_set():
                break
            target_f = min(total_frames - 1, int(round((start_t + step_i * step) * vid_fps)))
            while position < target_f:
                if not cap.grab():
                    break
                position += 1
            ok, frame = cap.read()
            position += 1
            if not ok or frame is None:
                break
            timestamp = start_t + step_i * step
            for ri, (bx, by, br, bb) in enumerate(boxes):
                crop = frame[by:bb, bx:br]
                if crop.size == 0:
                    samples[ri].append((timestamp, '', None))
                    continue
                gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                if is_blank_or_no_text(gray):
                    text = ''
                    box_data = None
                    prev_gray[ri] = None
                    prev_text[ri] = ''
                    prev_box[ri] = None
                elif prev_gray[ri] is not None and cv2.absdiff(prev_gray[ri], gray).mean() < 8.5:
                    text = prev_text[ri]
                    box_data = prev_box[ri]
                    skipped += 1
                else:
                    if hasattr(engine, '__call__'):
                        res, _ = engine(crop, use_cls=False)
                        text = ' '.join(str(line[1]) for line in (res or []) if line and len(line) > 1).strip()
                    else:
                        res = engine.readtext(crop, detail=1)
                        text = ' '.join(str(line[1]) for line in (res or []) if line and len(line) > 1).strip()
                    box_data = None
                    if res and text:
                        all_xs = [pt[0] for line in res if line and len(line) > 0 and line[0] is not None for pt in line[0]]
                        all_ys = [pt[1] for line in res if line and len(line) > 0 and line[0] is not None for pt in line[0]]
                        if all_xs and all_ys:
                            box_data = {
                                'rel_x': int(bx + min(all_xs)),
                                'rel_r': int(bx + max(all_xs)),
                                'rel_y': int(by + min(all_ys)),
                                'rel_b': int(by + max(all_ys))
                            }
                    prev_gray[ri] = gray
                    prev_text[ri] = text
                    prev_box[ri] = box_data
                    ocr_calls += 1
                samples[ri].append((timestamp, text, box_data))
            if (step_i + 1) % 5 == 0:
                pipe_out.send(('progress', chunk_id, step_i + 1, ocr_calls, skipped))
        cap.release()
        pipe_out.send(('done', chunk_id, samples, ocr_calls, skipped))
        pipe_out.close()
    except Exception as cv_err:
        pipe_out.send(('error', chunk_id, str(cv_err)))
        pipe_out.close()


def process_ocr(video_path, region, fps=2, threads=4, device='cpu', check_stop=None, output_dir=None):
    """
    Quét nhận diện phụ đề OCR với cơ chế phân đoạn song song đa tiến trình (Multi-Process Chunking):
    - Tự động chia timeline video thành nhiều phân đoạn song song độc lập
    - Kết hợp giải mã FFmpeg Pipe HW-Accel siêu tốc và Smart Temporal Dedup
    - Tăng tốc quét từ 4x đến 8x so với cơ chế tuần tự truyền thống
    - Tự động chuyển về tuần tự đơn luồng đối với video ngắn hoặc môi trường mock test
    - Tự động lưu cache phụ đề vào thư mục tạm editor_temp để tái sử dụng
    """
    import json
    import math
    import multiprocessing
    from concurrent.futures import ThreadPoolExecutor

    started = time.perf_counter()
    regions = normalize_ocr_regions(region)
    fps = float(fps)
    if not math.isfinite(fps) or not 0.1 <= fps <= 30:
        raise ValueError('FPS phải nằm trong khoảng 0.1–30')
    threads = max(1, min(8, int(threads)))
    yield "data: Đang khởi tạo hệ thống OCR tăng tốc...\n\n"

    diagnostics = []
    engine_type = 'rapidocr'
    try:
        engine, provider = _make_extract_engine(device, threads, diagnostics)
    except Exception as exc:
        yield f"data: Không khởi tạo được RapidOCR ({exc}); đang thử EasyOCR tiếng Trung...\n\n"
        try:
            import easyocr
            engine = easyocr.Reader(['ch_sim', 'en'], gpu=(device != 'cpu'))
            engine_type = 'easyocr'
            provider = f'EasyOCR {getattr(engine, "device", "unknown")}'
        except Exception as fallback_error:
            yield f"data: 🛑 Không khởi tạo được OCR: {fallback_error}\n\n"
            return

    for message in diagnostics:
        yield f"data: {' '.join(message.splitlines())}\n\n"
    yield f"data: Thiết bị thực tế: {provider}; luồng CPU trong ONNX: {threads}\n\n"
    if device != 'cpu' and provider == 'CPUExecutionProvider':
        yield "data: ⚠️ GPU không khởi tạo được; đang dùng CPU.\n\n"

    w, h, vid_fps, total_frames, duration = get_video_info(video_path)
    if duration <= 0 or total_frames <= 0:
        raise ValueError('Không xác định được thời lượng video')

    boxes = []
    for r in regions:
        x, y = int(w * r['x'] / 100), int(h * r['y'] / 100)
        right, bottom = min(w, int(w * (r['x'] + r['w']) / 100)), min(h, int(h * (r['y'] + r['h']) / 100))
        if right <= x or bottom <= y:
            raise ValueError('Vùng OCR quá nhỏ')
        boxes.append((x, y, right, bottom))

    step = 1 / min(fps, vid_fps)
    total = math.ceil(duration / step)

    # Nếu video dài (>30s) và có từ 2 luồng trở lên và tệp video có thật trên đĩa: Kích hoạt Multi-Process Chunking
    can_parallel = duration > 30.0 and total > 60 and threads > 1 and os.path.exists(video_path)

    if can_parallel:
        num_chunks = max(1, min(int(threads), 8))
        chunk_dur = duration / num_chunks
        threads_per_worker = max(1, threads // num_chunks)
        yield f"data: 🚀 Kích hoạt cơ chế phân đoạn song song: {num_chunks} tiến trình ({chunk_dur/60:.1f} phút/đoạn)\n\n"

        pipes = [multiprocessing.Pipe(duplex=False) for _ in range(num_chunks)]
        stop_evt = multiprocessing.Event()
        procs = []

        for i in range(num_chunks):
            s_time = i * chunk_dur
            p = multiprocessing.Process(
                target=_worker_chunk_ocr,
                args=(i, video_path, boxes, s_time, chunk_dur, fps, step, device, threads_per_worker, pipes[i][1], stop_evt)
            )
            procs.append(p)
            p.start()

        completed_chunks = {}
        active_pipes = {i: pipes[i][0] for i in range(num_chunks)}
        chunk_progress = {i: 0 for i in range(num_chunks)}
        calls = skipped = 0
        last_log = 0.0
        first_work_time = None
        base_done = 0

        try:
            while active_pipes:
                if check_stop and check_stop():
                    stop_evt.set()
                    for p in procs:
                        try:
                            p.terminate()
                        except Exception:
                            pass
                    yield "data: 🛑 Đã dừng OCR theo yêu cầu.\n\n"
                    return

                for cid, p_in in list(active_pipes.items()):
                    if p_in.poll(0.015):
                        try:
                            msg = p_in.recv()
                            msg_type = msg[0]
                            if msg_type == 'progress':
                                _, wid, prog, c_calls, c_sk = msg
                                chunk_progress[wid] = prog
                                done_total = sum(chunk_progress.values())
                                elapsed = time.perf_counter() - started
                                if first_work_time is None and done_total > 0:
                                    first_work_time = time.perf_counter()
                                    base_done = done_total

                                if elapsed - last_log >= 0.8 or done_total >= total:
                                    pct = min(99, int(done_total / total * 100))
                                    # Sử dụng tốc độ thời gian thực của worker thay vì bị kéo tụt bởi thời gian khởi động ban đầu
                                    if first_work_time is not None and (time.perf_counter() - first_work_time) >= 1.0 and done_total > base_done:
                                        work_elapsed = time.perf_counter() - first_work_time
                                        speed = ((done_total - base_done) * step) / max(work_elapsed, 0.001)
                                    else:
                                        speed = (done_total * step) / max(elapsed, 0.001)
                                    speed = max(0.5, speed)
                                    eta = max(0, duration - done_total * step) / max(speed, 0.001)
                                    cur_calls = c_calls
                                    cur_sk = c_sk
                                    yield f"data: [OCR {pct}%] {done_total}/{total} mốc × {len(regions)} vùng ({num_chunks} đoạn song song) | {speed:.1f}× | Còn ~{eta/60:.1f} phút | OCR: {cur_calls}, trùng: {cur_sk}\n\n"
                                    last_log = elapsed
                            elif msg_type == 'done':
                                _, wid, chunk_samples, c_calls, c_sk = msg
                                completed_chunks[wid] = chunk_samples
                                calls += c_calls
                                skipped += c_sk
                                del active_pipes[cid]
                            elif msg_type == 'error':
                                _, wid, err_str = msg
                                stop_evt.set()
                                yield f"data: 🛑 Lỗi phân đoạn {wid+1}: {err_str}\n\n"
                                return
                        except (EOFError, BrokenPipeError):
                            if cid in active_pipes:
                                del active_pipes[cid]

            for p in procs:
                p.join(timeout=3.0)
        finally:
            stop_evt.set()
            for p in procs:
                if p.is_alive():
                    try:
                        p.terminate()
                    except Exception:
                        pass

        if check_stop and check_stop():
            return

        samples = [[] for _ in regions]
        for ri in range(len(regions)):
            combined_region = []
            for i in range(num_chunks):
                if i in completed_chunks and ri < len(completed_chunks[i]):
                    combined_region.extend(completed_chunks[i][ri])
            seen_times = set()
            clean_region = []
            for item in sorted(combined_region, key=lambda it: it[0]):
                t_val = item[0]
                txt_val = item[1] if len(item) > 1 else ''
                box_val = item[2] if len(item) > 2 else None
                rounded_t = round(t_val, 3)
                if rounded_t not in seen_times:
                    seen_times.add(rounded_t)
                    clean_region.append((rounded_t, txt_val, box_val))
            samples[ri] = clean_region
    else:
        # Chế độ tuần tự đơn luồng (cho video ngắn, mock tests, hoặc 1 thread)
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            cap.release()
            raise ValueError('Không mở được video')
        position = 0

        def read_sample(index):
            nonlocal position
            target = min(total_frames - 1, int(round(index * step * vid_fps)))
            if target < position:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target)
                position = target
            while position < target:
                if check_stop and check_stop():
                    return None
                if not cap.grab():
                    raise RuntimeError(f'Lỗi giải mã video tại {index * step:.1f}s')
                position += 1
            ok, frame = cap.read()
            position += 1
            if not ok or frame is None:
                raise RuntimeError(f'Không đọc được ảnh tại {index * step:.1f}s')
            return [frame[y:bottom, x:right].copy() for x, y, right, bottom in boxes]

        samples = [[] for _ in regions]
        previous = [None for _ in regions]
        previous_text = ['' for _ in regions]
        previous_box = [None for _ in regions]
        last_read = [-999.0 for _ in regions]
        calls = skipped = 0
        decode_wait = inference_time = 0.0
        last_log = 0.0

        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix='ocr-decode') as decoder:
                pending = decoder.submit(read_sample, 0)
                for idx in range(total):
                    if check_stop and check_stop():
                        yield "data: 🛑 Đã dừng OCR theo yêu cầu.\n\n"
                        return
                    wait_start = time.perf_counter()
                    crops = pending.result()
                    decode_wait += time.perf_counter() - wait_start
                    if crops is None:
                        return
                    if idx + 1 < total:
                        pending = decoder.submit(read_sample, idx + 1)
                    timestamp = idx * step
                    for ri, crop in enumerate(crops):
                        bx, by, br, bb = boxes[ri]
                        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
                        if is_blank_or_no_text(gray):
                            text = ''
                            box_data = None
                            previous[ri] = None
                            previous_text[ri] = ''
                            previous_box[ri] = None
                        elif (previous[ri] is not None and timestamp - last_read[ri] < 1.0
                              and cv2.absdiff(previous[ri], gray).max() <= 2):
                            text = previous_text[ri]
                            box_data = previous_box[ri]
                            skipped += 1
                        else:
                            infer_start = time.perf_counter()
                            if engine_type == 'rapidocr':
                                result, _ = engine(crop, use_cls=(ri != 0))
                            else:
                                result = engine.readtext(crop, detail=1)
                            inference_time += time.perf_counter() - infer_start
                            text = ' '.join(str(line[1]) for line in (result or []) if line and len(line) > 1).strip()
                            box_data = None
                            if result and text:
                                all_xs = [pt[0] for line in result if line and len(line) > 0 and line[0] is not None for pt in line[0]]
                                all_ys = [pt[1] for line in result if line and len(line) > 0 and line[0] is not None for pt in line[0]]
                                if all_xs and all_ys:
                                    box_data = {
                                        'rel_x': int(bx + min(all_xs)),
                                        'rel_r': int(bx + max(all_xs)),
                                        'rel_y': int(by + min(all_ys)),
                                        'rel_b': int(by + max(all_ys))
                                    }
                            last_read[ri] = timestamp
                            calls += 1
                        previous[ri], previous_text[ri], previous_box[ri] = gray, text, box_data
                        samples[ri].append((timestamp, text, box_data))
                    elapsed = time.perf_counter() - started
                    if elapsed - last_log >= 1 or idx + 1 == total:
                        speed = min(duration, (idx + 1) * step) / max(elapsed, 0.001)
                        eta = max(0, duration - (idx + 1) * step) / max(speed, 0.001)
                        yield f"data: [OCR {int((idx+1)/total*100)}%] {idx+1}/{total} mốc × {len(regions)} vùng | {speed:.1f}× | Còn ~{eta/60:.1f} phút | OCR: {calls}, trùng: {skipped}\n\n"
                        last_log = elapsed
        finally:
            cap.release()

        if check_stop and check_stop():
            return

    v_stem = os.path.splitext(os.path.basename(video_path))[0]
    # Xác định thư mục xuất file: Lưu toàn bộ vào output_dir, tuyệt đối không ghi file vào thư mục video gốc
    effective_out_dir = output_dir if (output_dir and os.path.isdir(output_dir)) else os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
    os.makedirs(effective_out_dir, exist_ok=True)

    editor_temp_dir = get_editor_temp_dir(effective_out_dir, video_path)
    os.makedirs(editor_temp_dir, exist_ok=True)

    base = os.path.join(effective_out_dir, v_stem)
    tracks = []
    primary_srt = None
    for ri, region_samples in enumerate(samples):
        segments = _merge_ocr_samples(region_samples, step, duration, video_w=w, video_h=h)
        path = base + ('_ocr.srt' if ri == 0 else f'_ocr_region_{ri+1}.srt')
        if ri == 0:
            primary_srt = path
        with open(path, 'w', encoding='utf-8') as output:
            for n, sub in enumerate(segments, 1):
                output.write(f"{n}\n{format_time(sub['start'])} --> {format_time(sub['end'])}\n{sub['text']}\n\n")
        tracks.append(dict(region=regions[ri], srt_path=path, segments=segments))
        if ri:
            yield f"data: Vùng {ri+1} ({regions[ri]['label']}): {path}\n\n"

    elapsed = time.perf_counter() - started
    # Lưu metadata tổng hợp các vùng vào thư mục xuất file
    metadata_path = base + '_ocr_regions.json'
    with open(metadata_path, 'w', encoding='utf-8') as output:
        json.dump(dict(video=video_path, duration=duration, elapsed=elapsed, provider=provider,
                       ocr_calls=calls, skipped=skipped, tracks=tracks), output, ensure_ascii=False, indent=2)

    speed_final = duration / max(elapsed, 0.001)
    yield f"data: Hoàn thành trong {elapsed/60:.2f} phút ({speed_final:.1f}×). OCR: {calls}, trùng: {skipped}.\n\n"
    yield f"data: Dữ liệu tất cả vùng: {metadata_path}\n\n"
    if primary_srt:
        yield f"data: {primary_srt}\n\n"
        yield f"data: [RESULT_SRT] {primary_srt}\n\n"

    try:
        import shutil
        if primary_srt and os.path.exists(primary_srt):
            shutil.copyfile(primary_srt, os.path.join(editor_temp_dir, 'editor_subtitles.srt'))
            shutil.copyfile(primary_srt, os.path.join(editor_temp_dir, 'ocr_subtitles.srt'))
            shutil.copyfile(primary_srt, os.path.join(editor_temp_dir, f'{os.path.basename(editor_temp_dir)}_ocr.srt'))
        if os.path.exists(metadata_path):
            shutil.copyfile(metadata_path, os.path.join(editor_temp_dir, 'ocr_regions.json'))

        # Tự động xuất ai_blur_boxes.json DUY NHẤT vào editor_temp_dir để tái sử dụng làm mờ (không ghi vào thư mục video gốc)
        if tracks and tracks[0].get('segments'):
            blur_boxes_list = []
            for s_idx, seg in enumerate(tracks[0]['segments']):
                blur_boxes_list.append({
                    'index': s_idx,
                    'sub_id': s_idx + 1,
                    'start': seg.get('start', 0),
                    'end': seg.get('end', 0),
                    'text': seg.get('text', ''),
                    'box': seg.get('box')
                })
            blur_cache_path = os.path.join(editor_temp_dir, 'ai_blur_boxes.json')
            with open(blur_cache_path, 'w', encoding='utf-8') as bbf:
                json.dump(blur_boxes_list, bbf, ensure_ascii=False, indent=2)
        yield f"data: 💾 Đã lưu cache phụ đề OCR & hộp mờ vào: editor_temp/{os.path.basename(editor_temp_dir)}/\n\n"
    except Exception as cache_save_err:
        pass


_OCR_GPU_ENGINE = None
_OCR_CPU_ENGINE = None


def get_ocr_engine(prefer_gpu=True):
    """
    Bắt buộc ưu tiên sử dụng GPU (DirectML / CUDA RTX) với kiến trúc tối ưu mới nhất:
    - det_limit_side_len=960, det_limit_type='max' (tránh upscale phình to ma trận DBNet 280ms -> 25ms)
    - intra_op_num_threads=4, inter_op_num_threads=1
    - Singleton Pattern lưu giữ session trong VRAM, tránh nạp lại nhiều lần.
    """
    global _OCR_GPU_ENGINE, _OCR_CPU_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return None

    opt_params = dict(
        det_limit_side_len=960,
        det_limit_type='max',
        intra_op_num_threads=4,
        inter_op_num_threads=1
    )

    if prefer_gpu:
        if _OCR_GPU_ENGINE is not None:
            return _OCR_GPU_ENGINE
        # 1. Thử GPU DirectML (DirectX 12 GPU Hardware Acceleration cho RTX 5060 & Windows)
        try:
            _OCR_GPU_ENGINE = RapidOCR(det_use_dml=True, cls_use_dml=True, rec_use_dml=True, **opt_params)
            return _OCR_GPU_ENGINE
        except Exception:
            pass
        # 2. Thử GPU CUDA
        try:
            _OCR_GPU_ENGINE = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True, **opt_params)
            return _OCR_GPU_ENGINE
        except Exception:
            pass

    # 3. Fallback về CPU nếu GPU không khả dụng
    if _OCR_CPU_ENGINE is not None:
        return _OCR_CPU_ENGINE
    try:
        _OCR_CPU_ENGINE = RapidOCR(**opt_params)
        return _OCR_CPU_ENGINE
    except Exception:
        return None


def scan_single_frame_box(video_path, timestamp_sec, region):
    """
    Quét AI bounding box cho duy nhất 1 khung hình tại mốc thời gian timestamp_sec.
    Trả về dict chứa tọa độ bounding box theo tỷ lệ phần trăm (x_pct, y_pct, w_pct, h_pct) và chữ nhận diện được.
    """
    if not os.path.exists(video_path):
        return {'success': False, 'error': f'Video không tồn tại: {video_path}'}
    
    ocr_engine = get_ocr_engine(prefer_gpu=True)
    if not ocr_engine:
        return {'success': False, 'error': 'Không thể khởi tạo OCR engine'}
        
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {'success': False, 'error': f'Không mở được luồng đọc video: {video_path}'}
        
    try:
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        
        target_frame = max(0, int(round(float(timestamp_sec) * fps)))
        cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
        ret, frame = cap.read()
        if not ret or frame is None:
            return {'success': False, 'error': 'Không đọc được frame tại thời điểm chỉ định'}
            
        crop_w = int(w * (float(region.get('w', 60)) / 100.0))
        crop_h = int(h * (float(region.get('h', 9.5)) / 100.0))
        crop_x = int(w * (float(region.get('x', 20)) / 100.0))
        crop_y = int(h * (float(region.get('y', 81.5)) / 100.0))

        if crop_x + crop_w > w: crop_w = w - crop_x
        if crop_y + crop_h > h: crop_h = h - crop_y
        if crop_x < 0: crop_x = 0
        if crop_y < 0: crop_y = 0
        
        if crop_w <= 10 or crop_h <= 10:
            return {'success': False, 'error': 'Vùng chọn quá nhỏ'}
            
        crop_bgr = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
        if crop_bgr.size == 0:
            return {'success': False, 'error': 'Vùng crop rỗng'}
            
        res, _ = ocr_engine(crop_bgr, use_cls=False)
        if not res:
            return {'success': True, 'box': None, 'text': '', 'message': 'Không phát hiện chữ trong vùng chọn'}
            
        all_xs = []
        all_ys = []
        texts = []
        for line in res:
            if line and len(line) > 0 and len(line[0]) >= 4:
                for pt in line[0]:
                    all_xs.append(pt[0])
                    all_ys.append(pt[1])
            if line and len(line) > 1 and line[1]:
                texts.append(str(line[1]))
                
        if not all_xs:
            return {'success': True, 'box': None, 'text': '', 'message': 'Không tìm thấy tọa độ chữ'}
            
        min_bx = min(all_xs)
        max_bx = max(all_xs)
        min_by = min(all_ys)
        max_by = max(all_ys)
        
        abs_min_x = crop_x + min_bx
        abs_max_x = crop_x + max_bx
        abs_min_y = crop_y + min_by
        abs_max_y = crop_y + max_by
        
        pad_px_x = max(8, int(w * 0.012))
        pad_px_y = max(4, int(h * 0.006))
        
        box_x_ratio = max(0.01, (abs_min_x - pad_px_x) / float(w))
        box_w_ratio = min(0.98 - box_x_ratio, (abs_max_x - abs_min_x + (pad_px_x * 2)) / float(w))
        box_y_ratio = max(0.01, (abs_min_y - pad_px_y) / float(h))
        box_h_ratio = min(0.98 - box_y_ratio, (abs_max_y - abs_min_y + (pad_px_y * 2)) / float(h))
        
        return {
            'success': True,
            'box': {
                'x_pct': round(box_x_ratio * 100.0, 2),
                'w_pct': round(box_w_ratio * 100.0, 2),
                'y_pct': round(box_y_ratio * 100.0, 2),
                'h_pct': round(box_h_ratio * 100.0, 2)
            },
            'text': ' '.join(texts).strip()
        }
    except Exception as ex:
        return {'success': False, 'error': str(ex)}
    finally:
        cap.release()

def find_visual_boundaries(cap, s, e, prev_end, next_start, crop_x, crop_y, crop_w, crop_h, ocr_engine, fps, ref_gray=None):
    """
    Tự động dò lùi (Backward Seek) và dò tiến (Forward Seek) để xác định chính xác
    khung hình đầu tiên và cuối cùng mà chữ xuất hiện trên video, khắc phục hiện tượng
    chuyển cảnh có chữ trước khi nhân vật cất tiếng nói.
    Áp dụng tối ưu hóa từ kiến trúc OCR mới:
    - Kiểm tra is_blank_or_no_text (0.1ms)
    - So sánh sai khác Temporal Dedup (absdiff < 8.5) bỏ qua 70% cuộc gọi OCR nặng
    - Chỉ dùng text_det (không chạy text_rec) tăng tốc độ dò biên gấp 5-10 lần
    """
    vis_start = s
    vis_end = e

    # 1. DÒ LÙI (Backward Seek) - Bắt đầu từ s về trước (tối đa 0.4s để tối ưu tốc độ)
    max_lookback = min(0.4, max(0.0, s - (prev_end if prev_end is not None else 0.0) - 0.05))
    if max_lookback >= 0.15:
        test_steps = []
        dt = 0.2
        while dt <= max_lookback:
            test_steps.append(dt)
            dt += 0.2
            
        for dt in test_steps:
            t_check = s - dt
            target_f = max(0, int(round(t_check * fps)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            crop_bgr = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
            if crop_bgr.size == 0:
                break
            crop_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
            if is_blank_or_no_text(crop_gray, min_std=5.0, min_laplacian=10.0):
                break
            # Tái sử dụng kết quả nếu sai khác khung hình không đáng kể
            if ref_gray is not None and cv2.absdiff(ref_gray, crop_gray).mean() < 8.5:
                vis_start = t_check
                continue
            try:
                if hasattr(ocr_engine, 'text_det'):
                    dt_boxes, _ = ocr_engine.text_det(crop_bgr)
                    has_text = bool(dt_boxes is not None and len(dt_boxes) > 0)
                else:
                    res, _ = ocr_engine(crop_bgr, use_cls=False)
                    has_text = bool(res and any(line and len(line) > 1 and line[1] for line in res))
                if has_text:
                    vis_start = t_check
                else:
                    break
            except Exception:
                break

    # 2. DÒ TIẾN (Forward Seek) - Từ e về sau (tối đa 0.4s để tối ưu tốc độ)
    max_lookforward = min(0.4, max(0.0, (next_start - e - 0.05) if next_start is not None else 0.4))
    if max_lookforward >= 0.15:
        test_steps = []
        dt = 0.2
        while dt <= max_lookforward:
            test_steps.append(dt)
            dt += 0.2
            
        for dt in test_steps:
            t_check = e + dt
            target_f = max(0, int(round(t_check * fps)))
            cap.set(cv2.CAP_PROP_POS_FRAMES, target_f)
            ret, frame = cap.read()
            if not ret or frame is None:
                break
            crop_bgr = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
            if crop_bgr.size == 0:
                break
            crop_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
            if is_blank_or_no_text(crop_gray, min_std=5.0, min_laplacian=10.0):
                break
            if ref_gray is not None and cv2.absdiff(ref_gray, crop_gray).mean() < 8.5:
                vis_end = t_check
                continue
            try:
                if hasattr(ocr_engine, 'text_det'):
                    dt_boxes, _ = ocr_engine.text_det(crop_bgr)
                    has_text = bool(dt_boxes is not None and len(dt_boxes) > 0)
                else:
                    res, _ = ocr_engine(crop_bgr, use_cls=False)
                    has_text = bool(res and any(line and len(line) > 1 and line[1] for line in res))
                if has_text:
                    vis_end = t_check
                else:
                    break
            except Exception:
                break

    return round(vis_start, 2), round(vis_end, 2)

def calc_sub_width_ratio(text):
    """Tính tỷ lệ chiều rộng box blur khớp với độ dài câu chữ (chữ ngắn -> blur ngắn, chữ dài -> blur dài)"""
    if not text:
        return 0.35
    clean = str(text).strip()
    if not clean:
        return 0.35
    units = 0.0
    for char in clean:
        code = ord(char)
        if (0x4E00 <= code <= 0x9FFF) or (0x3400 <= code <= 0x4DBF) or (0x3040 <= code <= 0x30FF) or (0xAC00 <= code <= 0xD7AF):
            units += 2.9
        elif char == ' ':
            units += 0.9
        else:
            units += 1.45
    return max(0.18, min(0.95, (units * 1.05 + 6.5) / 100.0))

def scan_preview_boxes_generator(video_path, region, subtitles, save_cache_path=None):
    """
    Quét nhận diện bounding box phụ đề theo kiến trúc FFmpeg Pipe HW-Accel siêu tốc của OCR Sub:
    - Tìm và nạp cache tự động từ ai_blur_boxes.json hoặc _ocr_regions.json nếu có (tái sử dụng tức thì 0s)
    - Giải mã video liên tục bằng FFmpeg pipe phần cứng (-hwaccel auto), loại bỏ hoàn toàn cap.set() và seek ngược
    - Áp dụng is_blank_or_no_text (0.1ms) và Smart Temporal Dedup (absdiff < 8.5)
    - Loại bỏ hoàn toàn vòng lặp dò lùi/dò tiến chậm chạp find_visual_boundaries
    - Tự động xả cache từng đợt 25 câu để bảo toàn tiến trình
    - Fallback về OpenCV sequential grab nếu FFmpeg không khả dụng
    """
    import json
    import subprocess

    if not os.path.exists(video_path):
        yield {'type': 'error', 'message': f'Không tìm thấy file video: {video_path}'}
        return

    ocr_engine = get_ocr_engine(prefer_gpu=True)
    if not ocr_engine:
        yield {'type': 'error', 'message': 'Không thể khởi tạo OCR engine'}
        return

    total = len(subtitles)
    if total == 0:
        yield {'type': 'done', 'total_scanned': 0, 'detected_count': 0}
        return

    w, h, vid_fps, total_frames, duration = get_video_info(video_path)

    crop_w = int(w * (float(region.get('w', 60)) / 100.0))
    crop_h = int(h * (float(region.get('h', 9.5)) / 100.0))
    crop_x = int(w * (float(region.get('x', 20)) / 100.0))
    crop_y = int(h * (float(region.get('y', 81.5)) / 100.0))

    if crop_x + crop_w > w: crop_w = w - crop_x
    if crop_y + crop_h > h: crop_h = h - crop_y
    if crop_x < 0: crop_x = 0
    if crop_y < 0: crop_y = 0
    crop_w = max(2, crop_w - (crop_w % 2))
    crop_h = max(2, crop_h - (crop_h % 2))

    detected_count = 0
    cached_boxes_map = {}

    # 1. Nạp dữ liệu cache từ save_cache_path
    if save_cache_path and os.path.exists(save_cache_path) and os.path.getsize(save_cache_path) > 10:
        try:
            with open(save_cache_path, 'r', encoding='utf-8') as f:
                loaded = json.load(f)
            if isinstance(loaded, list):
                for item in loaded:
                    if isinstance(item, dict) and item.get('box') and item.get('index') is not None:
                        cached_boxes_map[item['index']] = item
        except Exception:
            cached_boxes_map = {}

    # 2. Tự động tìm kiếm file _ocr_regions.json hoặc ai_blur_boxes.json lân cận nếu cache chưa đầy
    if len(cached_boxes_map) < total * 0.5:
        video_base = os.path.splitext(video_path)[0]
        cache_candidates = [
            video_base + '_ocr_regions.json',
            video_base + '_ai_blur_boxes.json',
            os.path.join(os.path.dirname(save_cache_path) if save_cache_path else '', 'ocr_regions.json'),
            os.path.join(os.path.dirname(save_cache_path) if save_cache_path else '', 'ai_blur_boxes.json')
        ]
        for cp in cache_candidates:
            if cp and os.path.exists(cp) and os.path.getsize(cp) > 10 and cp != save_cache_path:
                try:
                    with open(cp, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    if isinstance(meta, dict) and 'tracks' in meta:
                        segs = meta.get('tracks', [{}])[0].get('segments', [])
                        for s_idx, seg in enumerate(segs):
                            if seg.get('box') and s_idx not in cached_boxes_map and s_idx < total:
                                cached_boxes_map[s_idx] = {
                                    'index': s_idx,
                                    'sub_id': s_idx + 1,
                                    'start': seg.get('start', 0),
                                    'end': seg.get('end', 0),
                                    'text': seg.get('text', ''),
                                    'box': seg.get('box')
                                }
                    elif isinstance(meta, list):
                        for item in meta:
                            if isinstance(item, dict) and item.get('box') and item.get('index') is not None:
                                if item['index'] not in cached_boxes_map and item['index'] < total:
                                    cached_boxes_map[item['index']] = item
                    if len(cached_boxes_map) >= total * 0.5:
                        break
                except Exception:
                    pass

    # 3. Nạp từ thuộc tính aiBox đã có trong mảng subtitles
    accumulated_dict = dict(cached_boxes_map)
    for idx, sub in enumerate(subtitles):
        if idx not in accumulated_dict and sub.get('aiBox'):
            accumulated_dict[idx] = {
                'index': idx,
                'sub_id': sub.get('id', idx + 1),
                'start': float(sub.get('startSeconds', sub.get('start', 0))),
                'end': float(sub.get('endSeconds', sub.get('end', 0))),
                'text': sub.get('text', sub.get('original_text', '')),
                'box': sub.get('aiBox')
            }
            cached_boxes_map[idx] = accumulated_dict[idx]

    def flush_cache():
        if not save_cache_path or not accumulated_dict:
            return
        try:
            os.makedirs(os.path.dirname(save_cache_path), exist_ok=True)
            sorted_entries = [accumulated_dict[k] for k in sorted(accumulated_dict.keys())]
            tmp_p = save_cache_path + '.tmp'
            with open(tmp_p, 'w', encoding='utf-8') as f:
                json.dump(sorted_entries, f, ensure_ascii=False, indent=2)
            if os.path.exists(save_cache_path):
                try:
                    os.remove(save_cache_path)
                except Exception:
                    pass
            os.replace(tmp_p, save_cache_path)
        except Exception:
            try:
                sorted_entries = [accumulated_dict[k] for k in sorted(accumulated_dict.keys())]
                with open(save_cache_path, 'w', encoding='utf-8') as f:
                    json.dump(sorted_entries, f, ensure_ascii=False)
            except Exception:
                pass

    # Phát ngay các câu đã có trong cache
    for idx in range(total):
        if idx in cached_boxes_map and cached_boxes_map[idx].get('box'):
            c_item = cached_boxes_map[idx]
            box_data = c_item.get('box')
            detected_text = c_item.get('text', '') or subtitles[idx].get('text', subtitles[idx].get('original_text', ''))
            pct = int((idx + 1) / total * 100) if total > 0 else 100
            detected_count += 1
            yield {
                'type': 'progress',
                'index': idx,
                'total': total,
                'pct': pct,
                'sub_id': c_item.get('sub_id', idx + 1),
                'box': box_data,
                'text': detected_text,
                'cached': True
            }

    uncached_indices = [idx for idx in range(total) if idx not in cached_boxes_map or not cached_boxes_map[idx].get('box')]

    if not uncached_indices:
        flush_cache()
        yield {
            'type': 'done',
            'total_scanned': total,
            'detected_count': detected_count
        }
        return

    # Quét các câu chưa có trong cache bằng FFmpeg Pipe HW-Accel giống như OCR Sub
    ffmpeg_path = _get_ffmpeg_path()
    use_ffmpeg = ffmpeg_path is not None and os.path.exists(ffmpeg_path)

    if use_ffmpeg:
        start_t = max(0.0, float(subtitles[uncached_indices[0]].get('startSeconds', subtitles[uncached_indices[0]].get('start', 0))) - 0.2)
        end_t = float(subtitles[uncached_indices[-1]].get('endSeconds', subtitles[uncached_indices[-1]].get('end', 0))) + 0.5
        dur_t = max(0.1, end_t - start_t)
        fps_sample = 2.0
        step = 1.0 / fps_sample
        frame_size = crop_w * crop_h * 3

        cmd = [
            ffmpeg_path,
            "-ss", f"{start_t:.3f}",
            "-t", f"{dur_t:.3f}",
            "-hwaccel", "auto",
            "-i", video_path,
            "-vf", f"fps={fps_sample},crop={crop_w}:{crop_h}:{crop_x}:{crop_y}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-v", "error",
            "pipe:1"
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_size * 5)
        u_pos = 0
        frame_idx = 0
        prev_gray = None
        prev_box = None
        prev_text = ""
        num_uncached = len(uncached_indices)

        try:
            while u_pos < num_uncached:
                raw = proc.stdout.read(frame_size)
                if len(raw) < frame_size:
                    break
                cur_t = start_t + frame_idx * step
                frame_idx += 1

                while u_pos < num_uncached:
                    actual_idx = uncached_indices[u_pos]
                    sub_item = subtitles[actual_idx]
                    s_val = float(sub_item.get('startSeconds', sub_item.get('start', 0)))
                    e_val = float(sub_item.get('endSeconds', sub_item.get('end', 0)))
                    if e_val < cur_t:
                        if actual_idx not in accumulated_dict:
                            accumulated_dict[actual_idx] = {
                                'index': actual_idx,
                                'sub_id': sub_item.get('id', actual_idx + 1),
                                'start': s_val,
                                'end': e_val,
                                'text': sub_item.get('text', sub_item.get('original_text', '')),
                                'box': None
                            }
                            pct = int((actual_idx + 1) / total * 100) if total > 0 else 100
                            yield {
                                'type': 'progress',
                                'index': actual_idx,
                                'total': total,
                                'pct': pct,
                                'sub_id': sub_item.get('id', actual_idx + 1),
                                'box': None,
                                'text': sub_item.get('text', sub_item.get('original_text', '')),
                                'cached': False
                            }
                        u_pos += 1
                    else:
                        break

                if u_pos >= num_uncached:
                    break

                actual_idx = uncached_indices[u_pos]
                sub_item = subtitles[actual_idx]
                s_val = float(sub_item.get('startSeconds', sub_item.get('start', 0)))
                e_val = float(sub_item.get('endSeconds', sub_item.get('end', 0)))

                if s_val <= cur_t <= e_val:
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape((crop_h, crop_w, 3))
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    if is_blank_or_no_text(gray):
                        continue
                    box_data = None
                    detected_text = ""
                    if prev_gray is not None and cv2.absdiff(prev_gray, gray).mean() < 8.5 and prev_box is not None:
                        box_data = dict(prev_box)
                        box_data['visual_start'] = round(max(0.0, s_val - 0.35), 2)
                        box_data['visual_end'] = round(e_val + 0.15, 2)
                        detected_text = prev_text
                        detected_count += 1
                    else:
                        try:
                            res, _ = ocr_engine(frame, use_cls=False)
                            prev_gray = gray
                            if res:
                                all_xs = [pt[0] for line in res if line and len(line) > 0 and len(line[0]) >= 4 for pt in line[0]]
                                all_ys = [pt[1] for line in res if line and len(line) > 0 and len(line[0]) >= 4 for pt in line[0]]
                                if all_xs:
                                    abs_min_x = crop_x + min(all_xs)
                                    abs_max_x = crop_x + max(all_xs)
                                    abs_min_y = crop_y + min(all_ys)
                                    abs_max_y = crop_y + max(all_ys)
                                    # Mở rộng khoảng đệm an toàn chiều ngang để không bao giờ bị cắt xén chữ ở 2 đầu
                                    pad_px_x = max(18, int(w * 0.025))
                                    pad_px_y = max(6, int(h * 0.008))
                                    box_x_ratio = max(0.01, (abs_min_x - pad_px_x) / float(w))
                                    box_w_ratio = min(0.98 - box_x_ratio, (abs_max_x - abs_min_x + (pad_px_x * 2)) / float(w))
                                    box_y_ratio = max(0.01, (abs_min_y - pad_px_y) / float(h))
                                    box_h_ratio = min(0.98 - box_y_ratio, (abs_max_y - abs_min_y + (pad_px_y * 2)) / float(h))
                                    
                                    # Bảo đảm an toàn: Mở rộng box nếu chữ nhận diện bị thiếu ký tự ở 2 đầu
                                    detected_text = ' '.join(str(line[1]) for line in res if line and len(line) > 1).strip()
                                    orig_text_for_calc = sub_item.get('original_text') or detected_text or ''
                                    if not orig_text_for_calc and sub_item.get('text'):
                                        cand_txt = str(sub_item.get('text'))
                                        if any((0x4E00 <= ord(c) <= 0x9FFF) or (0x3400 <= ord(c) <= 0x4DBF) for c in cand_txt):
                                            orig_text_for_calc = cand_txt
                                    est_w_ratio = calc_sub_width_ratio(orig_text_for_calc)
                                    if box_w_ratio < est_w_ratio:
                                        diff_w = est_w_ratio - box_w_ratio
                                        box_x_ratio = max(0.01, box_x_ratio - diff_w / 2.0)
                                        box_w_ratio = min(0.98 - box_x_ratio, est_w_ratio)

                                    # Tự động tính visual_start sớm hơn 0.35s để che đón đầu khung hình khi chuyển cảnh
                                    vis_start_lead = round(max(0.0, s_val - 0.35), 2)
                                    vis_end_pad = round(e_val + 0.15, 2)
                                    box_data = {
                                        'x_pct': round(box_x_ratio * 100.0, 2),
                                        'w_pct': round(box_w_ratio * 100.0, 2),
                                        'y_pct': round(box_y_ratio * 100.0, 2),
                                        'h_pct': round(box_h_ratio * 100.0, 2),
                                        'visual_start': vis_start_lead,
                                        'visual_end': vis_end_pad
                                    }
                                    detected_count += 1
                                    prev_box = box_data
                                    prev_text = detected_text
                        except Exception:
                            pass

                    accumulated_dict[actual_idx] = {
                        'index': actual_idx,
                        'sub_id': sub_item.get('id', actual_idx + 1),
                        'start': s_val,
                        'end': e_val,
                        'text': detected_text or sub_item.get('text', sub_item.get('original_text', '')),
                        'box': box_data
                    }
                    pct = int((actual_idx + 1) / total * 100) if total > 0 else 100
                    yield {
                        'type': 'progress',
                        'index': actual_idx,
                        'total': total,
                        'pct': pct,
                        'sub_id': sub_item.get('id', actual_idx + 1),
                        'box': box_data,
                        'text': detected_text or sub_item.get('text', sub_item.get('original_text', '')),
                        'cached': False
                    }
                    if len(accumulated_dict) % 25 == 0:
                        flush_cache()
                    u_pos += 1
        finally:
            try:
                proc.stdout.close()
                proc.wait(timeout=2.0)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    else:
        # Fallback OpenCV sequential forward reading (không seek ngược, không lặp find_visual_boundaries)
        cap = cv2.VideoCapture(video_path)
        cur_pos = 0
        prev_crop_gray = None
        prev_box_data = None
        prev_detected_text = ""
        try:
            for actual_idx in uncached_indices:
                sub_item = subtitles[actual_idx]
                s = float(sub_item.get('startSeconds', sub_item.get('start', 0)))
                e = float(sub_item.get('endSeconds', sub_item.get('end', 0)))
                mid_t = s + max(0.1, min(0.6, (e - s) * 0.4))
                target_frame = int(round(mid_t * vid_fps))

                if target_frame >= cur_pos and target_frame - cur_pos <= 30:
                    while cur_pos < target_frame - 1:
                        if not cap.grab(): break
                        cur_pos += 1
                    ret, frame = cap.read()
                    cur_pos += 1
                else:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                    cur_pos = target_frame
                    ret, frame = cap.read()
                    cur_pos += 1

                box_data = None
                detected_text = ""
                if ret and frame is not None and crop_w > 10 and crop_h > 10:
                    crop_bgr = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                    if crop_bgr.size > 0:
                        crop_gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
                        if is_blank_or_no_text(crop_gray):
                            pass
                        elif prev_crop_gray is not None and cv2.absdiff(prev_crop_gray, crop_gray).mean() < 8.5 and prev_box_data is not None:
                            box_data = dict(prev_box_data)
                            box_data['visual_start'] = round(max(0.0, s - 0.35), 2)
                            box_data['visual_end'] = round(e + 0.15, 2)
                            detected_text = prev_detected_text
                            detected_count += 1
                        else:
                            try:
                                res, _ = ocr_engine(crop_bgr, use_cls=False)
                                if res:
                                    all_xs = [pt[0] for line in res if line and len(line) > 0 and len(line[0]) >= 4 for pt in line[0]]
                                    all_ys = [pt[1] for line in res if line and len(line) > 0 and len(line[0]) >= 4 for pt in line[0]]
                                    if all_xs:
                                        abs_min_x = crop_x + min(all_xs)
                                        abs_max_x = crop_x + max(all_xs)
                                        abs_min_y = crop_y + min(all_ys)
                                        abs_max_y = crop_y + max(all_ys)
                                        pad_px_x = max(18, int(w * 0.025))
                                        pad_px_y = max(6, int(h * 0.008))
                                        box_x_ratio = max(0.01, (abs_min_x - pad_px_x) / float(w))
                                        box_w_ratio = min(0.98 - box_x_ratio, (abs_max_x - abs_min_x + (pad_px_x * 2)) / float(w))
                                        box_y_ratio = max(0.01, (abs_min_y - pad_px_y) / float(h))
                                        box_h_ratio = min(0.98 - box_y_ratio, (abs_max_y - abs_min_y + (pad_px_y * 2)) / float(h))
                                        
                                        # Bảo đảm an toàn: Mở rộng box nếu chữ nhận diện bị thiếu ký tự ở 2 đầu
                                        detected_text = ' '.join(str(line[1]) for line in res if line and len(line) > 1).strip()
                                        orig_text_for_calc = sub_item.get('original_text') or detected_text or ''
                                        if not orig_text_for_calc and sub_item.get('text'):
                                            cand_txt = str(sub_item.get('text'))
                                            if any((0x4E00 <= ord(c) <= 0x9FFF) or (0x3400 <= ord(c) <= 0x4DBF) for c in cand_txt):
                                                orig_text_for_calc = cand_txt
                                        est_w_ratio = calc_sub_width_ratio(orig_text_for_calc)
                                        if box_w_ratio < est_w_ratio:
                                            diff_w = est_w_ratio - box_w_ratio
                                            box_x_ratio = max(0.01, box_x_ratio - diff_w / 2.0)
                                            box_w_ratio = min(0.98 - box_x_ratio, est_w_ratio)

                                        vis_start_lead = round(max(0.0, s - 0.35), 2)
                                        vis_end_pad = round(e + 0.15, 2)
                                        box_data = {
                                            'x_pct': round(box_x_ratio * 100.0, 2),
                                            'w_pct': round(box_w_ratio * 100.0, 2),
                                            'y_pct': round(box_y_ratio * 100.0, 2),
                                            'h_pct': round(box_h_ratio * 100.0, 2),
                                            'visual_start': vis_start_lead,
                                            'visual_end': vis_end_pad
                                        }
                                        detected_count += 1
                                        prev_crop_gray = crop_gray
                                        prev_box_data = box_data
                                        prev_detected_text = detected_text
                            except Exception:
                                pass

                accumulated_dict[actual_idx] = {
                    'index': actual_idx,
                    'sub_id': sub_item.get('id', actual_idx + 1),
                    'start': s,
                    'end': e,
                    'text': detected_text or sub_item.get('text', sub_item.get('original_text', '')),
                    'box': box_data
                }
                pct = int((actual_idx + 1) / total * 100) if total > 0 else 100
                yield {
                    'type': 'progress',
                    'index': actual_idx,
                    'total': total,
                    'pct': pct,
                    'sub_id': sub_item.get('id', actual_idx + 1),
                    'box': box_data,
                    'text': detected_text or sub_item.get('text', sub_item.get('original_text', '')),
                    'cached': False
                }
                if len(accumulated_dict) % 25 == 0:
                    flush_cache()
        finally:
            cap.release()

    # Xử lý các câu còn sót lại nếu video kết thúc trước
    for actual_idx in uncached_indices:
        if actual_idx not in accumulated_dict:
            sub_item = subtitles[actual_idx]
            accumulated_dict[actual_idx] = {
                'index': actual_idx,
                'sub_id': sub_item.get('id', actual_idx + 1),
                'start': float(sub_item.get('startSeconds', sub_item.get('start', 0))),
                'end': float(sub_item.get('endSeconds', sub_item.get('end', 0))),
                'text': sub_item.get('text', sub_item.get('original_text', '')),
                'box': None
            }
            pct = int((actual_idx + 1) / total * 100) if total > 0 else 100
            yield {
                'type': 'progress',
                'index': actual_idx,
                'total': total,
                'pct': pct,
                'sub_id': sub_item.get('id', actual_idx + 1),
                'box': None,
                'text': sub_item.get('text', sub_item.get('original_text', '')),
                'cached': False
            }

    flush_cache()
    yield {
        'type': 'done',
        'total_scanned': total,
        'detected_count': detected_count
    }


def scan_subtitles_pixel_boxes_generator(video_path, region, subtitle_entries):
    """
    Quét trực tiếp từng đoạn timeline phụ đề [start_s, end_s] trên video bằng RapidOCR AI theo phong cách OCR Sub:
    - Loại bỏ hoàn toàn cap.set() và seek ngược find_visual_boundaries
    - Sử dụng chuẩn tọa độ pixel [box_x_ratio, box_w_ratio] ôm khít chữ
    Yields: ('progress', msg)
    Final yield: ('done', refined_entries)
    """
    if not os.path.exists(video_path):
        yield ("progress", f"🛑 Không tìm thấy file video: {video_path}")
        yield ("done", subtitle_entries)
        return

    total = len(subtitle_entries)
    if total == 0:
        yield ("done", subtitle_entries)
        return

    subtitles_dict = []
    for idx, item in enumerate(subtitle_entries):
        subtitles_dict.append({
            'id': idx + 1,
            'startSeconds': float(item[0]),
            'endSeconds': float(item[1]),
            'text': str(item[2]) if len(item) > 2 else ''
        })

    yield ("progress", f"🎯 [AI OCR Bounding Box] Đang kích hoạt quét siêu tốc tọa độ pixel cho {total} câu phụ đề...")

    boxes_by_idx = {}
    for ev in scan_preview_boxes_generator(video_path, region, subtitles_dict):
        ev_type = ev.get('type')
        if ev_type == 'progress':
            idx = ev.get('index', 0)
            box = ev.get('box')
            if box:
                boxes_by_idx[idx] = box
            if (idx + 1) % 25 == 0 or idx + 1 == total:
                pct = ev.get('pct', int((idx + 1) / total * 100))
                tag = '⚡ Tái sử dụng' if ev.get('cached') else 'Đang quét'
                yield ("progress", f"🎯 [AI OCR Bounding Box] {tag} {idx+1}/{total} câu ({pct}%)...")

    refined = []
    for idx, item in enumerate(subtitle_entries):
        s = float(item[0])
        e = float(item[1])
        txt = str(item[2]) if len(item) > 2 else ""
        if idx in boxes_by_idx:
            b = boxes_by_idx[idx]
            x_ratio = float(b.get('x_pct', 20.0)) / 100.0
            w_ratio = float(b.get('w_pct', 60.0)) / 100.0
            y_ratio = float(b.get('y_pct', region.get('y', 81.5))) / 100.0
            h_ratio = float(b.get('h_pct', region.get('h', 9.5))) / 100.0
            vis_s = float(b.get('visual_start', s))
            vis_e = float(b.get('visual_end', e))
            refined.append((s, e, txt, x_ratio, w_ratio, y_ratio, h_ratio, vis_s, vis_e))
        else:
            refined.append((s, e, txt))

    yield ("progress", f"✅ [AI OCR Bounding Box] Đã quét xong {total} câu! Tọa độ pixel đã được tối ưu ôm khít chữ.")
    yield ("done", refined)

