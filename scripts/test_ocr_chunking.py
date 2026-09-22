import unittest
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ocr_module

class TestOCRChunking(unittest.TestCase):
    def test_ffmpeg_path_found(self):
        ffmpeg_path = ocr_module._get_ffmpeg_path()
        self.assertIsNotNone(ffmpeg_path)
        self.assertTrue(os.path.exists(ffmpeg_path))

    def test_merge_chunks_boundary(self):
        # Simulating chunk 1 and chunk 2 with boundary overlap
        chunk1 = [(0.0, 'Câu 1'), (0.5, 'Câu 1'), (1.0, 'Câu 2')]
        chunk2 = [(1.0, 'Câu 2'), (1.5, 'Câu 2'), (2.0, 'Câu 3')]
        combined = chunk1 + chunk2
        seen = set()
        clean = []
        for item in sorted(combined, key=lambda x: x[0]):
            t = item[0]
            txt = item[1] if len(item) > 1 else ''
            b = item[2] if len(item) > 2 else None
            rt = round(t, 3)
            if rt not in seen:
                seen.add(rt)
                clean.append((rt, txt, b))
        merged = ocr_module._merge_ocr_samples(clean, 0.5, 2.5)
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]['text'], 'Câu 1')
        self.assertEqual(merged[0]['start'], 0.0)
        self.assertEqual(merged[0]['end'], 1.0)
        self.assertEqual(merged[1]['text'], 'Câu 2')
        self.assertEqual(merged[1]['start'], 1.0)
        self.assertEqual(merged[1]['end'], 2.0)
        self.assertEqual(merged[2]['text'], 'Câu 3')
        self.assertEqual(merged[2]['start'], 2.0)
        self.assertEqual(merged[2]['end'], 2.5)

    def test_merge_chunks_with_3tuples_and_boxes(self):
        # Test real worker output with 3-tuples (timestamp, text, box_data)
        box1 = {'rel_x': 10, 'rel_r': 100, 'rel_y': 20, 'rel_b': 50}
        box2 = {'rel_x': 15, 'rel_r': 110, 'rel_y': 20, 'rel_b': 50}
        chunk1 = [(0.0, 'Đoạn 1', box1), (0.5, 'Đoạn 1', box1), (1.0, 'Đoạn 2', box2)]
        chunk2 = [(1.0, 'Đoạn 2', box2), (1.5, 'Đoạn 2', box2), (2.0, 'Đoạn 3', None)]
        combined = chunk1 + chunk2
        seen = set()
        clean = []
        for item in sorted(combined, key=lambda x: x[0]):
            t = item[0]
            txt = item[1] if len(item) > 1 else ''
            b = item[2] if len(item) > 2 else None
            rt = round(t, 3)
            if rt not in seen:
                seen.add(rt)
                clean.append((rt, txt, b))
        merged = ocr_module._merge_ocr_samples(clean, 0.5, 2.5, video_w=1920, video_h=1080)
        self.assertEqual(len(merged), 3)
        self.assertEqual(merged[0]['text'], 'Đoạn 1')
        self.assertIsNotNone(merged[0].get('box'))
        self.assertEqual(merged[1]['text'], 'Đoạn 2')
        self.assertIsNotNone(merged[1].get('box'))

    def test_blank_check(self):
        import numpy as np
        # Completely blank frame
        blank = np.zeros((50, 200), dtype=np.uint8)
        self.assertTrue(ocr_module.is_blank_or_no_text(blank))
        # Uniform gray frame
        uniform = np.ones((50, 200), dtype=np.uint8) * 128
        self.assertTrue(ocr_module.is_blank_or_no_text(uniform))

if __name__ == '__main__':
    unittest.main()
