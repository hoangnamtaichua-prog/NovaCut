import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import ocr_module
import auto_edit_pipeline
from routes.video_edit import OutputGeometry, generate_styled_ass

def test_visual_alignment_and_filter():
    print("Testing auto_edit_pipeline.build_dynamic_blur_filter_chain with visual_start / visual_end...")
    
    # Mock entries with visual_start and visual_end
    # (s, e, txt, box_x, box_w, vis_s, vis_e)
    entries = [
        (3.0, 5.0, "Câu thoại 1", 0.25, 0.40, 2.2, 5.2),  # Visual start is 2.2s (earlier by 0.8s!)
        (7.0, 9.0, "Câu thoại 2", 0.20, 0.50, 6.5, 9.1),  # Visual start is 6.5s (earlier by 0.5s!)
        (9.4, 11.0, "Câu thoại 3", 0.30, 0.35, 9.2, 11.2) # Close to câu 2 -> should bridge gap smoothly!
    ]
    
    filters, final_v = auto_edit_pipeline.build_dynamic_blur_filter_chain(
        curr_v="0:v",
        active_intervals=entries,
        blur_sz=15,
        y_ratio=0.815,
        h_ratio=0.095,
        center_x_ratio=0.50,
        lead_sec=0.18,
        pad_sec=0.22
    )
    
    print(f"Generated {len(filters)} filter instructions:")
    for f in filters:
        print(f"  {f}")
        
    assert len(filters) > 0, "Filters must not be empty"
    assert "between(t," in "".join(filters), "Filter chain must contain between expressions"
    # Check that visual start 2.20 or s_lead is included
    assert "2.20" in "".join(filters) or "2.82" in "".join(filters), "Early visual start should be reflected in filter"

    print("\nTesting per-subtitle x/y/w/h geometry against preview formula...")
    geometry_filters, _ = auto_edit_pipeline.build_dynamic_blur_filter_chain(
        curr_v="0:v",
        active_intervals=[(1.0, 2.0, "原文", 0.40, 0.20, 0.86, 0.05, 1.0, 2.0)],
        y_ratio=0.815,
        h_ratio=0.095,
    )
    geometry_chain = "".join(geometry_filters)
    # Preview: width=20% + 2*1.5%=23%, centered at 50%; height=max(5%+1.2%, 9.5%*85%)=8.075%.
    assert "crop=iw*0.230:ih*0.081:iw*0.385:ih*0.845" in geometry_chain, geometry_chain
    assert "overlay=main_w*0.385:main_h*0.845" in geometry_chain, geometry_chain

    print("\nTesting that a manual blur region overrides an available AI box...")
    manual_filters, _ = auto_edit_pipeline.build_dynamic_blur_filter_chain(
        curr_v="0:v",
        active_intervals=[(1.0, 2.0, "原文", 0.40, 0.20, 0.86, 0.05, 1.0, 2.0)],
        y_ratio=0.70,
        h_ratio=0.08,
        center_x_ratio=0.25,
        manual_mode=True,
        manual_w=0.30,
    )
    manual_chain = "".join(manual_filters)
    assert "crop=iw*0.300:ih*0.080:iw*0.100:ih*0.700" in manual_chain, manual_chain
    assert "crop=iw*0.230" not in manual_chain, manual_chain

    print("\nTesting subtitle style export uses the selected preview font...")
    subtitle_filter = auto_edit_pipeline.build_subtitle_filter(
        "0:v", "v_sub", "D:/tmp/subtitles.srt",
        {"subtitle_style": {
            "font": "Be Vietnam Pro", "size": 32, "color": "#AABBCC",
            "outline_color": "#102030", "outline": 3, "bold": True,
            "italic": True, "align": "center"
        }}
    )
    assert "Fontname=Be Vietnam Pro" in subtitle_filter, subtitle_filter
    assert "Fontsize=32" in subtitle_filter, subtitle_filter
    assert "PrimaryColour=&H00CCBBAA" in subtitle_filter, subtitle_filter
    assert "OutlineColour=&H00302010" in subtitle_filter, subtitle_filter
    assert "Bold=-1,Italic=-1" in subtitle_filter, subtitle_filter
    assert "fontsdir=" in subtitle_filter, subtitle_filter

    print("\nTesting the editor ASS generator keeps the selected font and geometry...")
    with tempfile.TemporaryDirectory() as temp_dir:
        source_srt = os.path.join(temp_dir, 'source.srt')
        output_ass = os.path.join(temp_dir, 'output.ass')
        with open(source_srt, 'w', encoding='utf-8') as file:
            file.write('1\n00:00:00,000 --> 00:00:01,000\nPhụ đề mẫu\n')
        generate_styled_ass(
            source_srt, output_ass, 1920, 1080,
            {'font': 'Inter', 'size': 32, 'color': '#AABBCC', 'outline_color': '#102030',
             'outline': 3, 'bold': True, 'italic': True,
             'region': {'x': 10, 'y': 80, 'w': 80, 'h': 10}, 'align': 'center'},
            geometry=OutputGeometry(1920, 1080, 0, 0, 1920, 1080),
        )
        ass_text = open(output_ass, 'r', encoding='utf-8').read()
        assert 'Style: Default,Inter,48,&H00CCBBAA' in ass_text, ass_text
        assert '{\\an5\\pos(960,918)}' in ass_text, ass_text

    chunk_entries = [
        (i * 3.0, i * 3.0 + 1.0, "原文", 0.40, 0.20, 0.86, 0.05, i * 3.0, i * 3.0 + 1.0)
        for i in range(26)
    ]
    chunk_filters, _ = auto_edit_pipeline.build_dynamic_blur_filter_chain("0:v", chunk_entries)
    assert sum("overlay=" in value for value in chunk_filters) == 2, "Mỗi overlay chỉ được chứa tối đa 25 khoảng thời gian"
    
    print("\nTesting ocr_module helper function existence...")
    assert hasattr(ocr_module, 'find_visual_boundaries'), "find_visual_boundaries must exist in ocr_module"

    print("\nTesting Priority 1 - Timeline Masking Engine (ASS + maskedmerge)...")
    large_entries = [
        (i * 2.0, i * 2.0 + 1.5, f"Sub {i}", 0.30, 0.40, 0.815, 0.095, i * 2.0, i * 2.0 + 1.5)
        for i in range(50)
    ]
    mask_filters, mask_out = auto_edit_pipeline.build_dynamic_blur_filter_chain("0:v", large_entries, engine='auto')
    assert len(mask_filters) == 5, f"Timeline Masking must have exactly 5 filters, got {len(mask_filters)}"
    assert "maskedmerge" in mask_filters[-1], "Final filter must be maskedmerge"
    assert "subtitles=" in mask_filters[3], "Filter must load ASS mask via subtitles"
    assert auto_edit_pipeline._last_dynamic_blur_mask_file is not None, "Mask file must be tracked"
    assert os.path.exists(auto_edit_pipeline._last_dynamic_blur_mask_file), "Mask file must exist on disk"
    print(f"  Generated 4-node maskedmerge filter chain cleanly: {mask_filters[-1]}")
    
    print("\n✅ Tất cả kiểm thử Visual Alignment & Dynamic Blur Pipeline đã PASS 100%!")

if __name__ == '__main__':
    test_visual_alignment_and_filter()
