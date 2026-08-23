import os
import sys
import subprocess
import json
import time
import requests
import wave
import array
import hashlib
import shutil
import concurrent.futures
import ffmpeg_installer

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

def synthesize_sentence(text, voice_id, speed, output_path, open_speaker_key=None):
    """
    Synthesizes speech for a single text sentence using RVC (Custom Clone), Kokoro (offline), Edge AI or OpenSpeaker (online).
    """
    import vietnamese_text_normalizer
    text = vietnamese_text_normalizer.normalize_text_for_tts(text)

    # 0. Local Voice Engine (High Quality Preset & Instant Cloned Voices)
    import custom_voices
    voice_profile = custom_voices.get_voice_by_id(voice_id)
    if (voice_profile and voice_profile.get('provider') == 'local_voice') or voice_id.startswith('local_'):
        try:
            import local_voice_engine
            return local_voice_engine.synthesize(text=text, voice_id=voice_id, speed=speed, output_path=output_path)
        except Exception as e:
            print(f"[Local Voice] Synthesis error: {e}, falling back to Edge-TTS...")
            edge_fallback = "edge_vi-VN-HoaiMyNeural" if any(f in voice_id for f in ['huyen', 'trinh', 'linh', 'ly', 'ngoc', 'female']) else "edge_vi-VN-NamMinhNeural"
            return synthesize_sentence(text, edge_fallback, speed, output_path, open_speaker_key)

    # 0.1. RVC Voice Clone (Custom Trained Models)
    rvc_profile = voice_profile
    if (rvc_profile and rvc_profile.get('provider') == 'rvc') or voice_id.startswith('rvc_'):
        base_voice = rvc_profile.get('base_voice', 'edge_vi-VN-HoaiMyNeural') if rvc_profile else 'edge_vi-VN-HoaiMyNeural'
        temp_base_audio = os.path.join(os.path.dirname(os.path.abspath(output_path)), f"temp_base_{int(time.time()*1000)}.wav")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            model_path = rvc_profile.get('model_path') if rvc_profile else None
            if not model_path or not os.path.exists(model_path):
                print(f"[RVC] Không tìm thấy tệp model RVC ({model_path}), tự động chuyển sang giọng đọc Local Voice ONNX...")
                try:
                    import local_voice_engine
                    return local_voice_engine.synthesize(text=text, voice_id="local_ngoc_huyen", speed=speed, output_path=output_path)
                except Exception:
                    return synthesize_sentence(text, "edge_vi-VN-HoaiMyNeural", speed, output_path)

            synthesize_sentence(text, base_voice, speed, temp_base_audio, open_speaker_key)
            
            import rvc_bridge
            index_path = rvc_profile.get('index_path') if rvc_profile else None
            pitch = int(rvc_profile.get('pitch', 0)) if rvc_profile else 0
            f0_method = rvc_profile.get('f0_method', 'rmvpe') if rvc_profile else 'rmvpe'
            index_rate = float(rvc_profile.get('index_rate', 0.45)) if rvc_profile else 0.45
            protect = float(rvc_profile.get('protect', 0.50)) if rvc_profile else 0.50
            rms_mix_rate = float(rvc_profile.get('rms_mix_rate', 0.25)) if rvc_profile else 0.25
            
            rvc_bridge.convert_voice(
                input_audio=temp_base_audio,
                output_audio=output_path,
                model_path=model_path,
                index_path=index_path,
                pitch=pitch,
                f0_method=f0_method,
                index_rate=index_rate,
                rms_mix_rate=rms_mix_rate,
                protect=protect
            )
            return output_path
        except Exception as rvc_err:
            print(f"[RVC] Lỗi chuyển đổi giọng RVC ({rvc_err}), fallback sang Local Voice ONNX...")
            try:
                import local_voice_engine
                return local_voice_engine.synthesize(text=text, voice_id="local_ngoc_huyen", speed=speed, output_path=output_path)
            except Exception:
                return synthesize_sentence(text, "edge_vi-VN-HoaiMyNeural", speed, output_path)
        finally:
            if os.path.exists(temp_base_audio):
                try:
                    os.remove(temp_base_audio)
                except:
                    pass

    # 1. Edge AI (Microsoft Neural TTS - Miễn phí không cần API Key) with Retry & Kokoro Fallback
    if voice_id.startswith('edge_'):
        raw_voice = voice_id.replace('edge_', '')
        import asyncio
        import edge_tts
        
        rate_val = int(round((speed - 1.0) * 100))
        rate_str = f"{rate_val:+d}%"
        
        success = False
        last_err = None
        for attempt in range(3):
            try:
                async def run_edge():
                    communicate = edge_tts.Communicate(text, raw_voice, rate=rate_str)
                    await communicate.save(output_path)
                asyncio.run(run_edge())
                if os.path.exists(output_path) and os.path.getsize(output_path) > 500:
                    success = True
                    break
            except Exception as e:
                last_err = e
                time.sleep(0.5)
                
        if not success:
            print(f"Edge-TTS failed after 3 attempts ({last_err}), automatically falling back to Local Voice offline...")
            try:
                import local_voice_engine
                return local_voice_engine.synthesize(text=text, voice_id="local_ngoc_huyen", speed=speed, output_path=output_path)
            except Exception:
                pass
            kokoro_fallback = 'ngoc_huyen' if 'hoaimy' in raw_voice.lower() or 'female' in raw_voice.lower() else 'manh_dung'
            return synthesize_sentence(text, kokoro_fallback, speed, output_path)
            
        return output_path
        
    # 2. Kokoro / Offline Voices (Ưu tiên Local Voice ONNX Lite 48kHz không cần EXE)
    is_kokoro = voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat', 'en_heart', 'en_michael', 'en_nicole', 'en_adam', 'kokoro']
    
    if is_kokoro or not open_speaker_key:
        # 2.1 Thử Local Voice ONNX Lite Engine trước (In-process, zero-setup)
        try:
            import local_voice_engine
            local_vid = f"local_{voice_id}" if not voice_id.startswith('local_') else voice_id
            return local_voice_engine.synthesize(text=text, voice_id=local_vid, speed=speed, output_path=output_path)
        except Exception as e_lv:
            print(f"[Local Voice ONNX] Thử Kokoro EXE vì: {e_lv}")

        # 2.2 Kiểm tra file thực thi Kokoro EXE
        kokoro_candidates = [
            os.path.join(os.path.dirname(sys.executable), "bin", "kokoro-vietnamese-onnx.exe"),
            os.path.join(ROOT_DIR, "bin", "kokoro-vietnamese-onnx.exe"),
            os.path.join(os.environ.get('USERPROFILE', ''), 'AppData', 'Local', 'Programs', 'Python', 'Python312', 'Scripts', 'kokoro-vietnamese-onnx.exe'),
            shutil.which("kokoro-vietnamese-onnx.exe"),
            shutil.which("kokoro-vietnamese-onnx")
        ]
        kokoro_exe = None
        for cand in kokoro_candidates:
            if cand and os.path.exists(cand):
                kokoro_exe = cand
                break

        if kokoro_exe:
            voice_target = voice_id if voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc'] else 'ngoc_huyen'
            cmd = [
                kokoro_exe,
                "--text", text,
                "--output", output_path,
                "--voice", voice_target,
                "--speed", str(speed),
                "--device", "cpu"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', creationflags=0x08000000 if os.name == 'nt' else 0)
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return output_path

        # 2.3 Fallback an toàn sang Edge-TTS Miễn phí (Không cần API Key)
        fallback_edge_voice = "edge_vi-VN-HoaiMyNeural" if any(f in voice_id for f in ['huyen', 'trinh', 'linh', 'heart', 'nicole']) else "edge_vi-VN-NamMinhNeural"
        return synthesize_sentence(text, fallback_edge_voice, speed, output_path)
    else:
        # 3. Call OpenSpeaker (with Retry & Kokoro Fallback)
        last_error = None
        for attempt in range(3):
            try:
                res = requests.post(
                    "https://api.ai33.pro/v3/text-to-speech",
                    headers={"xi-api-key": open_speaker_key},
                    data={"text": text, "voice_id": voice_id, "speed": speed, "with_transcript": "false"},
                    timeout=30
                )
                res_data = res.json()
                if not res_data.get('success'):
                    raise Exception(f"OpenSpeaker API: {res_data.get('error_message') or res.text}")
                    
                task_id = res_data.get('task_id')
                if not task_id:
                    raise Exception("Không nhận được task_id từ OpenSpeaker API")
                    
                for _ in range(40):
                    time.sleep(1.0)
                    st_res = requests.get(f"https://api.ai33.pro/v1/task/{task_id}", headers={"xi-api-key": open_speaker_key}, timeout=20)
                    st_data = st_res.json()
                    if st_data.get('status') == 'done':
                        audio_url = st_data.get('metadata', {}).get('audio_url')
                        if not audio_url:
                            raise Exception("Không có audio_url trong kết quả OpenSpeaker")
                        aud_res = requests.get(audio_url, timeout=30)
                        with open(output_path, 'wb') as f:
                            f.write(aud_res.content)
                        return output_path
                    elif st_data.get('status') == 'failed':
                        raise Exception(f"OpenSpeaker task failed: {st_data.get('error_message')}")
            except Exception as e:
                last_error = e
                time.sleep(1.0)
                
        # Fallback to Kokoro if OpenSpeaker fails
        print(f"OpenSpeaker failed after 3 attempts ({last_error}), falling back to Kokoro offline for sentence...")
        return synthesize_sentence(text, 'ngoc_huyen', speed, output_path)

def synthesize_openspeaker_with_transcript(text, voice_id, speed, output_audio_path, output_srt_path, open_speaker_key):
    """
    Tạo giọng đọc và phụ đề SRT đồng bộ 1 lần từ OpenSpeaker API.
    """
    import vietnamese_text_normalizer
    text = vietnamese_text_normalizer.normalize_text_for_tts(text)

    def _sec_to_srt(seconds):
        seconds = max(0.0, float(seconds))
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int(round((seconds - int(seconds)) * 1000))
        if ms >= 1000:
            s += 1
            ms -= 1000
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    last_error = None
    for attempt in range(3):
        try:
            res = requests.post(
                "https://api.ai33.pro/v3/text-to-speech",
                headers={"xi-api-key": open_speaker_key},
                data={"text": text, "voice_id": voice_id, "speed": speed, "with_transcript": "true"},
                timeout=60
            )
            res_data = res.json()
            if not res_data.get('success'):
                raise Exception(f"OpenSpeaker API: {res_data.get('error_message') or res.text}")
                
            task_id = res_data.get('task_id')
            if not task_id:
                raise Exception("Không nhận được task_id từ OpenSpeaker API")
                
            for _ in range(90):
                time.sleep(1.0)
                st_res = requests.get(f"https://api.ai33.pro/v1/task/{task_id}", headers={"xi-api-key": open_speaker_key}, timeout=20)
                st_data = st_res.json()
                if st_data.get('status') == 'done':
                    meta = st_data.get('metadata', {})
                    audio_url = meta.get('audio_url')
                    if not audio_url:
                        raise Exception("Không có audio_url trong kết quả OpenSpeaker")
                    
                    # Tải file âm thanh
                    aud_res = requests.get(audio_url, timeout=60)
                    with open(output_audio_path, 'wb') as f:
                        f.write(aud_res.content)
                        
                    # Tải hoặc tạo file SRT
                    srt_url = meta.get('srt_url') or meta.get('transcript_url') or meta.get('subtitles_url')
                    if srt_url:
                        srt_res = requests.get(srt_url, timeout=30)
                        with open(output_srt_path, 'wb') as f:
                            f.write(srt_res.content)
                    elif 'transcript' in meta and isinstance(meta['transcript'], list):
                        with open(output_srt_path, 'w', encoding='utf-8') as sf:
                            for idx, item in enumerate(meta['transcript']):
                                s = float(item.get('start', 0.0))
                                e = float(item.get('end', 0.0))
                                t = str(item.get('text', '')).strip()
                                sf.write(f"{idx+1}\n")
                                sf.write(f"{_sec_to_srt(s)} --> {_sec_to_srt(e)}\n")
                                sf.write(f"{t}\n\n")
                    elif 'words' in meta and isinstance(meta['words'], list):
                        # Gộp các từ thành câu hoặc cụm
                        with open(output_srt_path, 'w', encoding='utf-8') as sf:
                            words = meta['words']
                            chunk_size = 8
                            for i in range(0, len(words), chunk_size):
                                chunk = words[i:i+chunk_size]
                                if not chunk:
                                    continue
                                s = float(chunk[0].get('start', 0.0))
                                e = float(chunk[-1].get('end', s + 1.0))
                                t = ' '.join([w.get('word', w.get('text', '')) for w in chunk]).strip()
                                idx = (i // chunk_size) + 1
                                sf.write(f"{idx}\n")
                                sf.write(f"{_sec_to_srt(s)} --> {_sec_to_srt(e)}\n")
                                sf.write(f"{t}\n\n")
                    else:
                        # Fallback nếu không có transcript riêng: tạo 1 block đơn
                        dur = 5.0
                        try:
                            import ffmpeg_installer
                            ff = ffmpeg_installer.get_ffmpeg_path()
                            p = subprocess.run([ff, '-i', output_audio_path], stderr=subprocess.PIPE, text=True)
                            import re
                            m = re.search(r'Duration:\s*(\d+):(\d+):([0-9.]+)', p.stderr)
                            if m:
                                dur = int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3))
                        except:
                            pass
                        with open(output_srt_path, 'w', encoding='utf-8') as sf:
                            sf.write(f"1\n00:00:00,000 --> {_sec_to_srt(dur)}\n{text}\n")
                    return output_audio_path, output_srt_path
                elif st_data.get('status') == 'failed':
                    raise Exception(f"OpenSpeaker task failed: {st_data.get('error_message')}")
        except Exception as e:
            last_error = e
            time.sleep(1.5)
            
    raise Exception(f"OpenSpeaker thất bại sau 3 lần thử: {last_error}")

def parse_time_str(time_val):
    if isinstance(time_val, (int, float)):
        return float(time_val)
    if not time_val:
        return 0.0
    time_str = str(time_val).strip().replace(',', '.')
    if '-->' in time_str:
        time_str = time_str.split('-->')[0].strip()
    parts = time_str.split(':')
    try:
        if len(parts) == 3:
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return float(parts[0]) * 60 + float(parts[1])
        return float(time_str)
    except Exception:
        return 0.0

def build_dubbing_track_for_subtitles_generator(subtitles, voice_id, speed, temp_dir, open_speaker_key=None, min_total_duration=0.0, max_workers=None, check_stop=None):
    """
    Generator that synthesizes speech with ThreadPoolExecutor and yields real-time progress.
    Hỗ trợ tùy biến số luồng, lưu bộ nhớ đệm (Audio Disk Cache) và tự động thử lại khi nghẽn mạng.
    Hỗ trợ dừng khẩn cấp lập tức (check_stop).
    Yields: ('progress', message)
    Final yield: ('done', output_dubbed_track)
    """
    os.makedirs(temp_dir, exist_ok=True)
    cache_dir = os.path.join(ROOT_DIR, '.cache', 'tts_cache')
    os.makedirs(cache_dir, exist_ok=True)
    ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    
    # Normalize subtitle items
    normalized = []
    for s in subtitles:
        if isinstance(s, (list, tuple)) and len(s) >= 3:
            s_start = parse_time_str(s[0])
            s_end = parse_time_str(s[1])
            s_text = str(s[2]).strip()
            if s_text:
                normalized.append({"text": s_text, "startSeconds": s_start, "endSeconds": s_end})
        elif isinstance(s, dict):
            s_text = (s.get('translation') or s.get('text') or '').strip()
            if not s_text:
                continue
            s_start = s.get('startSeconds')
            if s_start is None:
                s_start = parse_time_str(s.get('time') or s.get('start', 0.0))
            else:
                s_start = float(s_start)
                
            s_end = s.get('endSeconds')
            if s_end is None:
                s_end = s_start + 3.0
            else:
                s_end = float(s_end)
                
            normalized.append({"text": s_text, "startSeconds": s_start, "endSeconds": s_end})

    total = len(normalized)
    if total == 0:
        yield ("progress", "🛑 [LỖI LỒNG TIẾNG] Danh sách phụ đề trống! Không có câu nào để lồng tiếng.")
        yield ("done", None)
        return

    sample_rate = 44100
    channels = 2

    # Check OpenSpeaker key if using OpenSpeaker voice
    is_kokoro = voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'en_heart', 'en_michael', 'en_nicole', 'en_adam', 'kokoro']
    is_edge = voice_id.startswith('edge_')
    is_rvc = voice_id.startswith('rvc_')
    
    if not is_kokoro and not is_edge and not is_rvc and not open_speaker_key:
        yield ("progress", "🛑 [LỖI API KEY] Bạn đang chọn giọng OpenSpeaker nhưng chưa cài đặt API Key trong mục Cài đặt!")
        yield ("done", None)
        return

    # Determine worker threads (Parallel speedup)
    if max_workers is not None and int(max_workers) > 0:
        req_workers = int(max_workers)
        if is_edge:
            actual_workers = max(2, min(req_workers, 16))
        elif is_rvc:
            actual_workers = max(1, min(req_workers, 4))
        elif is_kokoro:
            actual_workers = max(1, min(req_workers, 8))
        else:
            actual_workers = max(4, min(req_workers, 32))
    else:
        if is_edge:
            actual_workers = 12
        elif is_rvc:
            actual_workers = 2
        elif is_kokoro:
            actual_workers = 4
        else:
            actual_workers = 16

    yield ("progress", f"🎙️ Khởi động {actual_workers} luồng tạo giọng song song cho {total} câu phụ đề (Giọng: {voice_id})...")

    def process_one_sub(idx, sub):
        if check_stop and check_stop():
            return (idx, None, sub['startSeconds'], sub['text'], "Đã dừng theo yêu cầu khẩn cấp")

        text = sub['text']
        start_sec = sub['startSeconds']
        part_raw = os.path.join(temp_dir, f"raw_sub_{idx}.wav")
        part_resampled = os.path.join(temp_dir, f"resampled_sub_{idx}.wav")
        
        # 1. Kiểm tra Cache âm thanh trước (Instant 0ms)
        cache_key = hashlib.md5(f"{voice_id}_{speed:.2f}_{text.strip()}".encode('utf-8')).hexdigest()
        cached_file = os.path.join(cache_dir, f"{cache_key}.wav")
        if os.path.exists(cached_file) and os.path.getsize(cached_file) > 100:
            try:
                shutil.copyfile(cached_file, part_resampled)
                return (idx, part_resampled, start_sec, text, None)
            except Exception:
                pass

        if check_stop and check_stop():
            return (idx, None, start_sec, text, "Đã dừng theo yêu cầu khẩn cấp")

        # 2. Tạo giọng với cơ chế Retry 3 lần nếu có lỗi mạng
        last_err = None
        for attempt in range(3):
            if check_stop and check_stop():
                return (idx, None, start_sec, text, "Đã dừng theo yêu cầu khẩn cấp")
            try:
                synthesize_sentence(text, voice_id, speed, part_raw, open_speaker_key)
                if os.path.exists(part_raw) and os.path.getsize(part_raw) > 100:
                    last_err = None
                    break
            except Exception as ex:
                last_err = str(ex)
                time.sleep(0.3 * (attempt + 1))
                
        if not os.path.exists(part_raw) or os.path.getsize(part_raw) <= 100:
            return (idx, None, start_sec, text, last_err or "Không tạo được file âm thanh sau 3 lần thử")

        if check_stop and check_stop():
            return (idx, None, start_sec, text, "Đã dừng theo yêu cầu khẩn cấp")

        try:
            # Resample to 44100Hz 16-bit Stereo WAV
            cmd_resample = [
                ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
                "-i", part_raw,
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-c:a", "pcm_s16le",
                part_resampled
            ]
            subprocess.run(cmd_resample, capture_output=True)
            
            if os.path.exists(part_raw):
                try:
                    os.remove(part_raw)
                except:
                    pass
                    
            if os.path.exists(part_resampled) and os.path.getsize(part_resampled) > 100:
                try:
                    shutil.copyfile(part_resampled, cached_file)
                except:
                    pass
                return (idx, part_resampled, start_sec, text, None)
            return (idx, None, start_sec, text, "File âm thanh bị rỗng sau khi xử lý")
        except Exception as e:
            return (idx, None, start_sec, text, str(e))

    sentence_audios = []
    error_list = []
    completed_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=actual_workers) as executor:
        future_map = {executor.submit(process_one_sub, i, sub): i for i, sub in enumerate(normalized)}
        for future in concurrent.futures.as_completed(future_map):
            if check_stop and check_stop():
                try:
                    executor.shutdown(wait=False, cancel_futures=True)
                except Exception:
                    pass
                yield ("progress", "🛑 Đã hủy bỏ tiến trình tạo giọng AI theo yêu cầu khẩn cấp.")
                yield ("done", None)
                return

            completed_count += 1
            pct = int((completed_count / total) * 100)
            try:
                idx, audio_path, start_s, text, err = future.result()
                if audio_path:
                    sentence_audios.append((audio_path, start_s))
                    yield ("progress", f"🎙️ [{completed_count}/{total}] ({pct}%) Đang tạo giọng: \"{text[:26]}...\" ({start_s:.1f}s)")
                else:
                    error_list.append((idx, text, err))
                    yield ("progress", f"⚠️ [{completed_count}/{total}] Lỗi câu #{idx+1}: {err}")
            except Exception as e:
                error_list.append((0, '', str(e)))
                yield ("progress", f"⚠️ [{completed_count}/{total}] Lỗi xử lý: {str(e)}")

    if not sentence_audios:
        first_err = error_list[0][2] if error_list else "Không thể kết nối đến máy chủ tạo giọng"
        yield ("progress", f"🛑 [LỖI LỒNG TIẾNG] Không có câu nào được tạo thành công! Chi tiết: {first_err}")
        yield ("done", None)
        return

    yield ("progress", f"✨ Đã tạo xong {len(sentence_audios)}/{total} câu. Đang ghép nối vào timeline video...")

    output_dubbed_track = os.path.join(temp_dir, "dubbed_timeline.wav")

    # Pure Python High-Precision PCM Timeline Mixer
    max_time = max(item[1] + 8.0 for item in sentence_audios)
    if min_total_duration and min_total_duration > max_time:
        max_time = float(min_total_duration) + 1.0

    total_samples = int(max_time * sample_rate * channels)
    master_buffer = array.array('h', [0] * total_samples)

    for wav_file, start_s in sentence_audios:
        try:
            with wave.open(wav_file, 'rb') as wf:
                n_frames = wf.getnframes()
                raw_bytes = wf.readframes(n_frames)
                clip_data = array.array('h')
                clip_data.frombytes(raw_bytes)
                
                offset_idx = int(start_s * sample_rate) * channels
                for s_i, sample_val in enumerate(clip_data):
                    target_i = offset_idx + s_i
                    if target_i < total_samples:
                        mixed_val = master_buffer[target_i] + sample_val
                        master_buffer[target_i] = max(-32767, min(32767, mixed_val))
        except Exception as e:
            print(f"Error overlaying {wav_file}: {e}")

    with wave.open(output_dubbed_track, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(master_buffer.tobytes())

    if os.path.exists(output_dubbed_track) and os.path.getsize(output_dubbed_track) > 1000:
        yield ("done", output_dubbed_track)
    else:
        yield ("done", None)

def build_dubbing_track_for_subtitles(subtitles, voice_id, speed, temp_dir, open_speaker_key=None, log_cb=None, min_total_duration=0.0):
    """Synchronous wrapper for build_dubbing_track_for_subtitles_generator"""
    gen = build_dubbing_track_for_subtitles_generator(subtitles, voice_id, speed, temp_dir, open_speaker_key, min_total_duration)
    result = None
    for event_type, data in gen:
        if event_type == 'progress' and log_cb:
            log_cb(data)
        elif event_type == 'done':
            result = data
    return result
