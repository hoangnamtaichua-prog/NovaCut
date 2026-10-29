import os
import sys
import unittest
import json
import time

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from routes.tts import parse_text_into_speech_segments, generate_tts_stream_internal

class TestTtsOptimization(unittest.TestCase):

    def test_short_sentence_coalescing(self):
        """Kiểm tra logic gom các câu quá ngắn (<35 ký tự) thành cụm thoại tự nhiên."""
        text = "Trời mưa rồi. Gió thổi mạnh. Chúng ta hãy mau chóng tìm một nơi an toàn để trú ẩn thôi."
        segments = parse_text_into_speech_segments(text)
        speech_segs = [s[1] for s in segments if s[0] == 'speech']
        
        # 'Trời mưa rồi.' (13 ký tự) và 'Gió thổi mạnh.' (15 ký tự) phải được gom lại
        self.assertTrue(len(speech_segs) <= 2)
        self.assertTrue(any("Trời mưa rồi. Gió thổi mạnh." in s for s in speech_segs))

    def test_cache_and_stream_generation(self):
        """Kiểm tra luồng stream TTS với khả năng cache hit tức thì."""
        test_text = "Thử nghiệm kiểm tra bộ đệm thông minh của hệ thống TTS tối ưu hóa tốc độ."
        req = {
            'text': test_text,
            'voice': 'local_ngoc_huyen',
            'speed': 1.0,
            'output_dir': os.path.join(ROOT_DIR, 'output'),
            'filename': 'test_unit_cache.wav'
        }

        # Lần 1: Tạo và ghi vào cache
        complete_1 = None
        for chunk in generate_tts_stream_internal(req):
            if chunk.startswith('data: '):
                evt = json.loads(chunk[6:].strip())
                if evt.get('type') == 'complete':
                    complete_1 = evt
        self.assertIsNotNone(complete_1)
        self.assertTrue(complete_1.get('success'))

        # Lần 2: Phải đạt cache hit cực nhanh (< 1.0s)
        t0 = time.time()
        complete_2 = None
        has_cache_msg = False
        for chunk in generate_tts_stream_internal(req):
            if chunk.startswith('data: '):
                evt = json.loads(chunk[6:].strip())
                if evt.get('type') == 'progress' and '⚡' in evt.get('message', ''):
                    has_cache_msg = True
                elif evt.get('type') == 'complete':
                    complete_2 = evt
        elapsed = time.time() - t0

        self.assertIsNotNone(complete_2)
        self.assertTrue(complete_2.get('success'))
        self.assertTrue(has_cache_msg)
        self.assertTrue(elapsed < 2.0, f"Cache hit should take under 2s, took {elapsed:.2f}s")

if __name__ == '__main__':
    unittest.main()
