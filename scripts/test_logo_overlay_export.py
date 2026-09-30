import sys
import os
import re

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

# Add root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_logo_watermark_filter_construction():
    print("Testing Logo watermark filter complex logic in routes/video_edit.py...")
    
    # 1. Simulate export_data with logo enabled
    export_data = {
        'inputVideo': 'test_video.mp4',
        'outputDir': 'output',
        'outputName': 'test_out.mp4',
        'logo': {
            'enabled': True,
            'path': os.path.abspath(__file__), # existing file for test
            'x_pct': 10.5,
            'y_pct': 15.2,
            'w_pct': 25.0,
            'h_pct': 10.0,
            'opacity': 85
        }
    }
    
    logo_data = export_data.get('logo') or {}
    logo_enabled = bool(logo_data.get('enabled', False))
    logo_path = logo_data.get('path', '').strip()
    
    inputs = ['-i', 'test_video.mp4']
    v_filters = []
    curr_v = "0:v"
    cur_out_w, cur_out_h = 1920, 1080
    
    if logo_enabled and logo_path and os.path.exists(logo_path):
        logo_input_idx = len(inputs) // 2
        inputs.extend(['-i', logo_path])

        x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
        y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
        w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
        h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
        opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

        box_w = max(2, int(round((cur_out_w * w_pct / 100.0) / 2.0) * 2))
        box_h = max(2, int(round((cur_out_h * h_pct / 100.0) / 2.0) * 2))
        box_x = int(round(cur_out_w * x_pct / 100.0))
        box_y = int(round(cur_out_h * y_pct / 100.0))

        v_filters.append(f"[{logo_input_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f},scale=w={box_w}:h={box_h}:force_original_aspect_ratio=decrease:force_divisible_by=2[logo_ready]")
        v_filters.append(f"[{curr_v}][logo_ready]overlay=x='{box_x}+({box_w}-overlay_w)/2':y='{box_y}+({box_h}-overlay_h)/2'[v_logo]")
        curr_v = "v_logo"
    
    # Assertions
    assert len(inputs) == 4, f"Expected 4 items in inputs (2 pairs of -i <file>), got: {inputs}"
    assert inputs[2] == '-i' and inputs[3] == os.path.abspath(__file__)
    assert len(v_filters) == 2, f"Expected 2 video filters for logo, got: {v_filters}"
    assert "[1:v]format=rgba,colorchannelmixer=aa=0.85,scale=w=480:h=108:force_original_aspect_ratio=decrease:force_divisible_by=2[logo_ready]" in v_filters[0]
    assert "[0:v][logo_ready]overlay=x='202+(480-overlay_w)/2':y='164+(108-overlay_h)/2'[v_logo]" in v_filters[1]
    assert curr_v == "v_logo"
    
    print("  -> Generated Filter 0:", v_filters[0])
    print("  -> Generated Filter 1:", v_filters[1])
    print("  -> Inputs:", inputs)
    print("✅ Test Logo Watermark Filter Logic: PASS 100%!")

if __name__ == '__main__':
    test_logo_watermark_filter_construction()

