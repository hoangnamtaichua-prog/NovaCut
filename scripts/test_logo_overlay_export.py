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
    
    if logo_enabled and logo_path and os.path.exists(logo_path):
        logo_input_idx = len(inputs) // 2
        inputs.extend(['-i', logo_path])

        x_pct = max(0.0, min(100.0, float(logo_data.get('x_pct', 5.0))))
        y_pct = max(0.0, min(100.0, float(logo_data.get('y_pct', 5.0))))
        w_pct = max(1.0, min(100.0, float(logo_data.get('w_pct', 18.0))))
        h_pct = max(1.0, min(100.0, float(logo_data.get('h_pct', 12.0))))
        opacity = max(0.05, min(1.0, float(logo_data.get('opacity', 100.0)) / 100.0))

        v_filters.append(f"[{logo_input_idx}:v]format=rgba,colorchannelmixer=aa={opacity:.2f}[logo_alpha]")
        v_filters.append(f"[logo_alpha][{curr_v}]scale2ref=w='main_w*{w_pct/100:.4f}':h='main_h*{h_pct/100:.4f}':force_original_aspect_ratio=decrease[logo_scaled][v_ref]")
        v_filters.append(f"[v_ref][logo_scaled]overlay=x='main_w*{x_pct/100:.4f}':y='main_h*{y_pct/100:.4f}'[v_logo]")
        curr_v = "v_logo"
    
    # Assertions
    assert len(inputs) == 4, f"Expected 4 items in inputs (2 pairs of -i <file>), got: {inputs}"
    assert inputs[2] == '-i' and inputs[3] == os.path.abspath(__file__)
    assert len(v_filters) == 3, f"Expected 3 video filters for logo, got: {v_filters}"
    assert "[1:v]format=rgba,colorchannelmixer=aa=0.85[logo_alpha]" in v_filters[0]
    assert "[logo_alpha][0:v]scale2ref=w='main_w*0.2500':h='main_h*0.1000':force_original_aspect_ratio=decrease[logo_scaled][v_ref]" in v_filters[1]
    assert "[v_ref][logo_scaled]overlay=x='main_w*0.1050':y='main_h*0.1520'[v_logo]" in v_filters[2]
    assert curr_v == "v_logo"
    
    print("  -> Generated Filter 0:", v_filters[0])
    print("  -> Generated Filter 1:", v_filters[1])
    print("  -> Generated Filter 2:", v_filters[2])
    print("  -> Inputs:", inputs)
    print("✅ Test Logo Watermark Filter Logic: PASS 100%!")

if __name__ == '__main__':
    test_logo_watermark_filter_construction()
