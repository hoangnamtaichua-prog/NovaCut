import os, sys, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
test_ffmpeg = str(ROOT / 'tools/ffmpeg-nvenc-test/ffmpeg.exe')
src = next((ROOT / 'downloads').glob('*.mp4'))
temp_dir = ROOT / 'reports/video_export_research_2026-09-18'
ass_file = str(temp_dir / 'dynamic_blur_mask_test.ass').replace('\\', '/').replace(':', r'\:')

# Generate a valid test ASS mask file
with open(temp_dir / 'dynamic_blur_mask_test.ass', 'w', encoding='utf-8') as f:
    f.write("""[Script Info]
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Mask,Arial,20,&H00FFFFFF,&H00000000,&H00FFFFFF,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:04.00,Mask,,0,0,0,,{\\an7\\pos(300,900)\\p1}m 0 0 l 1320 0 l 1320 120 l 0 120{\\p0}
Dialogue: 0,0:00:05.00,0:00:10.00,Mask,,0,0,0,,{\\an7\\pos(300,900)\\p1}m 0 0 l 1320 0 l 1320 120 l 0 120{\\p0}
""")

filter_a = (
    "[0:v]split=3[v_orig][v_blur][v_mask];"
    "[v_orig]format=gbrp[v_orig_rgb];"
    "[v_blur]format=gbrp,gblur=sigma=20:steps=2,lutrgb=r='val*0.94':g='val*0.94':b='val*0.94'[v_blur_rgb];"
    f"[v_mask]drawbox=c=black:t=fill,subtitles=filename='{ass_file}',format=gray,geq=lum='if(gt(lum(X,Y),100),255,0)',format=gbrp[v_mask_rgb];"
    "[v_orig_rgb][v_blur_rgb][v_mask_rgb]maskedmerge,format=yuv420p[v]"
)

# Test B: Fixed crop + boxblur + overlay
filter_b = (
    "[0:v]split[v_base][v_crop];"
    "[v_crop]crop=iw*0.8:ih*0.12:iw*0.1:ih*0.84,boxblur=15:2[v_blurred];"
    "[v_base][v_blurred]overlay=main_w*0.1:main_h*0.84:enable='between(t,0,4)+between(t,5,10)'[v]"
)

# Test C: YUV crop + avgblur + overlay
filter_c = (
    "[0:v]split[v_base][v_crop];"
    "[v_crop]crop=iw*0.8:ih*0.12:iw*0.1:ih*0.84,avgblur=sizeX=25:sizeY=25[v_blurred];"
    "[v_base][v_blurred]overlay=main_w*0.1:main_h*0.84:enable='between(t,0,4)+between(t,5,10)'[v]"
)

# Test D: Fast GPU mask (YUV native maskedmerge without gbrp or geq)
filter_d = (
    "[0:v]split=3[v_orig][v_blur][v_mask];"
    "[v_blur]avgblur=sizeX=25:sizeY=25[v_blur_yuv];"
    f"[v_mask]drawbox=c=black:t=fill,subtitles=filename='{ass_file}',format=yuv420p[v_mask_yuv];"
    "[v_orig][v_blur_yuv][v_mask_yuv]maskedmerge[v]"
)

tests = [
    ("Filter A (Current: gbrp + gblur + geq + maskedmerge)", filter_a),
    ("Filter B (Fixed Crop + boxblur + overlay)", filter_b),
    ("Filter C (Fixed Crop + avgblur + overlay)", filter_c),
    ("Filter D (YUV ASS Mask: avgblur + maskedmerge without geq)", filter_d)
]

print("=== STARTING FILTER BENCHMARK (10s sample, 1080p AV1 -> h264_nvenc p4) ===")
for name, f_complex in tests:
    t0 = time.perf_counter()
    cmd = [test_ffmpeg, '-hide_banner', '-ss', '120', '-t', '10', '-i', str(src),
           '-filter_complex', f_complex, '-map', '[v]',
           '-c:v', 'h264_nvenc', '-preset', 'p4', '-f', 'null', '-']
    res = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
    dur = time.perf_counter() - t0
    status = f"{dur:.3f}s -> speed {10/dur:.2f}x" if res.returncode == 0 else f"FAILED (rc={res.returncode}): {res.stderr[-200:]}"
    print(f"{name}:\n   Result: {status}")
