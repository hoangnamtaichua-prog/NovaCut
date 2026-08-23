import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
import subprocess
import json
import traceback

def extract_audio(video_path, audio_path):
    print("[STEP] Đang trích xuất âm thanh từ Video (có thể mất một lúc với video dài)...", flush=True)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    try:
        import ffmpeg_installer
        ffmpeg_bin = ffmpeg_installer.get_ffmpeg_path()
    except Exception:
        ffmpeg_bin = None
    if not ffmpeg_bin or not os.path.exists(ffmpeg_bin):
        ffmpeg_bin = os.path.join(base_dir, "bin", "ffmpeg.exe")
    if not os.path.exists(ffmpeg_bin):
        ffmpeg_bin = "ffmpeg"

    cmd = [
        ffmpeg_bin, "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, creationflags=0x08000000 if os.name == 'nt' else 0)

def format_timestamp(milliseconds):
    seconds = milliseconds / 1000.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def format_whisper_timestamp(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds - int(seconds)) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

def main():
    if len(sys.argv) < 4:
        print(json.dumps({"success": False, "error": "Missing arguments"}))
        return

    video_path = sys.argv[1]
    model_name = sys.argv[2]
    output_srt = sys.argv[3]
    language = sys.argv[4] if len(sys.argv) > 4 else "auto"
    
    if language == "auto" or language == "":
        language = None

    audio_path = "temp_asr_audio.wav"

    try:
        extract_audio(video_path, audio_path)

        if model_name == "whisper":
            print("[STEP] Đang nạp mô hình Faster-Whisper (Hỗ trợ 99 ngôn ngữ)...", flush=True)
            from faster_whisper import WhisperModel
            
            print("[STEP] Đang nạp Model 'large-v3-turbo' lên GPU (sẽ tự tải xuống nếu là lần đầu)...", flush=True)
            model = WhisperModel("large-v3-turbo", device="cuda", compute_type="float16")
            
            print(f"[STEP] Bắt đầu nhận diện. Ngôn ngữ: {language or 'Tự động'}. Vui lòng chờ...", flush=True)
            segments, info = model.transcribe(audio_path, language=language, beam_size=5, vad_filter=True)
            
            print(f"[STEP] AI đã phát hiện ngôn ngữ: {info.language} với độ tin cậy {info.language_probability:.2f}", flush=True)
            
            with open(output_srt, 'w', encoding='utf-8') as f:
                idx = 1
                total_duration = info.duration
                for segment in segments:
                    if idx % 5 == 0:
                        percent = min(100, int((segment.end / total_duration) * 100)) if total_duration > 0 else 0
                        print(f"[PROGRESS] {percent}", flush=True)
                        print(f"[STEP] Đang xử lý tới đoạn {format_whisper_timestamp(segment.start)} ({percent}%)...", flush=True)
                        
                    f.write(f"{idx}\n")
                    f.write(f"{format_whisper_timestamp(segment.start)} --> {format_whisper_timestamp(segment.end)}\n")
                    f.write(f"{segment.text.strip()}\n\n")
                    idx += 1
            
        else:
            print("[STEP] Đang nạp thư viện lõi AI (FunASR)...", flush=True)
            from funasr import AutoModel
            from funasr.utils.postprocess_utils import rich_transcription_postprocess
            
            model_id = "iic/SenseVoiceSmall"
            
            def run_inference(device=None):
                kwargs = {
                    "model": model_id,
                    "vad_model": "fsmn-vad",
                    "vad_kwargs": {"max_single_segment_time": 30000},
                    "punc_model": "ct-punc",
                    "disable_update": True
                }
                if device:
                    kwargs["device"] = device
                
                print("[STEP] Đang nạp Model (sẽ tự động tải xuống nếu là lần đầu tiên)...", flush=True)
                model = AutoModel(**kwargs)
                print("[STEP] Nạp Model thành công. Đang bóc tách phụ đề (quá trình này tốn nhiều thời gian nhất)...", flush=True)
                
                return model.generate(input=audio_path, batch_size_s=300, sentence_timestamp=True)

            try:
                res = run_inference()
            except Exception as e:
                err_msg = str(e)
                if "CUDA" in err_msg or "kernel image" in err_msg or "device-side assert" in err_msg:
                    res = run_inference(device="cpu")
                else:
                    raise e
            
            with open(output_srt, 'w', encoding='utf-8') as f:
                idx = 1
                if len(res) > 0:
                    result_dict = res[0]
                    if 'sentence_info' in result_dict:
                        for sentence in result_dict['sentence_info']:
                            start_ms = sentence.get('start', 0)
                            end_ms = sentence.get('end', 0)
                            text = rich_transcription_postprocess(sentence.get('text', ''))
                            
                            f.write(f"{idx}\n")
                            f.write(f"{format_timestamp(start_ms)} --> {format_timestamp(end_ms)}\n")
                            f.write(f"{text}\n\n")
                            idx += 1
                    else:
                        text = rich_transcription_postprocess(result_dict.get('text', ''))
                        f.write(f"1\n")
                        f.write(f"00:00:00,000 --> 00:00:10,000\n")
                        f.write(f"{text}\n\n")

        if os.path.exists(audio_path):
            os.remove(audio_path)

        print("\n[RESULT] " + json.dumps({"success": True, "srtPath": output_srt}), flush=True)

    except Exception as e:
        print("\n[RESULT] " + json.dumps({"success": False, "error": str(e), "traceback": traceback.format_exc()}), flush=True)

if __name__ == "__main__":
    main()
