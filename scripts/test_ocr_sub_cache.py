# -*- coding: utf-8 -*-
"""
Test OCR subtitle and AI box caching and auto-resume.
"""
import os
import sys
import json
import shutil
import tempfile

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

import ocr_module

def test_cache_logic():
    print("=== Testing OCR Cache Logic ===")
    with tempfile.TemporaryDirectory() as temp_dir:
        cache_boxes_path = os.path.join(temp_dir, 'ai_blur_boxes.json')
        
        # 1. Pre-seed cache with 2 boxes
        seed_data = [
            {
                "index": 0,
                "sub_id": 1,
                "start": 0.0,
                "end": 2.0,
                "text": "Hello world",
                "box": {
                    "x_pct": 20.0,
                    "w_pct": 60.0,
                    "y_pct": 80.0,
                    "h_pct": 10.0,
                    "visual_start": 0.1,
                    "visual_end": 1.9
                }
            },
            {
                "index": 1,
                "sub_id": 2,
                "start": 2.5,
                "end": 4.5,
                "text": "NovaCut test",
                "box": {
                    "x_pct": 25.0,
                    "w_pct": 50.0,
                    "y_pct": 82.0,
                    "h_pct": 9.0,
                    "visual_start": 2.6,
                    "visual_end": 4.4
                }
            }
        ]
        with open(cache_boxes_path, 'w', encoding='utf-8') as f:
            json.dump(seed_data, f, ensure_ascii=False)
            
        mock_subs = [
            {"id": 1, "startSeconds": 0.0, "endSeconds": 2.0, "text": "Hello world"},
            {"id": 2, "startSeconds": 2.5, "endSeconds": 4.5, "text": "NovaCut test"},
            {"id": 3, "startSeconds": 5.0, "endSeconds": 7.0, "text": "New uncached line"}
        ]
        
        # Scan with a dummy video path (will fast-yield the 2 cached items, then report error or skip for non-existent video)
        # Note: if video does not exist, scan_preview_boxes_generator returns error if not cached,
        # but let's see how generator handles cached vs uncached.
        events = list(ocr_module.scan_preview_boxes_generator(
            "non_existent.mp4",
            {'x': 20, 'y': 80, 'w': 60, 'h': 10},
            mock_subs,
            save_cache_path=cache_boxes_path
        ))
        
        print(f"Events received with non_existent video: {len(events)}")
        # Since non_existent.mp4 doesn't exist, it yields error immediately
        assert any(e.get('type') == 'error' for e in events)

        # Now test with a real video or mock video file using OpenCV
        import cv2
        import numpy as np
        test_video_path = os.path.join(temp_dir, 'sample.mp4')
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(test_video_path, fourcc, 25.0, (640, 360))
        for _ in range(150):
            frame = np.zeros((360, 640, 3), dtype=np.uint8)
            cv2.putText(frame, "Hello world", (150, 300), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 2)
            out.write(frame)
        out.release()
        
        print("Created sample video for OCR test:", test_video_path)
        
        # Run scan_preview_boxes_generator with cache_boxes_path
        scan_events = list(ocr_module.scan_preview_boxes_generator(
            test_video_path,
            {'x': 10, 'y': 70, 'w': 80, 'h': 25},
            mock_subs,
            save_cache_path=cache_boxes_path
        ))
        
        cached_progress = [e for e in scan_events if e.get('type') == 'progress' and e.get('cached') == True]
        print(f"Cached progress events (instant reuse): {len(cached_progress)}")
        assert len(cached_progress) == 2, f"Expected 2 cached events, got {len(cached_progress)}"
        
        done_event = next((e for e in scan_events if e.get('type') == 'done'), None)
        assert done_event is not None
        print(f"Scan completed: {done_event}")
        
        # Check that cache file on disk was updated with item 3
        with open(cache_boxes_path, 'r', encoding='utf-8') as f:
            updated_cache = json.load(f)
        print(f"Updated cache items count on disk: {len(updated_cache)}")
        assert len(updated_cache) == 3, f"Expected 3 items in cache, got {len(updated_cache)}"
        print("✅ scan_preview_boxes_generator cache reuse and persistence test passed!")

def test_routes_cache():
    print("=== Testing Video Edit Blueprint Routes ===")
    from flask import Flask
    from routes.video_edit import video_edit_bp
    
    app = Flask(__name__)
    app.config['TESTING'] = True
    app.register_blueprint(video_edit_bp)
    
    client = app.test_client()
    
    # 1. Test check_cache with temp dir
    test_dir = os.path.join(ROOT_DIR, 'output', 'test_cache_temp')
    os.makedirs(test_dir, exist_ok=True)
    try:
        safe_stem = 'test_movie'
        editor_temp = os.path.join(test_dir, 'editor_temp', safe_stem)
        os.makedirs(editor_temp, exist_ok=True)
        
        # Write mock ai_blur_boxes.json and editor_subtitles.srt
        boxes_path = os.path.join(editor_temp, 'ai_blur_boxes.json')
        with open(boxes_path, 'w', encoding='utf-8') as f:
            json.dump([{"index": 0, "box": {"x_pct": 20}}], f)
            
        srt_path = os.path.join(editor_temp, 'editor_subtitles.srt')
        with open(srt_path, 'w', encoding='utf-8') as f:
            f.write("1\n00:00:01,000 --> 00:00:03,000\nTest sub\n\n")
            
        # Test check_cache endpoint
        res = client.post('/api/editor/check_cache', json={
            'input_video': f'C:/fake_path/{safe_stem}.mp4',
            'output_dir': test_dir
        })
        print("check_cache status:", res.status_code, res.data.decode('utf-8', 'ignore'))
        assert res.status_code == 200
        data = res.get_json()
        print("check_cache response:", data)
        assert data['has_cache'] is True
        assert data['details']['ai_boxes_count'] == 1
        assert 'cached_srt' in data['details']
        
        # Test cache_ai_boxes GET
        res_boxes = client.get(f'/api/editor/cache_ai_boxes?video_path=C:/fake_path/{safe_stem}.mp4&output_dir={test_dir}')
        assert res_boxes.status_code == 200
        boxes_data = res_boxes.get_json()
        print("cache_ai_boxes response:", boxes_data)
        assert boxes_data['success'] is True
        assert len(boxes_data['boxes']) == 1
        
        # Test save_cache_subtitles
        res_save = client.post('/api/editor/save_cache_subtitles', json={
            'video_path': f'C:/fake_path/{safe_stem}.mp4',
            'output_dir': test_dir,
            'subtitles': [{'startSeconds': 1.0, 'endSeconds': 3.0, 'text': 'Saved text'}]
        })
        assert res_save.status_code == 200
        print("save_cache_subtitles response:", res_save.get_json())
        
        # Test clear_cache_boxes
        res_clear = client.post('/api/editor/clear_cache_boxes', json={
            'video_path': f'C:/fake_path/{safe_stem}.mp4',
            'output_dir': test_dir
        })
        assert res_clear.status_code == 200
        assert not os.path.exists(boxes_path)
        print("clear_cache_boxes successfully removed ai_blur_boxes.json")
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)
        
    print("✅ All API routes tested successfully!")

if __name__ == '__main__':
    test_cache_logic()
    test_routes_cache()
