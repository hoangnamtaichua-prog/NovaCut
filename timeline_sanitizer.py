import os
import json
import math
import time
import threading
from typing import List, Dict, Tuple, Any, Optional

def refine_scene_cuts_boundary(
    video,
    candidate_cuts: List[float],
    threshold: float = 27.0,
    window_sec: float = 0.5,
    downscale_factor: int = 1
) -> List[float]:
    """
    Giai đoạn 2 (Boundary Refinement):
    Với mỗi điểm cut ứng viên tìm được từ Coarse Scan, quét vi mô trong cửa sổ hẹp
    [cut - window_sec, cut + window_sec] với frame_skip=0 (kiểm tra từng frame).
    Đảm bảo phát hiện mốc chuyển cảnh chính xác 100% từng frame mà không bị trôi do frame_skip.
    """
    if not candidate_cuts:
        return []
    
    try:
        from scenedetect import SceneManager, ContentDetector
    except ImportError:
        return candidate_cuts

    duration_sec = 0.0
    if video.duration and hasattr(video.duration, 'seconds'):
        duration_sec = float(video.duration.seconds)
    elif video.duration and hasattr(video.duration, 'get_seconds'):
        duration_sec = float(video.duration.get_seconds())

    refined_cuts = []
    for cand in candidate_cuts:
        w_start = max(0.0, cand - window_sec)
        w_end = min(duration_sec, cand + window_sec) if duration_sec > 0 else (cand + window_sec)
        
        if w_end <= w_start + 0.04:
            refined_cuts.append(round(cand, 3))
            continue
            
        try:
            sm_refine = SceneManager()
            sm_refine.auto_downscale = False
            sm_refine.downscale = downscale_factor
            sm_refine.add_detector(ContentDetector(threshold=threshold))
            # frame_skip=0: Đọc từng frame để đạt độ chính xác frame-accurate
            sm_refine.detect_scenes(video, frame_skip=0, start_time=w_start, end_time=w_end)
            scenes = sm_refine.get_scene_list()
            
            best_cut = cand
            min_dist = float('inf')
            for s in scenes:
                t = round(s[0].seconds, 3)
                dist = abs(t - cand)
                if dist < min_dist and dist <= window_sec:
                    min_dist = dist
                    best_cut = t
            refined_cuts.append(round(best_cut, 3))
        except Exception:
            refined_cuts.append(round(cand, 3))

    # Loại bỏ duplicate và sort
    return sorted(list(set(refined_cuts)))


def extract_scene_cuts_with_progress(
    video_path: str,
    threshold: float = 27.0,
    cache_dir: str = 'output/auto_edit_temp',
    check_stop_func = None,
    target_timeline: List[Dict[str, Any]] = None,
    enable_refinement: bool = True
):
    """
    Quét video gốc để phát hiện các điểm chuyển cảnh (scene cuts) tự nhiên bằng PySceneDetect.
    Kiến trúc 2 giai đoạn:
    1. Coarse scan: Boundary-targeted scan quanh các mốc timeline với frame_skip=2 + downscale 360p.
    2. Boundary refinement: Quét vi mô quanh từng điểm cắt với frame_skip=0 (chính xác từng frame).
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
    refine_flag = "refined2stage" if enable_refinement else "coarse"
    cache_hash = hashlib.md5(f"{video_path}_{file_size}_{mtime}_{threshold}_{refine_flag}".encode()).hexdigest()[:10]
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
        frame_skip = 2  # Quét 1 frame mỗi 3 frame cho giai đoạn Coarse Scan

        # Xây dựng danh sách các cửa sổ biên cần quét (Boundary Windows) nếu có target_timeline
        merged_windows = []
        if target_timeline and isinstance(target_timeline, list) and len(target_timeline) > 0:
            raw_windows = []
            for clip in target_timeline:
                v_s = float(clip.get('source_start') or clip.get('start', 0))
                v_d = float(clip.get('source_duration') or clip.get('duration', 0))
                raw_windows.append((max(0.0, v_s - 1.5), min(duration_sec, v_s + 1.5)))
                raw_windows.append((max(0.0, v_s + v_d - 1.5), min(duration_sec, v_s + v_d + 1.5)))
            
            raw_windows.sort(key=lambda x: x[0])
            for w in raw_windows:
                if not merged_windows or w[0] > merged_windows[-1][1]:
                    merged_windows.append([w[0], w[1]])
                else:
                    merged_windows[-1][1] = max(merged_windows[-1][1], w[1])

        coarse_cuts = []

        if merged_windows:
            # Giai đoạn 1: Quét siêu tốc theo từng cửa sổ biên (Boundary-Targeted Scan)
            total_win = len(merged_windows)
            for idx, (win_s, win_e) in enumerate(merged_windows):
                if check_stop_func and check_stop_func():
                    yield ("Đã dừng quét chuyển cảnh theo yêu cầu.", [])
                    return
                
                win_pct = int((idx + 1) / total_win * 80)
                if idx % 5 == 0 or idx == total_win - 1:
                    yield (f"Đang quét chuyển cảnh sơ bộ (Pha 1): {win_pct}% (Cửa sổ {idx+1}/{total_win} - phát hiện {len(coarse_cuts)} điểm)...", None)

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
                            coarse_cuts.append(cut_t)
                except Exception:
                    pass
            
            candidate_cuts = sorted(list(set(coarse_cuts)))
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
                pct = min(80, int((cur_frame / max(1, total_frames)) * 80))
                now = time.time()

                if (pct >= last_reported_pct + 5 or (now - last_report_time > 2.0 and pct > last_reported_pct)):
                    cuts_found = len(sm.get_scene_list())
                    yield (f"Đang quét chuyển cảnh (Pha 1): {pct}% ({cur_sec:.0f}s / {duration_sec:.0f}s - phát hiện {cuts_found} cảnh)...", None)
                    last_reported_pct = pct
                    last_report_time = now

                time.sleep(0.1)

            worker.join()

            if error_holder:
                yield (f"⚠️ Lỗi quét chuyển cảnh ({error_holder[0]}). Tiếp tục với timeline gốc.", [])
                return

            scenes = sm.get_scene_list()
            candidate_cuts = [round(s[0].seconds, 3) for i, s in enumerate(scenes) if i > 0]

        # Giai đoạn 2: Tinh chỉnh biên chính xác (Boundary Refinement với frame_skip=0)
        final_cuts = candidate_cuts
        if enable_refinement and candidate_cuts:
            yield (f"🎯 Pha 2: Tinh chỉnh chính xác {len(candidate_cuts)} điểm cắt (Accurate Frame Refinement)...", None)
            final_cuts = refine_scene_cuts_boundary(
                video=video,
                candidate_cuts=candidate_cuts,
                threshold=threshold,
                window_sec=0.4,
                downscale_factor=downscale_factor
            )

        # Lưu cache
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(final_cuts, f, indent=2)
        except Exception:
            pass

        yield (f"Đã nhận diện {len(final_cuts)} điểm chuyển cảnh vật lý chuẩn xác trong video gốc.", final_cuts)

    except Exception as e:
        yield (f"⚠️ PySceneDetect: {e}. Bỏ qua snap cảnh.", [])


def extract_scene_cuts(video_path: str, threshold: float = 27.0, cache_dir: str = 'output/auto_edit_temp') -> List[float]:
    """Hàm đồng bộ trả về kết quả cuts (dùng cho các module khác nếu cần)."""
    result = []
    for _, cuts in extract_scene_cuts_with_progress(video_path, threshold=threshold, cache_dir=cache_dir):
        if cuts is not None:
            result = cuts
    return result


def find_nearest_cut(time_val: float, scene_cuts: List[float], max_dist: float) -> Tuple[Optional[float], float]:
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


def resolve_timeline_with_voice_clock(
    timeline: List[Dict[str, Any]],
    voice_entries: List[Any],
    scene_cuts: Optional[List[float]] = None,
    snap_threshold: float = 0.6,
    min_clip_duration: float = 1.2,
    min_speed: float = 0.85,
    max_speed: float = 1.20,
    dense_cut_threshold: int = 3
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    DETERMINISTIC TIMELINE RESOLVER:
    Lấy Voice SRT làm MASTER CLOCK bất biến.
    Quyết định mốc cắt cuối cùng, tốc độ video, đảm bảo đồng bộ hoàn hảo từng câu:
    - Schema đầy đủ: source_start, source_end, voice_start, voice_end, voice_duration,
      video_duration, video_speed, audio_tempo, voice_ref, voice_refs, subsegments, sync_error_ms.
    - Snap vào scene cuts chính xác.
    - Áp dụng video_speed để video_duration đúng 100% bằng voice_duration.
    - Bảo toàn mapping voice_refs và subsegments khi gộp clip ngắn.
    """
    logs: List[str] = []
    if not timeline:
        return [], logs

    if scene_cuts is None:
        scene_cuts = []

    # 1. Chuẩn hóa voice_entries thành dict tra cứu {ref: (voice_start, voice_end, text)}
    voice_clock_map: Dict[int, Dict[str, Any]] = {}
    if voice_entries:
        for idx, entry in enumerate(voice_entries):
            ref = idx + 1
            if isinstance(entry, (tuple, list)) and len(entry) >= 2:
                v_s = float(entry[0])
                v_e = float(entry[1])
                v_txt = str(entry[2]) if len(entry) >= 3 else ""
            elif isinstance(entry, dict):
                ref = int(entry.get('voice_ref') or entry.get('ref') or (idx + 1))
                v_s = float(entry.get('voice_start') or entry.get('start', 0.0))
                v_e = float(entry.get('voice_end') or entry.get('end', v_s + 2.0))
                v_txt = str(entry.get('text', ''))
            else:
                v_s = float(idx * 2.5)
                v_e = float(v_s + 2.5)
                v_txt = ""

            v_dur = max(0.05, round(v_e - v_s, 3))
            voice_clock_map[ref] = {
                "voice_start": round(v_s, 3),
                "voice_end": round(v_e, 3),
                "voice_duration": v_dur,
                "text": v_txt
            }

    # 2. Xây dựng phân đoạn ban đầu từ LLM và Voice Clock
    initial_segments = []
    for i, item in enumerate(timeline):
        raw_ref = item.get('voice_ref', i + 1)
        try:
            v_ref = int(raw_ref)
        except Exception:
            v_ref = i + 1

        # Lấy mốc thời gian giọng đọc chuẩn
        if v_ref in voice_clock_map:
            v_info = voice_clock_map[v_ref]
            v_start = v_info["voice_start"]
            v_end = v_info["voice_end"]
            v_dur = v_info["voice_duration"]
            v_txt = v_info["text"]
        else:
            v_dur = float(item.get('voice_duration') or item.get('duration') or 2.5)
            if v_dur <= 0:
                v_dur = 2.5
            v_start = float(item.get('voice_start', 0.0))
            v_end = round(v_start + v_dur, 3)
            v_txt = str(item.get('text', ''))

        # Lấy mốc video nguồn gợi ý từ LLM
        raw_s_start = float(item.get('source_start') if item.get('source_start') is not None else item.get('start', 0.0))
        raw_s_end = float(item.get('source_end') if item.get('source_end') is not None else item.get('end', raw_s_start + v_dur))
        if raw_s_end <= raw_s_start:
            raw_s_end = raw_s_start + v_dur

        # 3. Snap start/end vào Scene Cuts
        snapped_s = raw_s_start
        snapped_e = raw_s_end
        start_snapped = False
        end_snapped = False

        if scene_cuts:
            near_s, dist_s = find_nearest_cut(raw_s_start, scene_cuts, snap_threshold)
            if near_s is not None and near_s >= 0:
                snapped_s = near_s
                start_snapped = True

            near_e, dist_e = find_nearest_cut(raw_s_end, scene_cuts, snap_threshold)
            if near_e is not None and near_e > snapped_s + 0.2:
                snapped_e = near_e
                end_snapped = True

        raw_cut_dur = max(0.1, snapped_e - snapped_s)
        # Tốc độ video cần thiết để chiếu hết raw_cut_dur trong thời gian v_dur:
        # speed = raw_cut_dur / v_dur. Nếu speed = 1.0 -> phát bình thường.
        req_speed = raw_cut_dur / v_dur

        # Kiểm tra ngưỡng an toàn của tốc độ
        if min_speed <= req_speed <= max_speed:
            final_s = snapped_s
            final_e = snapped_e
            final_source_dur = round(raw_cut_dur, 3)
            final_speed = round(req_speed, 4)
            is_snapped = start_snapped or end_snapped
            if is_snapped:
                logs.append(
                    f"[RESOLVER] Clip #{i+1} (voice_ref={v_ref}): Snap scene cut thành công! "
                    f"[{raw_s_start:.2f}s -> {final_s:.2f}s, {raw_s_end:.2f}s -> {final_e:.2f}s], "
                    f"Tốc độ bù: {final_speed:.2f}x (chuẩn voice {v_dur:.2f}s)."
                )
        else:
            # Lệch tốc độ quá lớn: Hủy snap biên gây lệch nhiều nhất hoặc điều chỉnh để giữ nhịp tự nhiên
            logs.append(
                f"[RESOLVER] Clip #{i+1} (voice_ref={v_ref}): Tốc độ snap {req_speed:.2f}x vượt ngưỡng an toàn "
                f"[{min_speed:.2f}x - {max_speed:.2f}x]. Giữ tốc độ chuẩn 1.0x để đảm bảo tự nhiên."
            )
            final_s = raw_s_start
            final_source_dur = round(v_dur * 1.0, 3)
            final_e = round(final_s + final_source_dur, 3)
            final_speed = 1.0
            is_snapped = False

        # Target video duration đầu ra sau khi setpts: Luôn bằng v_dur
        video_dur = v_dur
        sync_error = round(abs(video_dur - v_dur) * 1000.0, 2)

        initial_segments.append({
            "id": i + 1,
            "voice_ref": v_ref,
            "voice_refs": [v_ref],
            "subsegments": [{
                "voice_ref": v_ref,
                "voice_start": v_start,
                "voice_end": v_end,
                "voice_duration": v_dur,
                "text": v_txt
            }],
            "source_start": round(final_s, 3),
            "source_end": round(final_e, 3),
            "source_duration": round(final_e - final_s, 3),
            "voice_start": v_start,
            "voice_end": v_end,
            "voice_duration": v_dur,
            "video_duration": round(video_dur, 3),
            "video_speed": final_speed,
            "audio_tempo": 1.0,
            "sync_error_ms": sync_error,
            "is_snapped": is_snapped,
            # Backward compatibility fields:
            "start": round(final_s, 3),
            "end": round(final_e, 3),
            "duration": round(video_dur, 3),
            "original_duration": round(v_dur, 3),
            "speed_ratio": final_speed,
            "raw_start": round(raw_s_start, 3),
            "raw_end": round(raw_s_end, 3)
        })

    # 4. Gộp các clip quá ngắn (< min_clip_duration) nhưng BẢO TOÀN ĐẦY ĐỦ voice_refs và subsegments
    merged_clips: List[Dict[str, Any]] = []
    skip_indices = set()
    
    idx = 0
    while idx < len(initial_segments):
        if idx in skip_indices:
            idx += 1
            continue
            
        curr = dict(initial_segments[idx])
        
        # Nếu clip quá ngắn và có clip tiếp theo -> Gộp vào clip sau
        if curr['video_duration'] < min_clip_duration and idx + 1 < len(initial_segments):
            nxt = initial_segments[idx + 1]
            combined_voice_dur = round(curr['voice_duration'] + nxt['voice_duration'], 3)
            combined_voice_refs = curr['voice_refs'] + nxt['voice_refs']
            combined_subsegments = curr['subsegments'] + nxt['subsegments']
            
            # Kết hợp vùng video nguồn
            # Nếu liền kề hoặc tiến tới
            if abs(nxt['source_start'] - curr['source_end']) <= 1.5 and nxt['source_end'] > curr['source_start']:
                merged_s_start = curr['source_start']
                merged_s_end = nxt['source_end']
            else:
                merged_s_start = curr['source_start']
                merged_s_end = max(curr['source_end'], merged_s_start + combined_voice_dur)

            merged_s_dur = max(0.1, merged_s_end - merged_s_start)
            merged_speed = round(merged_s_dur / combined_voice_dur, 4)
            # Giới hạn speed trong khoảng an toàn
            if merged_speed < min_speed or merged_speed > max_speed:
                merged_speed = 1.0
                merged_s_dur = combined_voice_dur
                merged_s_end = round(merged_s_start + merged_s_dur, 3)

            logs.append(
                f"[RESOLVER] Gộp clip ngắn #{idx+1} ({curr['video_duration']:.2f}s) vào clip #{idx+2}. "
                f"Đã bảo toàn voice_refs={combined_voice_refs}, tổng voice: {combined_voice_dur:.2f}s."
            )

            merged_clips.append({
                "id": len(merged_clips) + 1,
                "voice_ref": combined_voice_refs[0],
                "voice_refs": combined_voice_refs,
                "subsegments": combined_subsegments,
                "source_start": round(merged_s_start, 3),
                "source_end": round(merged_s_end, 3),
                "source_duration": round(merged_s_dur, 3),
                "voice_start": curr['voice_start'],
                "voice_end": nxt['voice_end'],
                "voice_duration": combined_voice_dur,
                "video_duration": combined_voice_dur,
                "video_speed": merged_speed,
                "audio_tempo": 1.0,
                "sync_error_ms": 0.0,
                "is_snapped": curr['is_snapped'] or nxt['is_snapped'],
                # Backward compatibility:
                "start": round(merged_s_start, 3),
                "end": round(merged_s_end, 3),
                "duration": combined_voice_dur,
                "original_duration": combined_voice_dur,
                "speed_ratio": merged_speed,
                "raw_start": curr['raw_start'],
                "raw_end": nxt['raw_end']
            })
            skip_indices.add(idx + 1)
            idx += 2
            continue
        elif curr['video_duration'] < min_clip_duration and len(merged_clips) > 0:
            # Gộp vào clip liền trước nếu là clip cuối cùng
            prev = merged_clips[-1]
            combined_voice_dur = round(prev['voice_duration'] + curr['voice_duration'], 3)
            prev['voice_refs'].extend(curr['voice_refs'])
            prev['subsegments'].extend(curr['subsegments'])
            prev['voice_end'] = curr['voice_end']
            prev['voice_duration'] = combined_voice_dur
            prev['video_duration'] = combined_voice_dur
            prev['duration'] = combined_voice_dur
            prev['original_duration'] = combined_voice_dur
            
            # Mở rộng video nguồn của clip trước
            prev_s_dur = max(0.1, prev['source_end'] - prev['source_start'])
            curr_s_dur = max(0.1, curr['source_end'] - curr['source_start'])
            new_s_end = round(prev['source_end'] + curr_s_dur, 3)
            prev['source_end'] = new_s_end
            prev['end'] = new_s_end
            prev['source_duration'] = round(new_s_end - prev['source_start'], 3)
            
            # Recalculate speed
            new_speed = round(prev['source_duration'] / combined_voice_dur, 4)
            if new_speed < min_speed or new_speed > max_speed:
                new_speed = 1.0
                prev['source_end'] = round(prev['source_start'] + combined_voice_dur, 3)
                prev['end'] = prev['source_end']
                prev['source_duration'] = combined_voice_dur
            prev['video_speed'] = new_speed
            prev['speed_ratio'] = new_speed

            logs.append(
                f"[RESOLVER] Gộp clip cuối #{idx+1} ({curr['video_duration']:.2f}s) vào clip liền trước #{len(merged_clips)}."
            )
            idx += 1
            continue
        else:
            merged_clips.append(curr)
            idx += 1

    # 5. Xử lý vùng scene cut dày đặc (Dense Cut Zone)
    if scene_cuts:
        for i, clip in enumerate(merged_clips):
            c_s = clip['source_start']
            c_e = clip['source_end']
            internal_cuts = [c for c in scene_cuts if c_s + 0.1 < c < c_e - 0.1]
            if len(internal_cuts) >= dense_cut_threshold and clip['video_duration'] <= 3.0:
                # Mở rộng nhẹ 0.2s hai đầu để không bị cụt pha hành động
                new_s = max(0.0, c_s - 0.2)
                new_e = c_e + 0.2
                new_src_dur = new_e - new_s
                new_speed = round(new_src_dur / clip['voice_duration'], 4)
                if min_speed <= new_speed <= max_speed:
                    clip['source_start'] = round(new_s, 3)
                    clip['source_end'] = round(new_e, 3)
                    clip['source_duration'] = round(new_src_dur, 3)
                    clip['start'] = clip['source_start']
                    clip['end'] = clip['source_end']
                    clip['video_speed'] = new_speed
                    clip['speed_ratio'] = new_speed
                    logs.append(
                        f"[RESOLVER] Clip #{i+1}: Vùng cắt cảnh dày đặc ({len(internal_cuts)} cuts), "
                        f"đã mở rộng nhẹ biên: [{clip['source_start']}s -> {clip['source_end']}s]"
                    )

    # 6. Đảm bảo tính tuần tự thời gian và không trùng lặp cảnh
    enforced_clips, order_logs = enforce_chronological_and_unique_timeline(merged_clips, scene_cuts=scene_cuts)
    logs.extend(order_logs)

    # Cập nhật ID chuẩn
    for idx_c, clip in enumerate(enforced_clips):
        clip['id'] = idx_c + 1

    logs.append(
        f"[RESOLVER] Hoàn tất Deterministic Resolver: {len(timeline)} mẻ gốc -> {len(enforced_clips)} clips chuẩn hóa "
        f"(Khớp 100% Voice Master Clock, video_duration == voice_duration)."
    )
    return enforced_clips, logs


def validate_timeline(
    timeline: List[Dict[str, Any]],
    max_p95_error_ms: float = 80.0,
    max_single_error_ms: float = 150.0
) -> Tuple[bool, Dict[str, Any]]:
    """
    PRE-RENDER VALIDATOR:
    Kiểm tra tính toàn vẹn và độ chính xác của timeline trước khi thực hiện render:
    - Tổng thời lượng video so với voice
    - Sai số đồng bộ từng đoạn (P95, Max)
    - Kiểm tra giới hạn tốc độ biến đổi video (video_speed)
    - Phát hiện clip rỗng, duration <= 0, hoặc đảo ngược thời gian
    """
    report = {
        "is_valid": True,
        "total_clips": len(timeline),
        "total_voice_duration": 0.0,
        "total_video_duration": 0.0,
        "total_drift_ms": 0.0,
        "p95_sync_error_ms": 0.0,
        "max_sync_error_ms": 0.0,
        "speed_violations": [],
        "errors": [],
        "warnings": []
    }

    if not timeline:
        report["is_valid"] = False
        report["errors"].append("Timeline rỗng không có clip nào.")
        return False, report

    total_voice = 0.0
    total_video = 0.0
    errors_ms = []

    for i, clip in enumerate(timeline):
        v_dur = float(clip.get('voice_duration', clip.get('duration', 0.0)))
        vid_dur = float(clip.get('video_duration', clip.get('duration', 0.0)))
        speed = float(clip.get('video_speed', clip.get('speed_ratio', 1.0)))
        s_start = float(clip.get('source_start', clip.get('start', 0.0)))
        s_end = float(clip.get('source_end', clip.get('end', 0.0)))

        if vid_dur <= 0 or v_dur <= 0:
            report["is_valid"] = False
            report["errors"].append(f"Clip #{i+1}: Thời lượng không hợp lệ (video={vid_dur}s, voice={v_dur}s).")

        if s_end <= s_start:
            report["is_valid"] = False
            report["errors"].append(f"Clip #{i+1}: Điểm kết thúc nhỏ hơn điểm bắt đầu ({s_start}s -> {s_end}s).")

        # Kiểm tra tốc độ vượt quá giới hạn an toàn
        if speed < 0.65 or speed > 1.40:
            report["speed_violations"].append({
                "clip_idx": i + 1,
                "speed": speed,
                "voice_duration": v_dur,
                "source_duration": round(s_end - s_start, 3)
            })
            report["warnings"].append(f"Clip #{i+1}: Tốc độ {speed:.2f}x biến đổi mạnh, có thể gây cảm giác nhanh/chậm.")

        total_voice += v_dur
        total_video += vid_dur
        err_ms = float(clip.get('sync_error_ms', abs(vid_dur - v_dur) * 1000.0))
        errors_ms.append(err_ms)

    report["total_voice_duration"] = round(total_voice, 3)
    report["total_video_duration"] = round(total_video, 3)
    total_drift = abs(total_video - total_voice) * 1000.0
    report["total_drift_ms"] = round(total_drift, 2)

    if errors_ms:
        sorted_errs = sorted(errors_ms)
        p95_idx = int(math.ceil(0.95 * len(sorted_errs))) - 1
        p95_idx = max(0, min(p95_idx, len(sorted_errs) - 1))
        report["p95_sync_error_ms"] = round(sorted_errs[p95_idx], 2)
        report["max_sync_error_ms"] = round(max(sorted_errs), 2)

    # Đánh giá giới hạn chất lượng
    if total_drift > max_p95_error_ms:
        report["warnings"].append(
            f"Tổng độ lệch video-voice ({total_drift:.1f}ms) lớn hơn ngưỡng khuyến nghị ({max_p95_error_ms:.1f}ms)."
        )

    if report["max_sync_error_ms"] > max_single_error_ms:
        report["warnings"].append(
            f"Sai số lớn nhất ({report['max_sync_error_ms']:.1f}ms) vượt ngưỡng tối đa {max_single_error_ms:.1f}ms."
        )

    if len(report["errors"]) > 0:
        report["is_valid"] = False

    return report["is_valid"], report


def sanitize_timeline(
    timeline: List[Dict[str, Any]],
    scene_cuts: List[float],
    snap_threshold: float = 0.6,
    min_clip_duration: float = 1.2,
    max_speed_ratio_deviation: float = 0.15,
    dense_cut_threshold: int = 3,
    voice_entries: Optional[List[Any]] = None
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Wrapper tương thích ngược.
    Nếu có voice_entries -> Sử dụng resolve_timeline_with_voice_clock để đạt độ chính xác tối đa.
    Nếu không có voice_entries -> Dựng voice entries từ duration có sẵn.
    """
    if voice_entries:
        return resolve_timeline_with_voice_clock(
            timeline=timeline,
            voice_entries=voice_entries,
            scene_cuts=scene_cuts,
            snap_threshold=snap_threshold,
            min_clip_duration=min_clip_duration,
            min_speed=1.0 - max_speed_ratio_deviation,
            max_speed=1.0 + max_speed_ratio_deviation,
            dense_cut_threshold=dense_cut_threshold
        )

    # Fallback khi chưa có voice_entries: Tự tạo clock giả lập từ timeline
    mock_voice_entries = []
    accum_t = 0.0
    for i, item in enumerate(timeline):
        d = float(item.get('duration') or item.get('original_duration') or 2.5)
        if d <= 0:
            d = max(0.5, float(item.get('end', 0.0) - item.get('start', 0.0)))
        mock_voice_entries.append((accum_t, accum_t + d, f"Sentence {i+1}"))
        accum_t += d

    return resolve_timeline_with_voice_clock(
        timeline=timeline,
        voice_entries=mock_voice_entries,
        scene_cuts=scene_cuts,
        snap_threshold=snap_threshold,
        min_clip_duration=min_clip_duration,
        min_speed=1.0 - max_speed_ratio_deviation,
        max_speed=1.0 + max_speed_ratio_deviation,
        dense_cut_threshold=dense_cut_threshold
    )


def enforce_chronological_and_unique_timeline(
    timeline: List[Dict[str, Any]],
    scene_cuts: List[float] = None,
    min_step_gap: float = 0.0
) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Bảo đảm quy tắc dựng phim Movie Review cốt lõi:
    1. Cảnh cắt luôn tuân theo trình tự thời gian tiến dần (Chronological Order):
       source_start[i] >= source_end[i-1] + min_step_gap. Tuyệt đối không cho cảnh ở thời gian sau nhảy lên trước.
    2. Một cảnh cắt chỉ xuất hiện DUY NHẤT 1 LẦN trong toàn bộ video review:
       Tuyệt đối không lặp lại đoạn thời gian hoặc chồng lấn (overlap) lên cảnh đã dùng trước đó.
    3. Bảo toàn đầy đủ tất cả các trường schema chuẩn và voice master clock.
    """
    logs = []
    if not timeline:
        return [], logs

    sorted_timeline = sorted(timeline, key=lambda x: int(x.get('voice_ref', 0)))
    result = []
    
    current_movie_time = 0.0
    adjusted_count = 0
    rewind_prevented_count = 0

    for idx, item in enumerate(sorted_timeline):
        clip = dict(item)
        target_video_dur = float(clip.get('video_duration') or clip.get('duration') or 2.0)
        v_dur = float(clip.get('voice_duration') or target_video_dur)
        if target_video_dur <= 0:
            target_video_dur = 2.0
            v_dur = 2.0

        orig_src_start = float(clip.get('source_start', clip.get('start', 0.0)))
        orig_src_end = float(clip.get('source_end', clip.get('end', orig_src_start + target_video_dur)))
        src_dur = max(0.1, orig_src_end - orig_src_start)

        # 1. Kiểm tra lùi thời gian (Chronological violation: source_start < current_movie_time)
        if orig_src_start < current_movie_time:
            rewind_prevented_count += 1
            # Đẩy start tiến lên mốc current_movie_time
            new_s_start = current_movie_time + min_step_gap
            
            # Tìm scene cut hợp lệ đầu tiên ở phía sau new_s_start
            if scene_cuts:
                next_cuts = [c for c in scene_cuts if c >= new_s_start]
                if next_cuts and (next_cuts[0] - new_s_start) <= 2.0:
                    new_s_start = next_cuts[0]
            
            new_s_end = new_s_start + src_dur
            adjusted_count += 1
            logs.append(
                f"[ORDER-GUARD] Clip #{idx+1} (voice_ref={clip.get('voice_ref')}): Phát hiện nhảy lùi thời gian "
                f"({orig_src_start:.2f}s < mốc hiện tại {current_movie_time:.2f}s). "
                f"Đã đẩy tiến mốc cắt nguồn: [{new_s_start:.2f}s -> {new_s_end:.2f}s]"
            )
        else:
            new_s_start = orig_src_start
            new_s_end = orig_src_start + src_dur
            if new_s_start < current_movie_time:
                new_s_start = current_movie_time
                new_s_end = new_s_start + src_dur
                adjusted_count += 1

        new_src_dur = round(new_s_end - new_s_start, 3)
        calc_speed = round(new_src_dur / v_dur, 4) if v_dur > 0 else 1.0

        # Cập nhật mốc nguồn & đồng bộ
        clip['source_start'] = round(new_s_start, 3)
        clip['source_end'] = round(new_s_end, 3)
        clip['source_duration'] = new_src_dur
        clip['voice_duration'] = round(v_dur, 3)
        clip['video_duration'] = round(v_dur, 3)
        clip['video_speed'] = calc_speed
        clip['sync_error_ms'] = 0.0

        # Backward compatibility
        clip['start'] = clip['source_start']
        clip['end'] = clip['source_end']
        clip['duration'] = clip['video_duration']
        clip['speed_ratio'] = clip['video_speed']

        current_movie_time = new_s_end
        result.append(clip)

    if adjusted_count > 0:
        logs.append(
            f"[ORDER-GUARD] Hoàn tất chuẩn hóa tuyến tính: Ngăn chặn {rewind_prevented_count} lần nhảy lùi cảnh, "
            f"điều chỉnh {adjusted_count}/{len(timeline)} clips để đảm bảo 100% không trùng lặp và luôn tiến dần."
        )

    return result, logs
