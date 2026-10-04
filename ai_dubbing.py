import os
import sys
import re
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

def get_app_root_dir():
    """Xác định chính xác tuyệt đối thư mục gốc của ứng dụng NovaCut."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr and os.path.dirname(curr) != curr:
        if os.path.exists(os.path.join(curr, 'web', 'index.html')):
            norm_curr = os.path.normpath(curr).lower()
            if not norm_curr.endswith(os.path.normpath('patches/active').lower()) and not norm_curr.endswith(os.path.normpath('release/novacut').lower()):
                return os.path.abspath(curr)
        curr = os.path.dirname(curr)
    return os.path.dirname(os.path.abspath(__file__))

ROOT_DIR = get_app_root_dir()

def get_sentence_cache_info(text, voice_id, speed=1.0, target_sample_rate=44100, target_channels=2):
    """
    Trả về (cache_key, cache_file_path, is_local) bảo đảm 100% Cache Hash Parity
    giữa các endpoint preview và pipeline xuất video lồng tiếng.
    """
    import custom_voices
    import local_voice_engine

    clean_text = str(text or '').strip()
    clean_voice = str(voice_id or 'local_ngoc_huyen').strip()
    safe_speed = float(speed or 1.0)

    voice_profile = custom_voices.resolve_voice_profile(clean_voice) or {}
    is_local = (
        clean_voice.startswith('local_') or
        voice_profile.get('provider') == 'local_voice' or
        any(w in clean_voice.lower() for w in ['adam', 'local_adam'])
    )

    cache_dir = os.path.join(ROOT_DIR, '.cache', 'tts_cache')
    os.makedirs(cache_dir, exist_ok=True)

    if is_local:
        cache_key = local_voice_engine.get_versioned_audio_cache_key(
            clean_text, clean_voice, safe_speed, target_sample_rate, target_channels, version="v3"
        )
    else:
        cache_key = hashlib.md5(f"{clean_voice}_{safe_speed:.2f}_{clean_text}".encode('utf-8')).hexdigest()

    cache_file = os.path.join(cache_dir, f"{cache_key}.wav")
    return cache_key, cache_file, is_local


def get_sentence_cache_path(text, voice_id, speed=1.0, sample_rate=44100, channels=2):
    """Helper alias returning (cache_key, cache_file_path)."""
    cache_key, cache_file, _ = get_sentence_cache_info(text, voice_id, speed, sample_rate, channels)
    return cache_key, cache_file


def is_valid_pcm_wav(file_path, target_sample_rate=None, target_channels=None):
    """Kiểm tra tệp có phải là RIFF 16-bit PCM WAV hợp lệ hay không."""
    if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) < 44:
        return False
    try:
        with wave.open(file_path, 'rb') as wf:
            if wf.getsampwidth() != 2:
                return False
            if target_sample_rate is not None and wf.getframerate() != int(target_sample_rate):
                return False
            if target_channels is not None and wf.getnchannels() != int(target_channels):
                return False
            return True
    except Exception:
        return False


def ensure_pcm_wav(file_path, target_sample_rate=44100, target_channels=2):
    """
    Đảm bảo file âm thanh tại file_path chắc chắn là 16-bit PCM WAV hợp lệ
    với đúng target_sample_rate và target_channels.
    Nếu file là MP3, AAC hoặc WAV giả định dạng (do Edge-TTS hay OpenSpeaker ghi thẳng MP3 stream),
    hệ thống tự động transcode siêu tốc qua FFmpeg sang PCM s16le để Python wave và Mixer đọc trơn tru 100%.
    """
    if not file_path or not os.path.exists(file_path) or os.path.getsize(file_path) < 44:
        return False

    if is_valid_pcm_wav(file_path, target_sample_rate, target_channels):
        return True

    try:
        ffmpeg_exe = ffmpeg_installer.get_ffmpeg_path() if hasattr(ffmpeg_installer, 'get_ffmpeg_path') else 'ffmpeg'
        dir_name = os.path.dirname(os.path.abspath(file_path))
        base_name = os.path.basename(file_path)
        tmp_wav = os.path.join(dir_name, f"tmp_trans_{int(time.time()*1000)}_{base_name}.wav")
        cmd = [
            ffmpeg_exe, "-y", "-hide_banner", "-loglevel", "error",
            "-i", file_path,
            "-ar", str(target_sample_rate),
            "-ac", str(target_channels),
            "-c:a", "pcm_s16le",
            tmp_wav
        ]
        res = subprocess.run(cmd, capture_output=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
        if res.returncode == 0 and os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 100:
            if os.path.exists(file_path):
                try:
                    os.remove(file_path)
                except Exception:
                    pass
            os.replace(tmp_wav, file_path)
            return True
        else:
            if os.path.exists(tmp_wav):
                try:
                    os.remove(tmp_wav)
                except Exception:
                    pass
    except Exception as e:
        print(f"[AI Dubbing] Transcode note for {file_path}: {e}")
    return False


def synthesize_sentence(text, voice_id, speed, output_path, open_speaker_key=None, **kwargs):
    """
    Synthesizes speech for a single text sentence and guarantees that the resulting
    file is a valid 16-bit PCM WAV if output_path ends with .wav or target_sample_rate is requested.
    """
    result_path = _synthesize_sentence_impl(text, voice_id, speed, output_path, open_speaker_key=open_speaker_key, **kwargs)
    if result_path and os.path.exists(result_path) and os.path.getsize(result_path) > 100:
        if str(result_path).lower().endswith('.wav') or kwargs.get('target_sample_rate'):
            tgt_sr = kwargs.get('target_sample_rate', 44100)
            tgt_ch = kwargs.get('target_channels', 2)
            ensure_pcm_wav(result_path, target_sample_rate=tgt_sr, target_channels=tgt_ch)
    return result_path


def _synthesize_sentence_impl(text, voice_id, speed, output_path, open_speaker_key=None, **kwargs):
    """
    Synthesizes speech for a single text sentence using RVC (Custom Clone), Kokoro (offline), Edge AI or OpenSpeaker (online).
    """
    import vietnamese_text_normalizer
    text = vietnamese_text_normalizer.normalize_text_for_tts(text)

    # 0. Local Voice Engine (High Quality Preset & Instant Cloned Voices)
    import custom_voices
    voice_profile = custom_voices.resolve_voice_profile(voice_id)
    print(f"[AI Dubbing] Synthesizing: voice_id='{voice_id}', gender='{voice_profile.get('gender')}', lang='{voice_profile.get('lang')}', provider='{voice_profile.get('provider')}'")

    # Bảo vệ câu thoại: nếu văn bản có dấu tiếng Việt nhưng người dùng chọn giọng tiếng Anh (như Adam/Guy)
    has_vi_diacritics = bool(re.search(r'[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]', text, re.IGNORECASE))
    is_voice_en = any(w in str(voice_id).lower() for w in ['adam', 'en_', 'en-', 'guy', 'jenny', 'heart', 'michael', 'nicole', 'us'])
    if has_vi_diacritics and is_voice_en:
        is_male = voice_profile.get('gender') == 'male' or any(w in str(voice_id).lower() for w in ['adam', 'nam', 'duc', 'dung', 'dat', 'guy', 'michael'])
        target_vi_voice = 'local_minh_duc' if is_male else 'local_ngoc_huyen'
        print(f"[AI Dubbing] Phát hiện phụ đề tiếng Việt nhưng chọn giọng tiếng Anh ('{voice_id}'). Tự động chuyển sang giọng {('Nam' if is_male else 'Nữ')} Việt ('{target_vi_voice}') để phát âm chuẩn xác, không bị câm câu.")
        return synthesize_sentence(text, target_vi_voice, speed, output_path, open_speaker_key, **kwargs)

    # Chuẩn hóa voice_id Adam sang local_adam nếu dùng local_voice
    if any(w in str(voice_id).lower() for w in ['kokoro_am_adam', 'en_adam', 'local_adam']) or voice_id == 'adam':
        voice_id = 'local_adam'

    if (voice_profile and voice_profile.get('provider') == 'local_voice') or voice_id.startswith('local_'):
        try:
            import local_voice_engine
            return local_voice_engine.synthesize(
                text=text,
                voice_id=voice_id,
                speed=speed,
                output_path=output_path,
                target_sample_rate=kwargs.get('target_sample_rate'),
                target_channels=kwargs.get('target_channels')
            )
        except Exception as e:
            print(f"[Local Voice] Synthesis error: {e}, falling back to Edge-TTS preserving gender/lang...")
            edge_fallback = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
            return synthesize_sentence(text, edge_fallback, speed, output_path, open_speaker_key, **kwargs)

    # 0.1. RVC Voice Clone (Custom Trained Models)
    rvc_profile = voice_profile
    if (rvc_profile and rvc_profile.get('provider') == 'rvc') or voice_id.startswith('rvc_'):
        base_voice = rvc_profile.get('base_voice')
        if not base_voice:
            base_voice = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
        temp_base_audio = os.path.join(os.path.dirname(os.path.abspath(output_path)), f"temp_base_{int(time.time()*1000)}.wav")
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        try:
            model_path = rvc_profile.get('model_path') if rvc_profile else None
            if not model_path or not os.path.exists(model_path):
                print(f"[RVC] Không tìm thấy tệp model RVC ({model_path}), tự động chuyển sang giọng đọc dự phòng cùng giới tính/ngôn ngữ...")
                fb_voice = custom_voices.get_fallback_voice(voice_id, target_provider='local_voice')
                try:
                    import local_voice_engine
                    return local_voice_engine.synthesize(text=text, voice_id=fb_voice, speed=speed, output_path=output_path)
                except Exception:
                    fb_edge = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
                    return synthesize_sentence(text, fb_edge, speed, output_path)

            synthesize_sentence(text, base_voice, speed, temp_base_audio, open_speaker_key)
            
            import rvc_bridge
            index_path = rvc_profile.get('index_path') if rvc_profile else None
            pitch = int(rvc_profile.get('pitch', 0)) if rvc_profile else 0
            f0_method = rvc_profile.get('f0_method', 'pm') if rvc_profile else 'pm'
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
            print(f"[RVC] Lỗi chuyển đổi giọng RVC ({rvc_err}), fallback sang giọng cùng giới tính...")
            fb_voice = custom_voices.get_fallback_voice(voice_id, target_provider='local_voice')
            try:
                import local_voice_engine
                return local_voice_engine.synthesize(text=text, voice_id=fb_voice, speed=speed, output_path=output_path)
            except Exception:
                fb_edge = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
                return synthesize_sentence(text, fb_edge, speed, output_path)
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
            print(f"Edge-TTS failed after 3 attempts ({last_err}), automatically falling back to offline voice preserving gender/lang...")
            fb_local = custom_voices.get_fallback_voice(voice_id, target_provider='local_voice')
            try:
                import local_voice_engine
                return local_voice_engine.synthesize(text=text, voice_id=fb_local, speed=speed, output_path=output_path)
            except Exception:
                pass
            kokoro_fallback = custom_voices.get_fallback_voice(voice_id, target_provider='kokoro')
            return synthesize_sentence(text, kokoro_fallback, speed, output_path)
            
        return output_path
        
    # 2. Kokoro / Offline Voices (Ưu tiên Local Voice ONNX Lite 48kHz không cần EXE)
    is_kokoro = voice_id.startswith('kokoro_') or voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat', 'en_heart', 'en_michael', 'en_nicole', 'en_adam', 'kokoro', 'adam', 'local_adam']
    
    if is_kokoro or not open_speaker_key:
        # 2.1 Thử Local Voice ONNX Lite Engine trước (In-process, zero-setup)
        try:
            import local_voice_engine
            if any(w in voice_id.lower() for w in ['adam']):
                local_vid = "local_adam"
            else:
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
            if voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat']:
                voice_target = voice_id
            else:
                voice_target = custom_voices.get_fallback_voice(voice_id, target_provider='kokoro')
            cmd = [
                kokoro_exe,
                "--text", text,
                "--output", output_path,
                "--voice", voice_target,
                "--speed", str(speed),
                "--device", "cpu"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', **ffmpeg_installer.get_stealth_subprocess_kwargs())
            if res.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return output_path

        # 2.3 Fallback an toàn sang Edge-TTS Miễn phí (Bảo toàn giới tính & ngôn ngữ)
        fallback_edge_voice = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
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
                
        # Fallback preserving gender/lang if OpenSpeaker fails
        print(f"OpenSpeaker failed after 3 attempts ({last_error}), falling back to offline voice preserving gender/lang...")
        fb_kokoro = custom_voices.get_fallback_voice(voice_id, target_provider='kokoro')
        return synthesize_sentence(text, fb_kokoro, speed, output_path)

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
                            p = subprocess.run([ff, '-i', output_audio_path], stderr=subprocess.PIPE, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
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

_QUICK_TRANSLATE_CACHE = {}

def quick_translate_to_vi(text):
    """
    Dịch nhanh một câu thoại chưa dịch sang tiếng Việt để bảo vệ tiến trình tạo giọng đọc.
    Ưu tiên dùng AI (OpenRouter / OpenAI) có sẵn trong cấu hình hệ thống, fallback sang DeepTranslator.
    """
    if not text or not str(text).strip():
        return ""
    text = str(text).strip()
    if text in _QUICK_TRANSLATE_CACHE:
        return _QUICK_TRANSLATE_CACHE[text]
    
    # 1. Thử qua OpenAI / OpenRouter có sẵn trong cấu hình
    try:
        from routes.subtitles import _resolve_openai_credentials
        api_key, base_url, model = _resolve_openai_credentials()
        if api_key:
            import openai
            headers = {}
            if 'openrouter.ai' in str(base_url) or api_key.startswith('sk-or-'):
                headers = {"HTTP-Referer": "https://novacut.app", "X-Title": "NovaCut AI"}
            client = openai.OpenAI(api_key=api_key, base_url=base_url, default_headers=headers if headers else None, timeout=8.0)
            req = {
                "model": model or "qwen/qwen3.7-flash",
                "messages": [
                    {"role": "system", "content": "Bạn là công cụ dịch thoại phim sang tiếng Việt. Hãy dịch câu sau sang tiếng Việt tự nhiên, chính xác, không ghi chú giải thích, chỉ trả về câu dịch thuần túy."},
                    {"role": "user", "content": text}
                ],
                "temperature": 0.0
            }
            if 'openrouter.ai' in str(base_url) or api_key.startswith('sk-or-'):
                req["extra_body"] = {"reasoning": {"effort": "none"}}
            res = client.chat.completions.create(**req)
            out = res.choices[0].message.content or ""
            out = re.sub(r'<think>.*?</think>', '', out, flags=re.DOTALL | re.IGNORECASE).strip()
            if out and not any(0x4E00 <= ord(c) <= 0x9FFF for c in out):
                _QUICK_TRANSLATE_CACHE[text] = out
                return out
    except Exception:
        pass

    # 2. Thử qua GoogleTranslator
    try:
        from deep_translator import GoogleTranslator
        gt = GoogleTranslator(source='auto', target='vi')
        out = gt.translate(text)
        if out and not any(k in out for k in ['Error 500', 'Server Error', 'TooManyRequests', '<!DOCTYPE', '<html']):
            if not any(0x4E00 <= ord(c) <= 0x9FFF for c in out):
                res_clean = out.strip()
                _QUICK_TRANSLATE_CACHE[text] = res_clean
                return res_clean
    except Exception:
        pass

    return ""

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
    
    # 0. Tự động kiểm tra file phụ đề đã dịch (editor_subtitles.srt) trong thư mục cha để tái sử dụng ngay lập tức (0s)
    parent_editor_sub = os.path.join(os.path.dirname(temp_dir), 'editor_subtitles.srt')
    if os.path.exists(parent_editor_sub) and os.path.getsize(parent_editor_sub) > 100:
        try:
            from auto_edit_pipeline import parse_srt_entries
            p_entries = parse_srt_entries(parent_editor_sub)
            if p_entries and len(p_entries) == len(subtitles) and not any(0x4E00 <= ord(c) <= 0x9FFF for c in p_entries[0][2]):
                subtitles = [{"text": txt, "translation": txt, "startSeconds": s, "endSeconds": e} for s, e, txt in p_entries]
        except Exception:
            pass

    # Normalize subtitle items
    raw_items = []
    for s in subtitles:
        if isinstance(s, (list, tuple)) and len(s) >= 3:
            s_start = parse_time_str(s[0])
            s_end = parse_time_str(s[1])
            s_text = str(s[2]).strip()
            if s_text:
                raw_items.append({"text": s_text, "startSeconds": s_start, "endSeconds": s_end})
        elif isinstance(s, dict):
            s_trans = (s.get('translation') or '').strip()
            s_orig = (s.get('text') or '').strip()
            s_text = s_trans if s_trans else s_orig
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
                
            raw_items.append({"text": s_text, "orig": s_orig, "startSeconds": s_start, "endSeconds": s_end})

    total = len(raw_items)
    if total == 0:
        yield ("progress", "🛑 [LỖI LỒNG TIẾNG] Danh sách phụ đề trống! Không có câu nào để lồng tiếng.")
        yield ("done", None)
        return

    # Tự động phát hiện và dịch nhanh song song các câu còn dính chữ Hán (On-the-fly Parallel Translation)
    chinese_indices = [idx for idx, item in enumerate(raw_items) if any(0x4E00 <= ord(c) <= 0x9FFF for c in item['text'])]
    if chinese_indices:
        yield ("progress", f"🌐 [Dịch phụ đề AI] Phát hiện {len(chinese_indices)} câu thoại còn chữ Hán, đang kích hoạt dịch nhanh song song sang tiếng Việt...")
        from concurrent.futures import ThreadPoolExecutor
        trans_workers = min(16, max(2, len(chinese_indices)))
        trans_done = 0

        def _do_trans(idx):
            nonlocal trans_done
            if check_stop and check_stop():
                return
            cand_text = raw_items[idx].get('orig') or raw_items[idx]['text']
            translated = quick_translate_to_vi(cand_text)
            if translated and not any(0x4E00 <= ord(c) <= 0x9FFF for c in translated):
                raw_items[idx]['text'] = translated.strip()
            trans_done += 1

        with ThreadPoolExecutor(max_workers=trans_workers) as pool:
            futures = [pool.submit(_do_trans, idx) for idx in chinese_indices]
            for f in futures:
                if check_stop and check_stop():
                    yield ("progress", "🛑 Đã dừng theo yêu cầu khẩn cấp.")
                    yield ("done", None)
                    return
                f.result()
                if trans_done % 25 == 0 or trans_done == len(chinese_indices):
                    pct = int((trans_done / len(chinese_indices)) * 100)
                    yield ("progress", f"🌐 [Dịch phụ đề AI] Tiến độ dịch: {trans_done}/{len(chinese_indices)} câu ({pct}%)...")

    normalized = [{"text": it["text"], "startSeconds": it["startSeconds"], "endSeconds": it["endSeconds"]} for it in raw_items]

    sample_rate = 44100
    channels = 2

    # Check OpenSpeaker key if using OpenSpeaker voice
    import custom_voices
    voice_profile = custom_voices.resolve_voice_profile(voice_id) or {}
    is_local = voice_id.startswith('local_') or voice_profile.get('provider') == 'local_voice' or any(w in voice_id.lower() for w in ['adam', 'local_adam'])
    is_kokoro = voice_id.startswith('kokoro_') or voice_id in ['ngoc_huyen', 'diem_trinh', 'mai_linh', 'nam_khoa', 'minh_duc', 'manh_dung', 'thanh_dat', 'en_heart', 'en_michael', 'en_nicole', 'en_adam', 'kokoro', 'adam', 'local_adam']
    is_edge = voice_id.startswith('edge_')
    is_rvc = voice_id.startswith('rvc_') or voice_profile.get('provider') == 'rvc'
    
    if not is_local and not is_kokoro and not is_edge and not is_rvc and not open_speaker_key:
        yield ("progress", "🛑 [LỖI API KEY] Bạn đang chọn giọng OpenSpeaker nhưng chưa cài đặt API Key trong mục Cài đặt!")
        yield ("done", None)
        return

    # Determine worker threads (Parallel speedup)
    if max_workers is not None and int(max_workers) > 0:
        req_workers = int(max_workers)
        if is_edge:
            actual_workers = max(2, min(req_workers, 32))
        elif is_rvc:
            actual_workers = max(1, min(req_workers, 8))
        elif is_local or is_kokoro:
            actual_workers = max(1, min(req_workers, 16))
        else:
            actual_workers = max(4, min(req_workers, 32))
    else:
        if is_edge:
            actual_workers = 32
        elif is_rvc:
            actual_workers = 4
        elif is_local or is_kokoro:
            actual_workers = 8
        else:
            actual_workers = 24

    sentence_audios = []
    error_list = []

    # ── ĐƯỜNG TỐI ƯU SIÊU TỐC CHO LOCAL VOICE (GPU PyTorch Batching qua Worker IPC) ──
    use_gpu_batch = False
    if is_local:
        try:
            import local_voice_worker_client
            client = local_voice_worker_client.get_voice_worker_client()
            if client.is_runtime_available():
                use_gpu_batch = True
        except Exception:
            use_gpu_batch = False

    if use_gpu_batch:
        yield ("progress", f"🚀 Kích hoạt GPU Worker (VieNeu v3 Turbo PyTorch) siêu tốc cho {total} câu phụ đề (Giọng: {voice_id})...")
        import gpu_resource_coordinator
        import local_voice_engine
        coordinator = gpu_resource_coordinator.get_gpu_coordinator()
        coordinator.acquire_gpu("tts")

        try:
            # 1. Kiểm tra cache phiên bản trước
            uncached_tasks = []
            completed_count = 0

            for i, sub in enumerate(normalized):
                if check_stop and check_stop():
                    yield ("progress", "🛑 Đã dừng theo yêu cầu khẩn cấp.")
                    yield ("done", None)
                    return

                text = sub['text']
                start_sec = sub['startSeconds']
                part_resampled = os.path.join(temp_dir, f"resampled_sub_{i}.wav")

                # Cache key đồng nhất qua get_sentence_cache_info
                cache_key, cached_file, _ = get_sentence_cache_info(
                    text, voice_id, speed, sample_rate, channels
                )

                if os.path.exists(cached_file) and os.path.getsize(cached_file) > 100:
                    try:
                        shutil.copyfile(cached_file, part_resampled)
                        ensure_pcm_wav(part_resampled, target_sample_rate=sample_rate, target_channels=channels)
                        if is_valid_pcm_wav(part_resampled, sample_rate, channels):
                            sentence_audios.append((part_resampled, start_sec))
                            completed_count += 1
                            pct = int((completed_count / total) * 100)
                            yield ("progress", f"⚡ [Cache Hit {completed_count}/{total}] ({pct}%) Câu #{i+1}: \"{text[:26]}...\" ({start_sec:.1f}s)")
                            continue
                    except Exception:
                        pass

                uncached_tasks.append({
                    "idx": i,
                    "id": i,
                    "text": text,
                    "startSeconds": start_sec,
                    "target_out": part_resampled,
                    "cached_file": cached_file
                })

            # 2. Xử lý theo Batch 16 câu trên GPU
            batch_size = 16
            for b_idx in range(0, len(uncached_tasks), batch_size):
                if check_stop and check_stop():
                    yield ("progress", "🛑 Đã hủy bỏ tiến trình tạo giọng AI theo yêu cầu khẩn cấp.")
                    yield ("done", None)
                    return

                chunk = uncached_tasks[b_idx:b_idx + batch_size]
                chunk_items = [{
                    "id": item["id"],
                    "text": item["text"],
                    "output_path": item["target_out"]
                } for item in chunk]

                # Gọi batch synthesis
                batch_results = local_voice_engine.synthesize_batch(
                    items=chunk_items,
                    voice_id=voice_id,
                    speed=speed,
                    target_sample_rate=sample_rate,
                    target_channels=channels,
                    batch_size=batch_size,
                    cancel_token=check_stop
                )

                # Thu thập kết quả
                for item, res in zip(chunk, batch_results):
                    completed_count += 1
                    pct = int((completed_count / total) * 100)
                    if res.get("success") and os.path.exists(item["target_out"]) and os.path.getsize(item["target_out"]) > 100:
                        try:
                            shutil.copyfile(item["target_out"], item["cached_file"])
                        except Exception:
                            pass
                        sentence_audios.append((item["target_out"], item["startSeconds"]))
                        yield ("progress", f"🎙️ [Tiến độ {completed_count}/{total}] ({pct}%) Đang tạo giọng câu #{item['idx']+1}: \"{item['text'][:26]}...\" ({item['startSeconds']:.1f}s)")
                    else:
                        # Cứu hộ tự động qua synthesize_sentence (thử lại qua CPU Engine hoặc Edge-TTS)
                        fb_success = False
                        try:
                            synthesize_sentence(
                                item["text"], voice_id, speed, item["target_out"], open_speaker_key,
                                target_sample_rate=sample_rate, target_channels=channels
                            )
                            if os.path.exists(item["target_out"]) and os.path.getsize(item["target_out"]) > 100:
                                fb_success = True
                            else:
                                fb_voice = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
                                synthesize_sentence(
                                    item["text"], fb_voice, speed, item["target_out"], open_speaker_key,
                                    target_sample_rate=sample_rate, target_channels=channels
                                )
                                if os.path.exists(item["target_out"]) and os.path.getsize(item["target_out"]) > 100:
                                    fb_success = True
                        except Exception:
                            pass

                        if fb_success:
                            ensure_pcm_wav(item["target_out"], target_sample_rate=sample_rate, target_channels=channels)
                            try:
                                shutil.copyfile(item["target_out"], item["cached_file"])
                            except Exception:
                                pass
                            sentence_audios.append((item["target_out"], item["startSeconds"]))
                            yield ("progress", f"🎙️ [Cứu hộ thành công] ({pct}%) Đã tạo giọng câu #{item['idx']+1}: \"{item['text'][:26]}...\" ({item['startSeconds']:.1f}s)")
                        else:
                            err = res.get("error", "Lỗi tạo audio GPU")
                            error_list.append((item["idx"], item["text"], err))
                            yield ("progress", f"⚠️ [Tiến độ {completed_count}/{total}] Lỗi tại câu #{item['idx']+1} (mốc {item['startSeconds']:.1f}s): {err}")

        finally:
            coordinator.release_gpu("tts")

    else:
        # ── ĐƯỜNG STANDARD CHO EDGE-TTS, OPENSPEAKER, KOKORO & RVC ──
        yield ("progress", f"🎙️ Khởi động {actual_workers} luồng tạo giọng song song cho {total} câu phụ đề (Giọng: {voice_id})...")

        def process_one_sub(idx, sub):
            if check_stop and check_stop():
                return (idx, None, sub['startSeconds'], sub['text'], "Đã dừng theo yêu cầu khẩn cấp")

            text = sub['text']
            start_sec = sub['startSeconds']
            part_raw = os.path.join(temp_dir, f"raw_sub_{idx}.wav")
            part_resampled = os.path.join(temp_dir, f"resampled_sub_{idx}.wav")
            
            # 1. Kiểm tra Cache âm thanh trước (Instant 0ms)
            cache_key, cached_file, _ = get_sentence_cache_info(
                text, voice_id, speed, sample_rate, channels
            )
            if os.path.exists(cached_file) and os.path.getsize(cached_file) > 100:
                try:
                    shutil.copyfile(cached_file, part_resampled)
                    ensure_pcm_wav(part_resampled, target_sample_rate=sample_rate, target_channels=channels)
                    if is_valid_pcm_wav(part_resampled, sample_rate, channels):
                        return (idx, part_resampled, start_sec, text, None)
                except Exception:
                    pass

            if check_stop and check_stop():
                return (idx, None, start_sec, text, "Đã dừng theo yêu cầu khẩn cấp")

            # 2. Tạo giọng với cơ chế Retry 3 lần nếu có lỗi mạng
            last_err = None
            target_out = part_resampled if is_local else part_raw
            for attempt in range(3):
                if check_stop and check_stop():
                    return (idx, None, start_sec, text, "Đã dừng theo yêu cầu khẩn cấp")
                try:
                    synthesize_sentence(
                        text, voice_id, speed, target_out, open_speaker_key,
                        target_sample_rate=sample_rate, target_channels=channels
                    )
                    if os.path.exists(target_out) and os.path.getsize(target_out) > 100:
                        last_err = None
                        break
                    else:
                        if any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
                            last_err = f"Câu còn nguyên chữ tiếng Trung chưa dịch ('{text[:20]}...'), giọng đọc tiếng Việt không thể phát âm"
                        elif not any(c.isalnum() for c in text):
                            last_err = f"Câu chỉ chứa dấu câu hoặc ký tự đặc biệt ('{text}')"
                        else:
                            last_err = "File âm thanh sinh ra bị rỗng (0 bytes)"
                except Exception as ex:
                    last_err = str(ex)
                    time.sleep(0.3 * (attempt + 1))
                    
            if not os.path.exists(target_out) or os.path.getsize(target_out) <= 100:
                # Cứu hộ tự động bằng Edge-TTS bảo toàn giới tính và ngôn ngữ
                try:
                    fb_voice = custom_voices.get_fallback_voice(voice_id, target_provider='edge')
                    synthesize_sentence(text, fb_voice, speed, target_out, open_speaker_key, target_sample_rate=sample_rate, target_channels=channels)
                except Exception:
                    pass

            if not os.path.exists(target_out) or os.path.getsize(target_out) <= 100:
                if not last_err:
                    if any(0x4E00 <= ord(c) <= 0x9FFF for c in text):
                        last_err = f"Câu còn nguyên chữ tiếng Trung chưa dịch ('{text[:20]}...'), giọng đọc tiếng Việt không thể phát âm"
                    elif not any(c.isalnum() for c in text):
                        last_err = f"Câu chỉ chứa dấu câu hoặc ký tự đặc biệt ('{text}')"
                    else:
                        last_err = "Không tạo được file âm thanh sau 3 lần thử"
                return (idx, None, start_sec, text, last_err)

            if check_stop and check_stop():
                return (idx, None, start_sec, text, "Đã dừng theo yêu cầu khẩn cấp")

            try:
                # Chuyển đổi an toàn sang 44100Hz 16-bit Stereo PCM WAV
                if target_out != part_resampled:
                    cmd_resample = [
                        ffmpeg_path, "-y", "-hide_banner", "-loglevel", "error",
                        "-i", target_out,
                        "-ar", str(sample_rate),
                        "-ac", str(channels),
                        "-c:a", "pcm_s16le",
                        part_resampled
                    ]
                    subprocess.run(cmd_resample, capture_output=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
                    
                    if os.path.exists(target_out):
                        try:
                            os.remove(target_out)
                        except:
                            pass
                else:
                    # target_out IS part_resampled (is_local path)
                    # Bắt buộc đảm bảo là PCM WAV chuẩn 16-bit (phòng ngừa Edge-TTS fallback sinh MP3)
                    ensure_pcm_wav(part_resampled, target_sample_rate=sample_rate, target_channels=channels)
                            
                if os.path.exists(part_resampled) and os.path.getsize(part_resampled) > 100 and is_valid_pcm_wav(part_resampled, sample_rate, channels):
                    try:
                        shutil.copyfile(part_resampled, cached_file)
                    except:
                        pass
                    return (idx, part_resampled, start_sec, text, None)
                return (idx, None, start_sec, text, "File âm thanh không đúng định dạng PCM WAV sau khi xử lý")
            except Exception as e:
                return (idx, None, start_sec, text, str(e))

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
                        yield ("progress", f"🎙️ [Tiến độ {completed_count}/{total}] ({pct}%) Đang tạo giọng câu #{idx+1}: \"{text[:26]}...\" ({start_s:.1f}s)")
                    else:
                        error_list.append((idx, text, err))
                        yield ("progress", f"⚠️ [Tiến độ {completed_count}/{total}] Lỗi tại câu #{idx+1} (mốc {start_s:.1f}s): {err}")
                except Exception as e:
                    error_list.append((0, '', str(e)))
                    yield ("progress", f"⚠️ [Tiến độ {completed_count}/{total}] Lỗi xử lý: {str(e)}")

    if not sentence_audios:
        first_err = error_list[0][2] if error_list else "Không thể kết nối đến máy chủ tạo giọng"
        yield ("progress", f"🛑 [LỖI LỒNG TIẾNG] Không có câu nào được tạo thành công! Chi tiết: {first_err}")
        yield ("done", None)
        return

    yield ("progress", f"✨ Đã tạo xong {len(sentence_audios)}/{total} câu. Đang ghép nối vào timeline video bằng NumPy...")

    output_dubbed_track = os.path.join(temp_dir, "dubbed_timeline.wav")

    # High-Performance NumPy Block-Based Timeline Audio Mixer
    try:
        import numpy_timeline_mixer
        numpy_timeline_mixer.mix_timeline_clips(
            clips=sentence_audios,
            output_path=output_dubbed_track,
            target_sample_rate=sample_rate,
            target_channels=channels,
            min_total_duration=min_total_duration,
            block_duration_sec=60.0
        )
    except Exception as mix_err:
        print(f"[Mixer] NumPy block mixer error ({mix_err}), falling back to standard array mixer...")
        max_time = 0.0
        for wav_file, start_s in sentence_audios:
            ensure_pcm_wav(wav_file, target_sample_rate=sample_rate, target_channels=channels)
            try:
                with wave.open(wav_file, 'rb') as wf:
                    max_time = max(max_time, start_s + wf.getnframes() / wf.getframerate())
            except Exception:
                pass
        if min_total_duration and min_total_duration > max_time:
            max_time = float(min_total_duration) + 1.0

        total_samples = int(max_time * sample_rate * channels)
        master_buffer = array.array('h', [0]) * total_samples

        for wav_file, start_s in sentence_audios:
            try:
                ensure_pcm_wav(wav_file, target_sample_rate=sample_rate, target_channels=channels)
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
