import os, sys, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
test_ffmpeg = str(ROOT / 'tools/ffmpeg-nvenc-test/ffmpeg.exe')
src = next((ROOT / 'downloads').glob('*.mp4'))

filter_b = (
    "[0:v]split[v_base][v_crop];"
    "[v_crop]crop=iw*0.8:ih*0.12:iw*0.1:ih*0.84,avgblur=sizeX=25:sizeY=25[v_blurred];"
    "[v_base][v_blurred]overlay=main_w*0.1:main_h*0.84:enable='between(t,0,4)+between(t,5,10)'[v]"
)

print("=== BENCHMARK COMBINATIONS (hwaccel x preset) ===")
for hw in [[], ['-hwaccel', 'cuda']]:
    for preset in ['p2', 'p3', 'p4']:
        t0 = time.perf_counter()
        cmd = [test_ffmpeg, '-hide_banner'] + hw + ['-ss', '120', '-t', '10', '-i', str(src),
               '-filter_complex', filter_b, '-map', '[v]',
               '-c:v', 'h264_nvenc', '-preset', preset, '-f', 'null', '-']
        res = subprocess.run(cmd, capture_output=True, encoding='utf-8', errors='replace')
        dur = time.perf_counter() - t0
        hw_label = 'CUDA' if hw else 'CPU-dec'
        print(f"{hw_label} + NVENC {preset}: {dur:.3f}s -> speed {10/dur:.2f}x (rc={res.returncode})")
