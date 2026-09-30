# -*- coding: utf-8 -*-
import unittest
import numpy as np
import cv2
import os
import tempfile
from subtitle_inspector import SubtitleInspectorBot, _text_similarity, _normalize_box_coords

class TestSubtitleInspector(unittest.TestCase):

    def test_text_similarity(self):
        # Giống hệt
        self.assertAlmostEqual(_text_similarity("Xin chào các bạn", "xin chào các bạn"), 1.0)
        # Tương đồng cao
        sim = _text_similarity("Cậu bé đứng nhìn xa xăm", "Cậu bé đứng nhìn xa")
        self.assertGreater(sim, 0.7)
        # Khác biệt
        sim_diff = _text_similarity("Hôm nay trời đẹp", "Ngày mai trời mưa")
        self.assertLess(sim_diff, 0.5)

    def test_normalize_box_coords(self):
        x1, y1, x2, y2 = _normalize_box_coords({'x': 10, 'y': 80, 'w': 80, 'h': 15}, 1920, 1080)
        self.assertEqual(x1, 192)
        self.assertEqual(y1, 864)
        self.assertEqual(x2, 1728)
        self.assertEqual(y2, 1026)

    def test_bot_synthetic_video(self):
        # Tạo một video giả lập ngắn 3 giây (75 frames @ 25fps)
        temp_dir = tempfile.mkdtemp()
        vid_path = os.path.join(temp_dir, "test_synth.mp4")
        
        w, h, fps = 640, 360, 25
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(vid_path, fourcc, fps, (w, h))

        # Giây 0 - 1 (frames 0 - 25): Có chữ "CHÀO BẠN"
        # Giây 1 - 2 (frames 25 - 50): Trống (không có chữ)
        # Giây 2 - 3 (frames 50 - 75): Có chữ "TẠM BIỆT"
        for i in range(75):
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            # Vẽ nền tối
            frame[:] = (20, 20, 20)
            if i < 25:
                # Text ở giây đầu
                cv2.putText(frame, "CHAO BAN", (150, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
            elif i >= 50:
                # Text ở giây thứ 3
                cv2.putText(frame, "TAM BIET", (150, 320), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 3)
            out.write(frame)
        out.release()

        # Tạo tình huống:
        # File SRT chỉ có câu 1 ("CHAO BAN" từ 0s đến 1s).
        # Đoạn 2s-3s ("TAM BIET") bị MISS trong SRT.
        # Đồng thời file SRT có một câu ma ở giây 1.2s - 1.8s ("GHOST SUBTITLE").
        subtitles = [
            {
                "id": 1,
                "start": "00:00:00,000",
                "end": "00:00:01,000",
                "startSeconds": 0.0,
                "endSeconds": 1.0,
                "text": "CHAO BAN"
            },
            {
                "id": 2,
                "start": "00:00:01,200",
                "end": "00:00:01,800",
                "startSeconds": 1.2,
                "endSeconds": 1.8,
                "text": "CAU NAY LA PHU DE MA KHONG CO TRONG VIDEO"
            }
        ]

        bot = SubtitleInspectorBot()
        res = bot.inspect(
            vid_path,
            subtitles,
            ocr_region={'x': 10, 'y': 75, 'w': 80, 'h': 22},
            options={'check_missing': True, 'check_ghost': True, 'auto_fix': True}
        )

        self.assertTrue(res.get('success'))
        # Bot phải bắt được ít nhất 1 câu ghost (câu id 2)
        ghost_ids = [g['sub_id'] for g in res.get('ghost_warnings', [])]
        self.assertIn(2, ghost_ids, "Bot phải phát hiện câu id 2 là ghost sub!")

        # Bot phải phát hiện được câu sót ở đoạn cuối video ("TAM BIET")
        missing_texts = [m['text'].upper() for m in res.get('missing_warnings', [])]
        found_missing = any('TAM' in t or 'BIET' in t for t in missing_texts)
        self.assertTrue(found_missing, f"Bot phải phát hiện câu sót 'TAM BIET'! Kết quả: {missing_texts}")

        # Kiểm tra fixed_subtitles
        fixed = res.get('fixed_subtitles', [])
        self.assertGreater(len(fixed), len(subtitles) - len(res.get('ghost_warnings', [])))

        # Dọn dẹp
        try:
            os.remove(vid_path)
            os.rmdir(temp_dir)
        except Exception:
            pass

if __name__ == '__main__':
    unittest.main()
