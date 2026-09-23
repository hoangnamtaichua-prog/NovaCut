import os
import sys
import subprocess
import time
import ffmpeg_installer

def render_comic_review_video(segments, output_path, aspect_ratio="9:16", ken_burns=True, bgm_path=None, bgm_vol=0.15, burn_subs=True, check_stop=None):
    """
    Render video review truyện tranh hoàn chỉnh từ danh sách phân cảnh (segments).
    Yields Server-Sent Events (SSE) logs.
    """
    if not segments:
        yield "data: 🛑 Không có phân cảnh nào để tạo video!\n\n"
        return False

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(output_path)), 'temp_render')
    os.makedirs(temp_dir, exist_ok=True)

    # Xác định độ phân giải mục tiêu
    if aspect_ratio == "16:9":
        tw, th = 1920, 1080
    elif aspect_ratio == "1:1":
        tw, th = 1080, 1080
    else: # 9:16 mặc định cho TikTok/Shorts
        tw, th = 1080, 1920

    bin_dir = os.path.join(ffmpeg_installer.ROOT_DIR, 'bin')
    ffmpeg_exe = os.path.join(bin_dir, 'ffmpeg.exe') if os.name == 'nt' else 'ffmpeg'

    total_segments = len(segments)
    clip_files = []
    concat_list_path = os.path.join(temp_dir, "concat_list.txt")

    yield f"data: 🚀 Khởi động luồng dựng phim Review Truyện ({total_segments} phân cảnh, tỉ lệ {aspect_ratio})...\n\n"

    # 1. Render từng đoạn clip ngắn cho mỗi phân cảnh
    for idx, seg in enumerate(segments, start=1):
        if check_stop and check_stop():
            yield "data: 🛑 Đã dừng tiến trình tạo video.\n\n"
            return False

        dur = float(seg.get('duration', 3.0))
        img_p = seg.get('panel_path')
        aud_p = seg.get('audio_path')

        if not os.path.exists(img_p) or not os.path.exists(aud_p):
            yield f"data: ⚠️ Bỏ qua phân cảnh #{idx} do thiếu ảnh hoặc audio.\n\n"
            continue

        pct = int((idx / max(1, total_segments)) * 60)
        yield f"data: [PROGRESS] {pct}\n\n"
        yield f"data: 🎬 [1/4 Dựng Cảnh] Đang render phân cảnh {idx}/{total_segments} ({dur:.1f}s) • {int(idx/total_segments*100)}%...\n\n"

        clip_out = os.path.join(temp_dir, f"clip_{idx:04d}.mp4")

        # Tạo hiệu ứng nền mờ (Blurred Background) + Ảnh chính ở giữa có hiệu ứng zoom nhẹ
        # Giúp bảo toàn 100% hình vẽ truyện mà khung hình vẫn tràn viền chuyên nghiệp
        frames_count = max(1, int(dur * 30))
        if ken_burns:
            vf = (
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=20:5,eq=brightness=-0.1[bg];"
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
            )
        else:
            vf = (
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=increase,crop={tw}:{th},boxblur=20:5,eq=brightness=-0.1[bg];"
                f"[0:v]scale={tw}:{th}:force_original_aspect_ratio=decrease[fg];"
                f"[bg][fg]overlay=(W-w)/2:(H-h)/2,format=yuv420p"
            )

        cmd = [
            ffmpeg_exe, '-y',
            '-loop', '1',
            '-t', str(dur),
            '-i', img_p,
            '-i', aud_p,
            '-filter_complex', vf,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-crf', '22',
            '-r', '30',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-ar', '44100',
            '-ac', '2',
            '-shortest',
            clip_out
        ]

        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **ffmpeg_installer.get_stealth_subprocess_kwargs())
        p.communicate()

        if os.path.exists(clip_out) and os.path.getsize(clip_out) > 1000:
            clip_files.append(clip_out)
        else:
            yield f"data: ⚠️ Lỗi tạo clip #{idx}\n\n"

    if not clip_files:
        yield "data: 🛑 Không tạo được clip phân cảnh nào thành công.\n\n"
        return False

    # 2. Ghép nối tất cả các clips (Concatenation)
    yield "data: [PROGRESS] 65\n\n"
    yield f"data: 🔗 [2/4 Ghép Nối] Đang hợp nhất tất cả {len(clip_files)} phân cảnh thành video liền mạch...\n\n"
    with open(concat_list_path, 'w', encoding='utf-8') as f:
        for c in clip_files:
            escaped_path = c.replace('\\', '/').replace("'", "'\\''")
            f.write(f"file '{escaped_path}'\n")

    merged_temp = os.path.join(temp_dir, "merged_raw.mp4")
    cmd_concat = [
        ffmpeg_exe, '-y',
        '-f', 'concat',
        '-safe', '0',
        '-i', concat_list_path,
        '-c', 'copy',
        merged_temp
    ]
    p = subprocess.Popen(cmd_concat, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **ffmpeg_installer.get_stealth_subprocess_kwargs())
    p.communicate()

    if not os.path.exists(merged_temp) or os.path.getsize(merged_temp) == 0:
        yield "data: 🛑 Lỗi khi ghép các phân cảnh video.\n\n"
        return False

    # 3. Tạo file phụ đề SRT nếu bật burn_subs
    yield "data: [PROGRESS] 75\n\n"
    yield "data: 💬 [3/4 Hiệu Ứng] Đang phủ phụ đề kịch bản và hòa âm nhạc nền...\n\n"
    srt_path = os.path.join(temp_dir, "subs.srt")
    curr_time = 0.0
    with open(srt_path, 'w', encoding='utf-8') as srt_f:
        for idx, seg in enumerate(segments, start=1):
            dur = float(seg.get('duration', 3.0))
            text = seg.get('script_text', '').strip()
            st_s = curr_time
            et_s = curr_time + dur
            curr_time = et_s

            def fmt_t(sec):
                h = int(sec // 3600)
                m = int((sec % 3600) // 60)
                s = int(sec % 60)
                ms = int((sec - int(sec)) * 1000)
                return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

            srt_f.write(f"{idx}\n{fmt_t(st_s)} --> {fmt_t(et_s)}\n{text}\n\n")

    # 4. Mix BGM và Subtitle vào video đích
    final_inputs = ['-i', merged_temp]
    filter_complex = []

    # BGM
    has_bgm = bgm_path and os.path.exists(bgm_path)
    if has_bgm:
        final_inputs.extend(['-stream_loop', '-1', '-i', bgm_path])
        # Voice (0:a) + BGM (1:a) với ducking
        audio_filter = f"[1:a]volume={bgm_vol:.2f}[bgm];[0:a]volume=1.2[voice];[voice][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]"
    else:
        audio_filter = "[0:a]volume=1.2[aout]"

    # Subtitle Burn
    if burn_subs and os.path.exists(srt_path):
        escaped_srt = srt_path.replace('\\', '/').replace(':', '\\:')
        sub_style = "FontName=Arial,FontSize=16,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,BorderStyle=3,Outline=2,Shadow=0,MarginV=45,Alignment=2"
        video_filter = f"subtitles='{escaped_srt}':force_style='{sub_style}'[vout]"
    else:
        video_filter = "null[vout]"

    filter_str = f"[0:v]{video_filter};{audio_filter}"

    cmd_final = [
        ffmpeg_exe, '-y'
    ] + final_inputs + [
        '-filter_complex', filter_str,
        '-map', '[vout]',
        '-map', '[aout]',
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '20',
        '-c:a', 'aac',
        '-b:a', '192k',
        output_path
    ]

    yield "data: [PROGRESS] 88\n\n"
    yield "data: ⚙️ [4/4 Xuất File] Đang mã hóa file video MP4 cuối cùng (H.264/AAC)...\n\n"

    p = subprocess.Popen(cmd_final, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **ffmpeg_installer.get_stealth_subprocess_kwargs())
    p.communicate()

    if os.path.exists(output_path) and os.path.getsize(output_path) > 1000:
        yield "data: [PROGRESS] 100\n\n"
        yield f"data: 🎉 CHÚC MỪNG! ĐÃ TẠO THÀNH CÔNG VIDEO REVIEW TRUYỆN:\n\ndata: 📁 {output_path}\n\n"
        return True
    else:
        yield "data: 🛑 Lỗi xuất file video cuối cùng.\n\n"
        return False
