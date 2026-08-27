import os
import json
import subprocess
import time
import tempfile
import urllib.request
import requests
import random
import shutil
from pathlib import Path
import ffmpeg_installer

def extract_prompt_from_video(video_path, custom_srt_path=None, review_style="dramatic", custom_style_prompt=None):
    """
    Looks for the SRT file corresponding to the video path and generates a ChatGPT prompt with review style.
    """
    import review_styles
    style_directive = review_styles.get_style_directive(review_style, custom_style_prompt)
    
    video_name = os.path.basename(video_path)
    movie_title = os.path.splitext(video_name)[0]
    
    # Check for SRT in scripts/srt_files/ or use custom_srt_path
    if custom_srt_path and os.path.exists(custom_srt_path):
        srt_path = custom_srt_path
    else:
        srt_path = os.path.join('scripts', 'srt_files', f"{movie_title}.srt")
    
    if not os.path.exists(srt_path):
        return None, f"Không tìm thấy file phụ đề (SRT) tại {srt_path}. Vui lòng sang tab 'Biên tập phim' để Quét OCR hoặc chọn trực tiếp file SRT."
    
    content = ""
    try:
        with open(srt_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return None, f"Lỗi đọc file SRT: {str(e)}"
    
    # We only take the first 1000 lines or so to avoid blowing up the prompt, 
    # but ideally the user feeds the whole thing to ChatGPT.
    # We'll just provide the prompt instruction.
    
    prompt = f"""Tôi đang làm một video tóm tắt phim (Movie Recap) cho bộ phim "{movie_title}".
Dưới đây là phụ đề của phim (hoặc một phần của phụ đề).

{style_directive}

Nhiệm vụ của bạn:
1. Đọc phụ đề và tóm tắt lại cốt truyện theo đúng PHONG CÁCH VĂN PHONG đã yêu cầu ở trên để làm video ngắn (Shorts/Tiktok/YouTube).
2. Viết lời thoại (narration) cho người dẫn truyện.
3. Chọn ra các khoảng thời gian (start, end) tương ứng trong phụ đề thể hiện những cảnh quay đắt giá nhất, phù hợp với câu thoại đó.

BẮT BUỘC trả về ĐÚNG định dạng JSON mảng (Array) như sau, KHÔNG thêm bất kỳ text nào khác:
[
  {{
    "start": 12.5,
    "end": 20.0,
    "narration": "Vào một ngày đẹp trời, nhân vật chính xuất hiện với vẻ mặt đầy tự tin."
  }},
  {{
    "start": 45.0,
    "end": 52.5,
    "narration": "Nhưng một biến cố khủng khiếp đã ập đến."
  }}
]

Lưu ý: start và end là giây (kiểu số, ví dụ 12.5).

NỘI DUNG PHỤ ĐỀ:
{content[:8000]}... [CÒN TIẾP]
"""
    return prompt, None

def _run_cmd_yield(cmd_list, prefix="FFmpeg", check_stop=None):
    yield f"data: ⚙ Chạy lệnh {prefix}: {' '.join(cmd_list)}\n\n"
    try:
        process = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', **ffmpeg_installer.get_stealth_subprocess_kwargs())
        for line in process.stdout:
            if check_stop and check_stop():
                process.terminate()
                yield f"data: 🛑 Đã dừng tiến trình {prefix}.\n\n"
                return False
            if "time=" in line or "frame=" in line or "speed=" in line:
                # Log process but sparingly to avoid spam
                yield f"data:   ... {line.strip()}\n\n"
        process.wait()
        if process.returncode != 0:
            # Check stop again just in case it was terminated by another way
            if check_stop and check_stop():
                yield f"data: 🛑 Đã dừng tiến trình {prefix}.\n\n"
                return False
            yield f"data: 🛑 Lỗi khi chạy lệnh {prefix} (Exit code: {process.returncode})\n\n"
            return False
        return True
    except Exception as e:
        yield f"data: 🛑 Lỗi Exception khi chạy lệnh: {str(e)}\n\n"
        return False

def build_video_workflow(video_path, script_json, voice_id, output_dir, output_name, check_stop=None):
    if not output_name.lower().endswith('.mp4'):
        output_name += '.mp4'
    yield "data: BẮT ĐẦU QUÁ TRÌNH DỰNG VIDEO TỰ ĐỘNG...\n\n"
    ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
    
    movie_title = os.path.splitext(os.path.basename(video_path))[0]
    
    # 1. Generate Voiceovers using existing Kokoro/RVC logic via HTTP or importing directly
    yield "data: Bước 1/4: Đang tạo lồng tiếng (Voice-over) cho từng cảnh...\n\n"
    
    os.makedirs('clips/audio', exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    
    clips_list_path = os.path.join('clips', 'concat_list.txt')
    total_clips = len(script_json)
    current_progress = 0.0
    yield f"data: [PROGRESS] 0\n\n"
    
    with open(clips_list_path, 'w', encoding='utf-8') as f_list:
        
        for i, clip in enumerate(script_json):
            if check_stop and check_stop():
                yield "data: 🛑 Đã dừng tiến trình theo yêu cầu.\n\n"
                return
                
            start_s = clip['start']
            end_s = clip['end']
            narration = clip['narration']
            
            clip_pct = int(50.0 * (i + 1) / total_clips) if total_clips > 0 else 50
            yield f"data: --- Cảnh {i+1}/{total_clips} ({clip_pct}%): {start_s}s -> {end_s}s ---\n\n"
            yield f"data: 🎙️ Text: {narration}\n\n"
            yield f"data: [PROGRESS] {clip_pct}\n\n"
            
            # Request TTS
            audio_out_path = os.path.abspath(os.path.join('clips', 'audio', f'narration_{i}.wav'))
            
            # Calling the local API (Assuming it runs on port 5000)
            try:
                res = requests.post("http://127.0.0.1:5000/api/tts/kokoro", json={
                    "text": narration,
                    "voice_id": voice_id,
                    "speed": 1.0,
                    "output_dir": os.path.abspath(os.path.join('clips', 'audio')),
                    "filename": f'narration_{i}.wav'
                })
                if res.status_code != 200:
                    yield f"data: 🛑 Lỗi tạo TTS: {res.text}\n\n"
                    return
            except Exception as e:
                yield f"data: 🛑 Lỗi gọi API TTS: {str(e)}. (Máy chủ Flask có đang chạy không?)\n\n"
                return
            
            # Check audio duration using ffprobe
            ffprobe_path = os.path.join(os.path.dirname(ffmpeg_path), 'ffprobe.exe') if os.name == 'nt' else 'ffprobe'
            dur_cmd = [ffprobe_path, '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', audio_out_path]
            audio_dur = 3.0 # Default Fallback
            try:
                audio_dur = float(subprocess.check_output(dur_cmd, **ffmpeg_installer.get_stealth_subprocess_kwargs()).decode('utf-8').strip())
            except Exception:
                pass
            
            video_dur = end_s - start_s
            if video_dur <= 0: video_dur = 1.0
            
            # Video speed ratio
            speed_ratio = video_dur / audio_dur
            # clamp between 0.5 and 2.0 to avoid ridiculous speeds
            speed_ratio = max(0.5, min(2.0, speed_ratio))
            
            out_clip = os.path.abspath(os.path.join('clips', f'clip_{i}.mp4'))
            
            yield f"data: Đang cắt video & chỉnh tốc độ (Video: {video_dur:.1f}s, Audio: {audio_dur:.1f}s, Speed: {speed_ratio:.2f}x)...\n\n"
            
            # FFmpeg make adjusted clip
            # ffmpeg -ss start -to end -i video -i audio -filter_complex "[0:v]setpts=PTS/SPEED[v]" -map "[v]" -map 1:a out
            cmd = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-ss', str(start_s), '-to', str(end_s), '-i', video_path,
                '-i', audio_out_path,
                '-filter_complex', f"[0:v]setpts=PTS/{speed_ratio}[v]",
                '-map', '[v]', '-map', '1:a',
                '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-preset', 'veryfast', '-crf', '22',
                '-c:a', 'aac', '-b:a', '192k',
                out_clip
            ]
            success = yield from _run_cmd_yield(cmd, f"Cắt cảnh {i+1}", check_stop)
            if not success: return
            
            f_list.write(f"file '{out_clip}'\n")
            
            if total_clips > 0:
                current_progress += (50.0 / total_clips)
                yield f"data: [PROGRESS] {int(current_progress)}\n\n"

    # 2. Concat
    yield "data: Bước 2/4: Đang ghép các cảnh phim lại với nhau...\n\n"
    concat_out = os.path.join('clips', 'concat_out.mp4')
    cmd_concat = [
        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-f', 'concat', '-safe', '0', '-i', clips_list_path,
        '-c', 'copy',
        concat_out
    ]
    success = yield from _run_cmd_yield(cmd_concat, "Ghép cảnh", check_stop)
    if not success: return
    
    current_progress = 60
    yield f"data: [PROGRESS] 60\n\n"
    
    # 3. Add BGM
    yield "data: Bước 3/4: Đang thêm nhạc nền (BGM)...\n\n"
    final_hz_out = os.path.join(output_dir, output_name)
    bgm_dir = 'backgroundmusic'
    if os.path.exists(bgm_dir) and len(os.listdir(bgm_dir)) > 0:
        bgm_files = [os.path.join(bgm_dir, f) for f in os.listdir(bgm_dir) if f.endswith('.mp3') or f.endswith('.m4a')]
        if len(bgm_files) > 0:
            chosen_bgm = random.choice(bgm_files)
            yield f"data: Chọn nhạc nền: {os.path.basename(chosen_bgm)}\n\n"
            
            cmd_mix = [
                ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
                '-i', concat_out, '-i', chosen_bgm,
                '-filter_complex', "[0:a]volume=2.5[a0];[1:a]volume=0.1[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[a]",
                '-map', '0:v', '-map', '[a]',
                '-c:v', 'copy', '-c:a', 'aac',
                final_hz_out
            ]
            yield from _run_cmd_yield(cmd_mix, "Mix nhạc nền", check_stop)
        else:
            yield "data: Không tìm thấy nhạc nền hợp lệ, sử dụng bản gốc.\n\n"
            shutil.copy(concat_out, final_hz_out)
    else:
        yield "data: Không có thư mục nhạc nền, bỏ qua bước này.\n\n"
        shutil.copy(concat_out, final_hz_out)
        
    current_progress = 75
    yield f"data: [PROGRESS] 75\n\n"
        
    # 4. Vertical Output
    yield "data: Bước 4/4: Đang xuất phiên bản TikTok (Tỷ lệ dọc 9:16)...\n\n"
    os.makedirs('tiktok_output', exist_ok=True)
    base_name = os.path.splitext(output_name)[0]
    final_vt_out = os.path.join('tiktok_output', f"{base_name}_vertical.mp4")
    
    cmd_vert = [
        ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
        '-i', final_hz_out,
        '-filter_complex', "[0:v]crop=ih*9/16:ih,scale=1080:1920[v]",
        '-map', '[v]', '-map', '0:a',
        '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
        '-c:a', 'copy',
        final_vt_out
    ]
    yield from _run_cmd_yield(cmd_vert, "Render Video dọc", check_stop)
    
    yield f"data: [PROGRESS] 100\n\n"
    
    yield f"data: 🎉 HOÀN THÀNH TẤT CẢ!\n\n"
    yield f"data: Video ngang (Youtube): {final_hz_out}\n\n"
    yield f"data: Video dọc (TikTok): {final_vt_out}\n\n"
