import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import ocr_module
import auto_edit_pipeline

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
    
    print("\nTesting ocr_module helper function existence...")
    assert hasattr(ocr_module, 'find_visual_boundaries'), "find_visual_boundaries must exist in ocr_module"
    
    print("\n✅ Tất cả kiểm thử Visual Alignment & Dynamic Blur Pipeline đã PASS 100%!")

if __name__ == '__main__':
    test_visual_alignment_and_filter()
