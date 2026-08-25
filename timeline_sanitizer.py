import os
import json
import math
import time
import threading
from typing import List, Dict, Tuple, Any

def extract_scene_cuts_with_progress(
    video_path: str,
    threshold: float = 27.0,
    cache_dir: str = 'output/auto_edit_temp',
    check_stop_func = None,
    target_timeline: List[Dict[str, Any]] = None
):
    """
    Quét video gốc để phát hiện các điểm chuyển cảnh (scene cuts) tự nhiên bằng PySceneDetect.
    Tối ưu hóa siêu tốc bằng Boundary-Targeted Scan (chỉ quét quanh các mốc timeline) + downscale + frame_skip.
    Yields (log_message, scene_cuts_result).
    """
    if not os.path.exists(video_path):
        yield ("Không tìm thấy video đầu vào.", [])
        return

    import hashlib
    os.makedirs(cache_dir, exist_ok=True)
    video_base = os.path.splitext(os.path.basename(video_path))[0]
    file_size = os.path.getsize(video_path)
    mtime = int(os.path.getmtime(video_path))
    cache_hash = hashlib.md5(f"{video_path}_{file_size}_{mtime}_{threshold}".encode()).hexdigest()[:10]
    cache_filename = f"scene_cuts_{video_base}_{cache_hash}.json"
    cache_path = os.path.join(cache_dir, cache_filename)

    # 1. Kiểm tra cache
    if os.path.exists(cache_path):
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    yield (f"Đã tải {len(data)} điểm chuyển cảnh từ bộ nhớ đệm (Cache tức thì).", [float(x) for x in data])
                    return
        except Exception:
            pass

    # 2. Quét tối ưu bằng PySceneDetect + Boundary-Targeted Scan
    try:
        from scenedetect import SceneManager, ContentDetector, open_video
        
        video = open_video(video_path)
        total_frames = video.duration.frame_num if (video.duration and hasattr(video.duration, 'frame_num')) else 100
        duration_sec = video.duration.seconds if (video.duration and hasattr(video.duration, 'seconds')) else 0.0

        # Downscale video xuống frame size ~360px để tăng tốc xử lý x20-x50 lần
        max_dim = max(video.frame_size) if video.frame_size else 1920
        downscale_factor = max(1, int(max_dim / 360))
        frame_skip = 2  # Quét 1 frame mỗi 3 frame để giảm 66% thời gian đọc đĩa

        # Xây dựng danh sách các cửa sổ biên cần quét (Boundary Windows) nếu có target_timeline
        merged_windows = []
        if target_timeline and isinstance(target_timeline, list) and len(target_timeline) > 0:
            raw_windows = []
            for clip in target_timeline:
                v_s = float(clip.get('start', 0))
                v_d = float(clip.get('duration', 0))
                raw_windows.append((max(0.0, v_s - 1.5), min(duration_sec, v_s + 1.5)))
                raw_windows.append((max(0.0, v_s + v_d - 1.5), min(duration_sec, v_s + v_d + 1.5)))
            
            raw_windows.sort(key=lambda x: x[0])
            for w in raw_windows:
                if not merged_windows or w[0] > merged_windows[-1][1]:
                    merged_windows.append([w[0], w[1]])
                else:
                    merged_windows[-1][1] = max(merged_windows[-1][1], w[1])

        all_cuts = []

        if merged_windows:
            # Quét siêu tốc theo từng cửa sổ biên (Boundary-Targeted Scan)
            total_win = len(merged_windows)
            for idx, (win_s, win_e) in enumerate(merged_windows):
                if check_stop_func and check_stop_func():
                    yield ("Đã dừng quét chuyển cảnh theo yêu cầu.", [])
                    return
                
                win_pct = int((idx + 1) / total_win * 100)
                if idx % 5 == 0 or idx == total_win - 1:
                    yield (f"Đang quét chuyển cảnh cục bộ: {win_pct}% (Cửa sổ {idx+1}/{total_win} - phát hiện {len(all_cuts)} điểm)...", None)

                try:
                    sm_win = SceneManager()
                    sm_win.auto_downscale = False
                    sm_win.downscale = downscale_factor
                    sm_win.add_detector(ContentDetector(threshold=threshold))
                    sm_win.detect_scenes(video, frame_skip=frame_skip, start_time=win_s, end_time=win_e)
                    scenes = sm_win.get_scene_list()
                    for s in scenes:
                        cut_t = round(s[0].seconds, 3)
                        if cut_t > win_s + 0.1:
                            all_cuts.append(cut_t)
                except Exception:
                    pass
            
            cuts = sorted(list(set(all_cuts)))
        else:
            # Quét toàn bộ video nếu không có target_timeline
            sm = SceneManager()
            sm.auto_downscale = False
            sm.downscale = downscale_factor
            sm.add_detector(ContentDetector(threshold=threshold))

            error_holder = []
            def detect_worker():
                try:
                    sm.detect_scenes(video, frame_skip=frame_skip)
                except Exception as ex:
                    error_holder.append(ex)

            worker = threading.Thread(target=detect_worker, daemon=True)
            worker.start()

            last_reported_pct = -1
            last_report_time = 0

            while worker.is_alive():
                if check_stop_func and check_stop_func():
                    sm.stop()
                    yield ("Đã dừng quét chuyển cảnh theo yêu cầu.", [])
                    return

                cur_frame = getattr(video, 'frame_number', 0)
                cur_sec = (cur_frame / total_frames) * duration_sec if total_frames > 0 else 0
                pct = min(99, int((cur_frame / max(1, total_frames)) * 100))
                now = time.time()

                if (pct >= last_reported_pct + 5 or (now - last_report_time > 2.0 and pct > last_reported_pct)):
                    cuts_found = len(sm.get_scene_list())
                    yield (f"Đang quét chuyển cảnh: {pct}% ({cur_sec:.0f}s / {duration_sec:.0f}s - phát hiện {cuts_found} cảnh)...", None)
                    last_reported_pct = pct
                    last_report_time = now

                time.sleep(0.1)

            worker.join()

            if error_holder:
                yield (f"⚠️ Lỗi quét chuyển cảnh ({error_holder[0]}). Tiếp tục với timeline gốc.", [])
                return

            scenes = sm.get_scene_list()
            cuts = [round(s[0].seconds, 3) for i, s in enumerate(scenes) if i > 0]

        # Lưu cache
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cuts, f, indent=2)
        except Exception:
            pass

        yield (f"Đã nhận diện {len(cuts)} điểm chuyển cảnh vật lý trong video gốc.", cuts)

    except Exception as e:
        yield (f"⚠️ PySceneDetect: {e}. Bỏ qua snap cảnh.", [])


def extract_scene_cuts(video_path: str, threshold: float = 27.0, cache_dir: str = 'output/auto_edit_temp') -> List[float]:
    """Hàm đồng bộ trả về kết quả cuts (dùng cho các module khác nếu cần)."""
    result = []
    for _, cuts in extract_scene_cuts_with_progress(video_path, threshold=threshold, cache_dir=cache_dir):
        if cuts is not None:
            result = cuts
    return result


def find_nearest_cut(time_val: float, scene_cuts: List[float], max_dist: float) -> Tuple[float, float]:
    """
    Tìm scene cut gần nhất với time_val trong khoảng max_dist.
    Trả về (nearest_cut, distance) hoặc (None, infinity) nếu không tìm thấy.
    """
    if not scene_cuts:
        return None, float('inf')
        
    nearest = None
    min_d = float('inf')
    
    for cut in scene_cuts:
        d = abs(cut - time_val)
        if d <= max_dist and d < min_d:
            min_d = d
            nearest = cut
            
    return nearest, min_d


def sanitize_timeline(
    timeline: List[Dict[str, Any]],
    scene_cuts: List[float],
    snap_threshold: float = 0.6,
    min_clip_duration: float = 1.2,
    max_speed_ratio_deviation: float = 0.15,
    dense_cut_threshold: int = 3
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Tối ưu hóa và làm sạch timeline từ LLM:
    1. Snap các điểm start/end vào scene cut gần nhất (trong buffer snap_threshold).
    2. Kiểm tra ngưỡng an toàn tốc độ (speed_ratio deviation) để tránh lệch tiếng-hình.
    3. Gộp các clip quá ngắn (< min_clip_duration).
    4. Xử lý vùng scene cut dày đặc (dense cut zone).
    
    Trả về: (sanitized_timeline, log_messages)
    """
    logs = []
    if not timeline:
        return [], logs

    processed_clips = []

    # Bước 1: Khởi tạo dữ liệu và Snap vào Scene Cuts
    for i, item in enumerate(timeline):
        raw_start = float(item.get('start', 0.0))
        raw_end = float(item.get('end', 0.0))
        orig_dur = max(0.1, raw_end - raw_start)
        voice_ref = item.get('voice_ref', i + 1)
        
        snapped_start = raw_start
        snapped_end = raw_end
        start_snapped = False
        end_snapped = False
        
        # Snap start
        near_start_cut, dist_start = find_nearest_cut(raw_start, scene_cuts, snap_threshold)
        if near_start_cut is not None and near_start_cut >= 0:
            snapped_start = near_start_cut
            start_snapped = True
            
        # Snap end
        near_end_cut, dist_end = find_nearest_cut(raw_end, scene_cuts, snap_threshold)
        if near_end_cut is not None and near_end_cut > snapped_start:
            snapped_end = near_end_cut
            end_snapped = True

        actual_dur = snapped_end - snapped_start
        
        # Kiểm tra ngưỡng an toàn của speed_ratio = actual_duration / original_duration
        if actual_dur <= 0:
            # Nếu snap làm clip thành <= 0 thì hủy snap
            snapped_start = raw_start
            snapped_end = raw_end
            actual_dur = orig_dur
            start_snapped = False
            end_snapped = False
            
        speed_ratio = actual_dur / orig_dur
        deviation = abs(speed_ratio - 1.0)
        
        if deviation > max_speed_ratio_deviation:
            # Vượt ngưỡng an toàn: HỦY SNAP để bảo toàn đồng bộ tiếng - hình
            logs.append(
                f"[SANITIZE] Clip #{i+1}: Huy snap do do lech toc do ({speed_ratio:.2f}x, lech {deviation*100:.1f}%) "
                f"vuot nguong an toan (+/-{max_speed_ratio_deviation*100:.0f}%)."
            )
            final_start = raw_start
            final_end = raw_end
            final_dur = orig_dur
            final_ratio = 1.0
        else:
            final_start = snapped_start
            final_end = snapped_end
            final_dur = actual_dur
            final_ratio = speed_ratio
            if start_snapped or end_snapped:
                logs.append(
                    f"[SANITIZE] Clip #{i+1}: Snap thanh cong! "
                    f"start ({raw_start:.2f}s -> {final_start:.2f}s), "
                    f"end ({raw_end:.2f}s -> {final_end:.2f}s), "
                    f"Toc do bu: {final_ratio:.2f}x"
                )

        processed_clips.append({
            "voice_ref": voice_ref,
            "start": round(final_start, 3),
            "end": round(final_end, 3),
            "duration": round(final_dur, 3),
            "original_duration": round(orig_dur, 3),
            "speed_ratio": round(final_ratio, 3),
            "raw_start": round(raw_start, 3),
            "raw_end": round(raw_end, 3)
        })

    # Bước 2: Gộp các clip quá ngắn (< min_clip_duration)
    merged_clips = []
    skip_indices = set()
    
    idx = 0
    while idx < len(processed_clips):
        if idx in skip_indices:
            idx += 1
            continue
            
        curr = processed_clips[idx]
        
        # Nếu clip quá ngắn và có clip tiếp theo
        if curr['duration'] < min_clip_duration and idx + 1 < len(processed_clips):
            nxt = processed_clips[idx + 1]
            merged_orig_dur = curr['original_duration'] + nxt['original_duration']
            
            # Kiểm tra xem curr và nxt có liền kề nhau trong video gốc không
            if abs(nxt['start'] - curr['end']) <= 1.0 and nxt['end'] > curr['start']:
                # Liền kề trong phim: Nối liền từ curr['start'] đến nxt['end']
                merged_start = curr['start']
                merged_end = nxt['end']
            else:
                # Không liền kề trong phim: Lấy cảnh của nxt và mở rộng độ dài để phủ cả 2
                merged_start = nxt['start']
                merged_end = nxt['start'] + merged_orig_dur
                
            merged_dur = max(0.1, merged_end - merged_start)
            merged_ratio = merged_dur / merged_orig_dur if merged_orig_dur > 0 else 1.0
            
            logs.append(
                f"[SANITIZE] Gop clip #{idx+1} (ngan: {curr['duration']:.2f}s) vao clip #{idx+2}. "
                f"Thoi luong video: {merged_dur:.2f}s, Audio tuong ung: {merged_orig_dur:.2f}s"
            )
            
            merged_clips.append({
                "voice_ref": curr['voice_ref'],
                "start": round(merged_start, 3),
                "end": round(merged_end, 3),
                "duration": round(merged_dur, 3),
                "original_duration": round(merged_orig_dur, 3),
                "speed_ratio": round(merged_ratio, 3),
                "raw_start": curr['raw_start'],
                "raw_end": nxt['raw_end']
            })
            skip_indices.add(idx + 1)
            idx += 2
            continue
        elif curr['duration'] < min_clip_duration and len(merged_clips) > 0:
            # Gộp vào clip trước đó nếu là clip cuối cùng
            prev = merged_clips[-1]
            merged_orig_dur = prev['original_duration'] + curr['original_duration']
            
            # Mở rộng clip trước
            merged_start = prev['start']
            merged_end = prev['start'] + merged_orig_dur
            merged_dur = max(0.1, merged_end - merged_start)
            merged_ratio = merged_dur / merged_orig_dur if merged_orig_dur > 0 else 1.0
            
            logs.append(
                f"[SANITIZE] Gop clip cuoi #{idx+1} (ngan: {curr['duration']:.2f}s) vao clip lien truoc #{len(merged_clips)}."
            )
            
            prev['end'] = round(merged_end, 3)
            prev['duration'] = round(merged_dur, 3)
            prev['original_duration'] = round(merged_orig_dur, 3)
            prev['speed_ratio'] = round(merged_ratio, 3)
            idx += 1
            continue
        else:
            merged_clips.append(curr)
            idx += 1

    # Bước 3: Xử lý vùng scene cut dày đặc (dense-cut zone)
    for i, clip in enumerate(merged_clips):
        c_start = clip['start']
        c_end = clip['end']
        # Đếm số scene cut rơi lọt vào bên trong khoảng (c_start, c_end)
        internal_cuts = [c for c in scene_cuts if c_start + 0.1 < c < c_end - 0.1]
        if len(internal_cuts) >= dense_cut_threshold and clip['duration'] <= 3.0:
            # Mở rộng nhẹ 0.2s hai đầu để không bị cụt giữa pha hành động
            new_start = max(0.0, c_start - 0.2)
            new_end = c_end + 0.2
            new_dur = new_end - new_start
            new_ratio = new_dur / clip['original_duration']
            if abs(new_ratio - 1.0) <= max_speed_ratio_deviation + 0.05:
                clip['start'] = round(new_start, 3)
                clip['end'] = round(new_end, 3)
                clip['duration'] = round(new_dur, 3)
                clip['speed_ratio'] = round(new_ratio, 3)
                logs.append(
                    f"[SANITIZE] Clip #{i+1}: Phat hien vung cat canh day dac ({len(internal_cuts)} cuts), "
                    f"da mo rong nhe bien: {clip['start']}s -> {clip['end']}s"
                )

    logs.append(f"[SANITIZE] Hoan tat toi uu timeline: {len(timeline)} clips goc -> {len(merged_clips)} clips da lam sach.")
    return merged_clips, logs
