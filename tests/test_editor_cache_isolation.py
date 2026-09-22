import unittest
import os
import shutil
import json
from web_app import app
from ocr_module import get_editor_temp_dir

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class TestEditorCacheIsolation(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.test_dir = os.path.join(ROOT_DIR, 'scratch', 'test_cache_suite')
        self.output_dir = os.path.join(self.test_dir, 'output')
        os.makedirs(self.output_dir, exist_ok=True)
        self.video_path = os.path.join(self.test_dir, 'video_moi_chua_tung_lam.mp4')
        with open(self.video_path, 'wb') as f:
            f.write(b'fake_video_content')

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_unique_folders_for_different_videos(self):
        v1 = os.path.join(self.test_dir, '皇帝居然偷听我心声.mp4')
        v2 = os.path.join(self.test_dir, '逆袭从退婚开始啦.mp4')
        d1 = get_editor_temp_dir(self.output_dir, v1)
        d2 = get_editor_temp_dir(self.output_dir, v2)
        self.assertNotEqual(d1, d2)
        self.assertIn('皇帝居然偷听我心声', os.path.basename(d1))
        self.assertIn('逆袭从退婚开始啦', os.path.basename(d2))

    def test_same_video_deterministic(self):
        v1 = os.path.join(self.test_dir, 'phim_hay_tap_1.mp4')
        d1 = get_editor_temp_dir(self.output_dir, v1)
        d2 = get_editor_temp_dir(self.output_dir, v1.lower())
        self.assertEqual(d1, d2)

    def test_empty_video_safe(self):
        d = get_editor_temp_dir(self.output_dir, '')
        self.assertIn('_unnamed_video', d)

    def test_brand_new_video_has_no_cache(self):
        # Video chua tung lam bao gio -> bat buoc has_cache: False, files: []
        res = self.app.post('/api/editor/check_cache', json={
            'input_video': self.video_path,
            'output_dir': self.output_dir,
            'dubbing': {'enabled': True},
            'blur_original_subtitles': True
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertFalse(data['has_cache'])
        self.assertEqual(data['files'], [])

    def test_nonexistent_video_has_no_cache(self):
        res = self.app.post('/api/editor/check_cache', json={
            'input_video': os.path.join(self.test_dir, 'nonexistent_random_12345.mp4'),
            'output_dir': self.output_dir
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertFalse(data['has_cache'])

    def test_video_with_real_cache_detects_properly(self):
        temp_dir = get_editor_temp_dir(self.output_dir, self.video_path)
        os.makedirs(temp_dir, exist_ok=True)
        dub_file = os.path.join(temp_dir, 'dubbed_timeline.wav')
        with open(dub_file, 'wb') as f:
            f.write(b'x' * 2000)

        # Neu dubbing bat: phat hien dung video
        res = self.app.post('/api/editor/check_cache', json={
            'input_video': self.video_path,
            'output_dir': self.output_dir,
            'dubbing': {'enabled': True}
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['has_cache'])
        self.assertIn('Track lồng tiếng AI (dubbed_timeline.wav)', data['files'])

        # Neu dubbing tat: khong bao
        res2 = self.app.post('/api/editor/check_cache', json={
            'input_video': self.video_path,
            'output_dir': self.output_dir,
            'dubbing': {'enabled': False}
        })
        self.assertEqual(res2.status_code, 200)
        data2 = res2.get_json()
        self.assertFalse(data2['has_cache'])
        self.assertEqual(data2['files'], [])

    def test_blur_cache_detection_respects_toggle(self):
        temp_dir = get_editor_temp_dir(self.output_dir, self.video_path)
        os.makedirs(temp_dir, exist_ok=True)
        ai_boxes = os.path.join(temp_dir, 'ai_blur_boxes.json')
        with open(ai_boxes, 'w', encoding='utf-8') as f:
            json.dump([{'start': 0, 'end': 2, 'box': {'x_pct': 20, 'w_pct': 60}}], f)

        # 1. Khi bật blur: phát hiện cache
        res1 = self.app.post('/api/editor/check_cache', json={
            'input_video': self.video_path,
            'output_dir': self.output_dir,
            'blur_original_subtitles': True,
            'subtitles_enabled': True
        })
        d1 = res1.get_json()
        self.assertTrue(d1['has_cache'])
        self.assertTrue(any('làm mờ AI Pixel' in x for x in d1['files']))

        # 2. Khi tắt blur: KHÔNG phát hiện cache làm mờ
        res2 = self.app.post('/api/editor/check_cache', json={
            'input_video': self.video_path,
            'output_dir': self.output_dir,
            'blur_original_subtitles': False,
            'subtitles_enabled': True
        })
        d2 = res2.get_json()
        self.assertFalse(d2['has_cache'])
        self.assertEqual(d2['files'], [])

        # 3. Khi tắt master subtitle switch (subtitles_enabled=False): blur tự động tắt, không báo cache
        res3 = self.app.post('/api/editor/check_cache', json={
            'input_video': self.video_path,
            'output_dir': self.output_dir,
            'blur_original_subtitles': True,
            'subtitles_enabled': False
        })
        d3 = res3.get_json()
        self.assertFalse(d3['has_cache'])
        self.assertEqual(d3['files'], [])

    def test_start_generation_no_subtitles_does_not_crash_unbound_local(self):
        # Khi tắt phụ đề và tắt blur, can_stream_copy phải đánh giá an toàn 100% không văng UnboundLocalError
        res = self.app.post('/api/start', json={
            'inputVideo': self.video_path,
            'outputDir': self.output_dir,
            'outputName': 'test_stream_copy.mp4',
            'subtitles_enabled': False,
            'blur_original_subtitles': False,
            'mode': 'none'
        })
        # Generator endpoint trả về stream SSE (200 OK)
        self.assertEqual(res.status_code, 200)
        # Đọc chunk đầu tiên của generator để kích hoạt đánh giá can_stream_copy
        first_chunk = next(res.response)
        text_out = first_chunk.decode('utf-8', errors='ignore') if isinstance(first_chunk, bytes) else str(first_chunk)
        self.assertNotIn("cannot access local variable 'logo_enabled'", text_out)
        self.assertNotIn("[LỖI HỆ THỐNG]", text_out)

if __name__ == '__main__':
    unittest.main()

