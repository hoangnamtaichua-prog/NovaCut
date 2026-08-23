import os
import sys
import cv2
import numpy as np
import time

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
    """Kiểm tra nhanh xem vùng crop có phải vùng trống hoặc không có nét chữ không"""
    if crop_gray is None or crop_gray.size == 0:
        return True
    if crop_gray.std() < min_std:
        return True
    var = cv2.Laplacian(crop_gray, cv2.CV_64F).var()
    return var < min_laplacian

def process_ocr(video_path, region, fps=2, threads=4, device='cpu', check_stop=None):
    yield "data: 🚀 Đang khởi động hệ thống OCR Tốc độ cao (High-Speed Engine)...\n\n"
    
    # 1. Initialize Engine (Prefer RapidOCR ONNX DirectML/CUDA GPU, Hybrid, or CPU)
    engine_type = 'rapidocr'
    ocr_engine = None
    gpu_engine = None
    cpu_engine = None
    use_hybrid = (device == 'hybrid')
    use_gpu = (device in ['cuda', 'gpu', 'hybrid'])
    
    try:
        from rapidocr_onnxruntime import RapidOCR
        import onnxruntime as ort
        
        if use_hybrid:
            try:
                gpu_engine = RapidOCR(det_use_dml=True, cls_use_dml=True, rec_use_dml=True)
            except Exception:
                gpu_engine = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
            cpu_engine = RapidOCR()
            ocr_engine = gpu_engine
            yield "data: ⚡🚀 Đã kích hoạt chế độ HYBRID: Kết hợp song song GPU NVIDIA RTX 5060 & Toàn bộ nhân CPU!\n\n"
        elif use_gpu:
            # 1st attempt: DirectML (Native Windows DirectX 12 GPU acceleration for RTX 5060 & sm_120)
            try:
                ocr_engine = RapidOCR(det_use_dml=True, cls_use_dml=True, rec_use_dml=True)
            except Exception:
                # 2nd attempt: CUDA
                ocr_engine = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)

            # Verify which provider was attached to the active session
            attached_provider = "CPU"
            for attr in ['text_rec', 'text_det']:
                sub = getattr(ocr_engine, attr, None)
                if sub and hasattr(sub, 'session') and hasattr(sub.session, 'session'):
                    provs = sub.session.session.get_providers()
                    if 'DmlExecutionProvider' in provs:
                        attached_provider = "DirectML_GPU"
                        break
                    elif 'CUDAExecutionProvider' in provs:
                        attached_provider = "CUDA_GPU"
                        break

            if attached_provider == "DirectML_GPU":
                yield "data: 🚀 Đã kích hoạt lõi RapidOCR DirectML chạy 100% trên GPU NVIDIA RTX 5060 (DirectX 12 GPU Hardware)!\n\n"
            elif attached_provider == "CUDA_GPU":
                yield "data: 🚀 Đã kích hoạt lõi RapidOCR CUDA chạy trực tiếp trên GPU NVIDIA RTX (CUDA Cores)!\n\n"
            else:
                yield "data: ⚡ Đã kích hoạt lõi RapidOCR ONNX chạy trên CPU Đa luồng (Hybrid CPU/GPU Mode).\n\n"
        else:
            ocr_engine = RapidOCR()
    except Exception as e:
        yield f"data: ⚠️ Không khởi động được RapidOCR ({str(e)}), đang thử EasyOCR...\n\n"
        engine_type = 'easyocr'
        try:
            import easyocr
            reader = easyocr.Reader(['vi', 'ch_sim', 'en'], gpu=use_gpu)
            ocr_engine = reader
        except Exception as e_easy:
            yield f"data: 🛑 [LỖI OCR] Không thể khởi động engine OCR (RapidOCR: {str(e)}, EasyOCR: {str(e_easy)}).\n\n"
            yield "data: 💡 Gợi ý: Hãy đảm bảo gói cài đặt đầy đủ file dữ liệu hoặc khởi động lại ứng dụng.\n\n"
            return
        
    yield "data: 📊 Đang phân tích thông số video...\n\n"
    try:
        w, h, vid_fps, total_vid_frames, duration = get_video_info(video_path)
    except Exception as e:
        yield f"data: 🛑 Lỗi đọc video: {str(e)}\n\n"
        return

    # Calculate crop coordinates
    crop_w = int(w * (region['w'] / 100))
    crop_h = int(h * (region['h'] / 100))
    crop_x = int(w * (region['x'] / 100))
    crop_y = int(h * (region['y'] / 100))
    
    # Boundary clamp
    if crop_x + crop_w > w: crop_w = w - crop_x
    if crop_y + crop_h > h: crop_h = h - crop_y
    if crop_x < 0: crop_x = 0
    if crop_y < 0: crop_y = 0
    
    if crop_w <= 0 or crop_h <= 0:
        yield "data: 🛑 Lỗi: Vùng chọn OCR quá nhỏ hoặc không hợp lệ. Vui lòng vẽ lại vùng phụ đề.\n\n"
        return

    yield f"data: 🎯 Vùng quét phụ đề: {crop_w}x{crop_h} tại tọa độ X:{crop_x} Y:{crop_y} (Thời lượng: {duration:.1f}s)\n\n"

    # Step in video timestamp
    step_sec = 1.0 / float(fps) if fps > 0 else 0.5
    sample_times = []
    curr_t = 0.0
    while curr_t < duration:
        sample_times.append(curr_t)
        curr_t += step_sec
    if not sample_times:
        sample_times = [0.0]

    total_samples = len(sample_times)
    yield f"data: 📥 Bắt đầu quét trực tiếp từ RAM ({total_samples} mốc thời gian, {fps} fps)...\n\n"

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        yield "data: 🛑 Không thể mở luồng đọc video trực tiếp.\n\n"
        return

    results = []
    success_count = 0
    empty_count = 0
    skipped_dup_count = 0

    prev_crop_gray = None
    prev_text = ""
    current_frame_pos = -1

    def run_ocr_on_image(crop_bgr, item_idx=0):
        if engine_type == 'rapidocr':
            try:
                active_engine = ocr_engine
                if use_hybrid and cpu_engine and (item_idx % 2 == 1):
                    active_engine = cpu_engine
                res, _ = active_engine(crop_bgr)
                if res:
                    texts = [item[1] for item in res if item and len(item) > 1]
                    return " ".join(texts).strip()
            except Exception:
                pass
            return ""
        else:
            try:
                text_list = ocr_engine.readtext(crop_bgr, detail=0, paragraph=True)
                return " ".join(text_list).strip()
            except Exception:
                return ""

    try:
        for idx, t_sec in enumerate(sample_times):
            if check_stop and check_stop():
                yield "data: 🛑 Đã dừng tiến trình quét OCR theo yêu cầu của người dùng.\n\n"
                return

            target_frame = int(round(t_sec * vid_fps))
            
            # Fast sequential grab vs seek optimization (prevents CPU decode spike)
            if current_frame_pos < 0 or target_frame < current_frame_pos or (target_frame - current_frame_pos) > 60:
                cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
                ret, frame = cap.read()
                current_frame_pos = target_frame + 1
            else:
                # Fast grab forward without re-seeking
                while current_frame_pos < target_frame:
                    cap.grab()
                    current_frame_pos += 1
                ret, frame = cap.read()
                current_frame_pos += 1

            if not ret or frame is None:
                # Video ended or read error
                results.append({'time': t_sec, 'text': ''})
                empty_count += 1
                continue

            # Crop Region in Memory
            crop = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
            if crop.size == 0:
                results.append({'time': t_sec, 'text': ''})
                empty_count += 1
                continue

            crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)

            # 1. Quick blank check (0.01ms)
            if is_blank_or_no_text(crop_gray):
                text = ""
                prev_text = ""
                prev_crop_gray = crop_gray
                empty_count += 1
                results.append({'time': t_sec, 'text': ''})
            else:
                # 2. Similarity check with previous frame (0.01ms)
                is_similar = False
                if prev_crop_gray is not None and prev_crop_gray.shape == crop_gray.shape:
                    diff = cv2.absdiff(prev_crop_gray, crop_gray).mean()
                    if diff < 2.5: # Virtually identical subtitle
                        is_similar = True

                if is_similar:
                    text = prev_text
                    skipped_dup_count += 1
                    if text:
                        success_count += 1
                    else:
                        empty_count += 1
                else:
                    # 3. Run OCR inference on changed frame
                    text = run_ocr_on_image(crop, idx)
                    prev_text = text
                    prev_crop_gray = crop_gray
                    if text:
                        success_count += 1
                    else:
                        empty_count += 1

                results.append({'time': t_sec, 'text': text})

            # Real-time progress logging
            if idx % 5 == 0 or idx == total_samples - 1:
                pct = int((idx + 1) / total_samples * 100)
                yield f"data: [OCR {pct}%] Đã xử lý {idx+1}/{total_samples} mốc | Phát hiện: {success_count} | Bỏ qua trùng lặp: {skipped_dup_count}\n\n"

    finally:
        cap.release()

    yield f"data: 🏁 Đã quét xong {total_samples} mốc (Phát hiện: {success_count}, Bỏ qua trùng: {skipped_dup_count}). Đang tổng hợp phụ đề...\n\n"

    # Merge consecutive identical texts into SRT time blocks
    srt_lines = []
    current_sub = None

    for res in results:
        text = res['text']
        t = res['time']
        if not text:
            if current_sub:
                current_sub['end'] = t
                srt_lines.append(current_sub)
                current_sub = None
            continue
            
        if current_sub is None:
            current_sub = {'start': t, 'end': t + step_sec, 'text': text}
        else:
            if text == current_sub['text']:
                current_sub['end'] = t + step_sec
            else:
                srt_lines.append(current_sub)
                current_sub = {'start': t, 'end': t + step_sec, 'text': text}

    if current_sub:
        srt_lines.append(current_sub)

    out_srt = os.path.splitext(video_path)[0] + "_ocr.srt"
    with open(out_srt, 'w', encoding='utf-8') as f:
        for i, sub in enumerate(srt_lines):
            f.write(f"{i+1}\n")
            f.write(f"{format_time(sub['start'])} --> {format_time(sub['end'])}\n")
            f.write(f"{sub['text']}\n\n")

    yield f"data: HOÀN THÀNH! Đã lưu file SRT tại:\n\n"
    yield f"data: {out_srt}\n\n"

_OCR_GPU_ENGINE = None
_OCR_CPU_ENGINE = None

def get_ocr_engine(prefer_gpu=True):
    """
    Bắt buộc ưu tiên sử dụng GPU (DirectML / CUDA RTX) để quét tọa độ chữ siêu tốc.
    Chỉ fallback về CPU khi máy không có GPU hoặc khởi tạo GPU thất bại.
    Sử dụng Singleton Pattern để lưu giữ session ONNX trong VRAM, tránh nạp lại nhiều lần.
    """
    global _OCR_GPU_ENGINE, _OCR_CPU_ENGINE
    try:
        from rapidocr_onnxruntime import RapidOCR
    except Exception:
        return None

    if prefer_gpu:
        if _OCR_GPU_ENGINE is not None:
            return _OCR_GPU_ENGINE
        # 1. Thử GPU DirectML (DirectX 12 GPU Hardware Acceleration cho RTX 5060 & Windows)
        try:
            _OCR_GPU_ENGINE = RapidOCR(det_use_dml=True, cls_use_dml=True, rec_use_dml=True)
            return _OCR_GPU_ENGINE
        except Exception:
            pass
        # 2. Thử GPU CUDA
        try:
            _OCR_GPU_ENGINE = RapidOCR(det_use_cuda=True, cls_use_cuda=True, rec_use_cuda=True)
            return _OCR_GPU_ENGINE
        except Exception:
            pass

    # 3. Fallback về CPU nếu GPU không khả dụng
    if _OCR_CPU_ENGINE is not None:
        return _OCR_CPU_ENGINE
    try:
        _OCR_CPU_ENGINE = RapidOCR()
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
            
        res, _ = ocr_engine(crop_bgr)
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

def find_visual_boundaries(cap, s, e, prev_end, next_start, crop_x, crop_y, crop_w, crop_h, ocr_engine, fps):
    """
    Tự động dò lùi (Backward Seek) và dò tiến (Forward Seek) để xác định chính xác
    khung hình đầu tiên và cuối cùng mà chữ xuất hiện trên video, khắc phục hiện tượng
    chuyển cảnh có chữ trước khi nhân vật cất tiếng nói.
    """
    vis_start = s
    vis_end = e

    # 1. DÒ LÙI (Backward Seek) - Bắt đầu từ s về trước
    max_lookback = min(2.5, max(0.0, s - (prev_end if prev_end is not None else 0.0) - 0.05))
    if max_lookback >= 0.15:
        test_steps = []
        dt = 0.25
        while dt <= max_lookback:
            test_steps.append(dt)
            dt += 0.25
            
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
            try:
                res, _ = ocr_engine(crop_bgr)
                if res and any(line and len(line) > 1 and line[1] for line in res):
                    vis_start = t_check
                else:
                    break
            except Exception:
                break

    # 2. DÒ TIẾN (Forward Seek) - Từ e về sau
    max_lookforward = min(2.0, max(0.0, (next_start - e - 0.05) if next_start is not None else 2.0))
    if max_lookforward >= 0.15:
        test_steps = []
        dt = 0.25
        while dt <= max_lookforward:
            test_steps.append(dt)
            dt += 0.25
            
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
            try:
                res, _ = ocr_engine(crop_bgr)
                if res and any(line and len(line) > 1 and line[1] for line in res):
                    vis_end = t_check
                else:
                    break
            except Exception:
                break

    return round(vis_start, 2), round(vis_end, 2)

def scan_preview_boxes_generator(video_path, region, subtitles):
    """
    Quét trực tiếp từng câu phụ đề trong danh sách subtitles cho Preview Player.
    subtitles: list các dict { id, startSeconds, endSeconds, text, ... }
    Yields dict theo chuẩn SSE:
      {'type': 'progress', 'index': i, 'total': N, 'pct': P, 'sub_id': id, 'box': {...}, 'text': ...}
      {'type': 'done', 'total_scanned': N, 'detected_count': count}
    """
    if not os.path.exists(video_path):
        yield {'type': 'error', 'message': f'Không tìm thấy file video: {video_path}'}
        return

    ocr_engine = get_ocr_engine(prefer_gpu=True)
    if not ocr_engine:
        yield {'type': 'error', 'message': 'Không thể khởi tạo OCR engine'}
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        yield {'type': 'error', 'message': f'Không thể mở video: {video_path}'}
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = len(subtitles)

    crop_w = int(w * (float(region.get('w', 60)) / 100.0))
    crop_h = int(h * (float(region.get('h', 9.5)) / 100.0))
    crop_x = int(w * (float(region.get('x', 20)) / 100.0))
    crop_y = int(h * (float(region.get('y', 81.5)) / 100.0))

    if crop_x + crop_w > w: crop_w = w - crop_x
    if crop_y + crop_h > h: crop_h = h - crop_y
    if crop_x < 0: crop_x = 0
    if crop_y < 0: crop_y = 0

    detected_count = 0

    try:
        for idx, sub in enumerate(subtitles):
            s = float(sub.get('startSeconds', sub.get('start', 0)))
            e = float(sub.get('endSeconds', sub.get('end', 0)))
            sub_id = sub.get('id', idx + 1)
            orig_txt = sub.get('text', sub.get('original_text', ''))

            prev_end = float(subtitles[idx-1].get('endSeconds', subtitles[idx-1].get('end', 0))) if idx > 0 else 0.0
            next_start = float(subtitles[idx+1].get('startSeconds', subtitles[idx+1].get('start', 0))) if idx < total - 1 else None

            # Lấy mẫu khung hình ở giữa câu thoại (40% timeline của câu)
            mid_t = s + max(0.1, min(0.6, (e - s) * 0.4))
            target_frame = int(round(mid_t * fps))

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            box_data = None
            detected_text = ""

            if ret and frame is not None and crop_w > 10 and crop_h > 10:
                crop_bgr = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                if crop_bgr.size > 0:
                    try:
                        res, _ = ocr_engine(crop_bgr)
                        if res:
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
                            if all_xs:
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

                                # Dò lùi/dò tiến để bắt đúng thời điểm chữ xuất hiện khi chuyển cảnh
                                vis_s, vis_e = find_visual_boundaries(
                                    cap, s, e, prev_end, next_start,
                                    crop_x, crop_y, crop_w, crop_h,
                                    ocr_engine, fps
                                )

                                box_data = {
                                    'x_pct': round(box_x_ratio * 100.0, 2),
                                    'w_pct': round(box_w_ratio * 100.0, 2),
                                    'y_pct': round(box_y_ratio * 100.0, 2),
                                    'h_pct': round(box_h_ratio * 100.0, 2),
                                    'visual_start': vis_s,
                                    'visual_end': vis_e
                                }
                                detected_text = " ".join(texts).strip()
                                detected_count += 1
                    except Exception:
                        pass

            pct = int((idx + 1) / total * 100) if total > 0 else 100
            yield {
                'type': 'progress',
                'index': idx,
                'total': total,
                'pct': pct,
                'sub_id': sub_id,
                'box': box_data,
                'text': detected_text or orig_txt
            }
    finally:
        cap.release()

    yield {
        'type': 'done',
        'total_scanned': total,
        'detected_count': detected_count
    }

def scan_subtitles_pixel_boxes_generator(video_path, region, subtitle_entries):
    """
    Quét trực tiếp từng đoạn timeline phụ đề [start_s, end_s] trên video bằng RapidOCR AI,
    để lấy chính xác tọa độ pixel [box_x_ratio, box_w_ratio] và khung hình xuất hiện thực tế [vis_s, vis_e].
    Yields: ('progress', msg)
    Final yield: ('done', refined_entries)
    """
    if not os.path.exists(video_path):
        yield ("progress", f"🛑 Không tìm thấy file video: {video_path}")
        yield ("done", subtitle_entries)
        return

    ocr_engine = get_ocr_engine(prefer_gpu=True)
    if not ocr_engine:
        yield ("progress", f"⚠️ Không tải được RapidOCR, sử dụng phương pháp ước tính.")
        yield ("done", subtitle_entries)
        return

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        yield ("done", subtitle_entries)
        return

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total = len(subtitle_entries)

    crop_w = int(w * (float(region.get('w', 60)) / 100.0))
    crop_h = int(h * (float(region.get('h', 9.5)) / 100.0))
    crop_x = int(w * (float(region.get('x', 20)) / 100.0))
    crop_y = int(h * (float(region.get('y', 81.5)) / 100.0))

    if crop_x + crop_w > w: crop_w = w - crop_x
    if crop_y + crop_h > h: crop_h = h - crop_y
    if crop_x < 0: crop_x = 0
    if crop_y < 0: crop_y = 0

    yield ("progress", f"🎯 [AI OCR Bounding Box] Đang kích hoạt AI quét tọa độ pixel & khung hình thực tế cho {total} câu phụ đề...")

    refined = []
    try:
        for idx, item in enumerate(subtitle_entries):
            s = float(item[0])
            e = float(item[1])
            txt = str(item[2]) if len(item) > 2 else ""

            prev_end = float(subtitle_entries[idx-1][1]) if idx > 0 else 0.0
            next_start = float(subtitle_entries[idx+1][0]) if idx < total - 1 else None

            # Lấy mẫu khung hình ở giữa câu thoại
            mid_t = s + max(0.1, min(0.6, (e - s) * 0.4))
            target_frame = int(round(mid_t * fps))

            cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)
            ret, frame = cap.read()
            detected_box = None

            if ret and frame is not None and crop_w > 10 and crop_h > 10:
                crop_bgr = frame[crop_y:crop_y+crop_h, crop_x:crop_x+crop_w]
                if crop_bgr.size > 0:
                    try:
                        res, _ = ocr_engine(crop_bgr)
                        if res:
                            all_xs = []
                            for line in res:
                                if line and len(line) > 0 and len(line[0]) >= 4:
                                    for pt in line[0]:
                                        all_xs.append(pt[0])
                            if all_xs:
                                min_bx = min(all_xs)
                                max_bx = max(all_xs)
                                abs_min_x = crop_x + min_bx
                                abs_max_x = crop_x + max_bx
                                pad_px = max(8, int(w * 0.012))
                                box_x_ratio = max(0.01, (abs_min_x - pad_px) / float(w))
                                box_w_ratio = min(0.98 - box_x_ratio, (abs_max_x - abs_min_x + (pad_px * 2)) / float(w))
                                detected_box = (box_x_ratio, box_w_ratio)
                    except Exception:
                        pass

            if detected_box:
                vis_s, vis_e = find_visual_boundaries(
                    cap, s, e, prev_end, next_start,
                    crop_x, crop_y, crop_w, crop_h,
                    ocr_engine, fps
                )
                refined.append((s, e, txt, detected_box[0], detected_box[1], vis_s, vis_e))
            else:
                refined.append((s, e, txt))

            if (idx + 1) % 20 == 0 or idx + 1 == total:
                pct = int((idx + 1) / total * 100)
                yield ("progress", f"🎯 [AI OCR Bounding Box] Đã quét {idx+1}/{total} câu ({pct}%)...")

    finally:
        cap.release()

    yield ("progress", f"✅ [AI OCR Bounding Box] Đã quét xong {total} câu! Tọa độ pixel và khung hình xuất hiện đã được tối ưu ôm khít chữ.")
    yield ("done", refined)

