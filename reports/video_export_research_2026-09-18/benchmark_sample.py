"""Bounded research benchmark; no application imports, configuration changes or network."""
import ast
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FFMPEG = ROOT / 'bin/ffmpeg.exe'
SOURCE = next((ROOT / 'downloads').glob('*.mp4'))
DURATION = 10
nodes = ast.parse((ROOT / 'auto_edit_pipeline.py').read_text(encoding='utf-8')).body
names = {'format_ass_time', 'calc_sub_width_ratio', 'generate_dynamic_blur_ass_mask', 'build_dynamic_blur_filter_chain'}
namespace = {'os': os, 'time': time, 'uuid': uuid}
exec(compile(ast.Module(body=[n for n in nodes if isinstance(n, ast.FunctionDef) and n.name in names], type_ignores=[]), '<isolated-current-blur-functions>', 'exec'), namespace)
filters, label = namespace['build_dynamic_blur_filter_chain'](
    '0:v', [(0, 4, 'Sample subtitle'), (5, 10, 'Sample subtitle longer')],
    engine='mask', temp_dir=str(OUT), frame_w=1920, frame_h=1080,
    content_h=1080, manual_mode=True, manual_w=0.6)
# Synthetic subtitles isolate filter cost; not claimed to reproduce user's project.
(OUT / 'sample.srt').write_text('1\n00:00:00,000 --> 00:00:04,000\nPhu de thu nghiem\n\n2\n00:00:05,000 --> 00:00:10,000\nKiem tra toc do xuat phim\n', encoding='utf-8')
subtitle = "subtitles=filename='sample.srt'"
graphs = {
    'encode_only': '[0:v]null[v]',
    'subtitle': f'[0:v]{subtitle}[v]',
    'current_mask_subtitle': ';'.join(filters + [f'[{label}]{subtitle}[v]']),
}
cases = [('encode_only', 'slow'), ('encode_only', 'veryfast'), ('subtitle', 'veryfast'), ('current_mask_subtitle', 'slow'), ('current_mask_subtitle', 'veryfast')]
results = {'source': str(SOURCE), 'offset_sec': 120, 'sample_duration_sec': DURATION,
           'limitations': '10 second local AV1 1080p30 sample, synthetic subtitles, null muxer, no audio; NOT six-hour end-to-end benchmark.', 'cases': []}
for graph_name, preset in cases:
    name = graph_name + '_' + preset
    graph_file = OUT / (name + '.txt')
    graph_file.write_text(graphs[graph_name], encoding='utf-8')
    cmd = [str(FFMPEG), '-hide_banner', '-nostdin', '-ss', '120', '-i', str(SOURCE),
           '-t', str(DURATION), '-/filter_complex', str(graph_file), '-map', '[v]',
           '-an', '-c:v', 'libx264', '-preset', preset, '-crf', '17', '-pix_fmt', 'yuv420p', '-f', 'null', '-']
    start = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=OUT, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60, creationflags=0x08000000)
        elapsed = time.perf_counter() - start
        (OUT / (name + '.log')).write_text(p.stderr, encoding='utf-8')
        row = {'case': name, 'exit_code': p.returncode, 'wall_sec': round(elapsed, 3), 'speed_wall_x': round(DURATION / elapsed, 3) if p.returncode == 0 else None, 'command': cmd}
    except subprocess.TimeoutExpired:
        row = {'case': name, 'status': 'timeout_60_seconds', 'command': cmd}
    results['cases'].append(row)
    (OUT / 'benchmark_results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in row.items() if k != 'command'}), flush=True)
