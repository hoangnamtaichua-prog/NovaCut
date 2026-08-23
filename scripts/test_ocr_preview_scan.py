import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import json
import ocr_module

def test_ocr_preview():
    # 1. Test get_ocr_engine
    engine = ocr_module.get_ocr_engine(prefer_gpu=True)
    print(f"OCR Engine loaded: {engine is not None}")

    # 2. Test scan_single_frame_box with non-existent file
    res_err = ocr_module.scan_single_frame_box("non_existent_file.mp4", 0.0, {'x': 20, 'y': 80, 'w': 60, 'h': 10})
    assert res_err['success'] is False, "Expected error on missing video"
    print(f"Error handling verified: {res_err['error']}")

    # 3. Test scan_preview_boxes_generator with empty / mock items
    mock_subs = [
        {'id': 1, 'startSeconds': 0.0, 'endSeconds': 1.5, 'text': 'Câu thoại mẫu 1'},
        {'id': 2, 'startSeconds': 2.0, 'endSeconds': 3.5, 'text': 'Câu thoại mẫu 2'}
    ]
    events = list(ocr_module.scan_preview_boxes_generator("non_existent.mp4", {'x': 20, 'y': 80, 'w': 60, 'h': 10}, mock_subs))
    assert len(events) > 0 and events[0]['type'] == 'error'
    print(f"Preview generator error handling verified: {events[0]}")

    print("\n✅ Tất cả kiểm thử logic OCR Preview Scan đã PASS 100%!")

if __name__ == "__main__":
    test_ocr_preview()
