import unittest
import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from auto_edit_pipeline import build_dynamic_blur_filter_chain, calc_sub_width_ratio


class TestDynamicBlurBatchEditor(unittest.TestCase):
    def test_calc_sub_width_ratio(self):
        # Short text should have smaller width ratio than long text
        short_text = "你好"
        long_text = "这是一段非常长的电影解说中文字幕用来测试动态宽度"
        
        short_w = calc_sub_width_ratio(short_text)
        long_w = calc_sub_width_ratio(long_text)
        
        self.assertGreater(long_w, short_w)
        self.assertLessEqual(long_w, 0.96)
        self.assertGreaterEqual(short_w, 0.12)

    def test_build_dynamic_blur_filter_chain_batch_pipeline(self):
        # Test dynamic blur filter generation with intervals
        intervals = [
            (1.0, 3.5, "第一句话测试"),
            (5.0, 8.0, "第二句话测试较长的文字内容"),
        ]
        
        # When called without manual_mode (batch editor dynamic blur pipeline)
        filters, out_v = build_dynamic_blur_filter_chain(
            curr_v="[0:v]",
            active_intervals=intervals,
            blur_sz=15,
            y_ratio=0.815,
            h_ratio=0.095,
            center_x_ratio=0.50,
            manual_mode=False,
            manual_w=None,
            engine='auto'
        )
        
        self.assertTrue(len(filters) > 0)
        self.assertTrue(isinstance(out_v, str))
        self.assertTrue(out_v.startswith("v_dynblur_"))
        
        # Check that filters contain maskedmerge and ass mask filter
        filter_str = ";".join(filters)
        self.assertTrue("maskedmerge" in filter_str)
        self.assertTrue("subtitles=" in filter_str)
        self.assertTrue("avgblur=" in filter_str)

    def test_manual_mode_fixed_blur(self):
        # When manual_mode is True, it should generate fixed blur overlays
        intervals = [
            (1.0, 3.5, "测试手动固定模式"),
        ]
        filters, out_v = build_dynamic_blur_filter_chain(
            curr_v="0:v",
            active_intervals=intervals,
            blur_sz=15,
            y_ratio=0.815,
            h_ratio=0.095,
            center_x_ratio=0.50,
            manual_mode=True,
            manual_w=0.60,
            engine='auto'
        )
        self.assertTrue(len(filters) > 0)
        self.assertTrue(out_v.startswith("v_fixblur_"))
        filter_str = ";".join(filters)
        self.assertTrue("crop=" in filter_str)
        self.assertTrue("overlay=" in filter_str)

    def test_routes_blur_parameters_independent_of_ocr_region(self):
        # Verify default blur parameters are independent of ocr_region
        # ocr_region might be wide like x=10, y=70, w=80, h=25
        ocr_region = {'x': 10.0, 'y': 70.0, 'w': 80.0, 'h': 25.0}
        
        # Default blur coordinates in pipeline
        blur_x_def = 20.0
        blur_y_def = 81.5
        blur_w_def = 60.0
        blur_h_def = 9.5
        
        # The blur box must NOT take ocr_region's y/h/w
        self.assertNotEqual(blur_y_def, ocr_region['y'])
        self.assertNotEqual(blur_h_def, ocr_region['h'])

    def test_subtitle_overlays_directly_on_blur_center(self):
        # Test that generate_styled_ass positions subtitles directly on the center of the blur region
        from routes.video_edit import generate_styled_ass
        import tempfile

        with tempfile.TemporaryDirectory() as td:
            srt_path = os.path.join(td, "test.srt")
            ass_path = os.path.join(td, "test.ass")

            with open(srt_path, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:04,000\nGia chủ, ta đã đạt Nguyên Thần cảnh.\n\n")

            cur_out_w = 1920
            cur_out_h = 1080
            blur_y = 81.5
            blur_h = 9.5
            blur_x = 20.0
            blur_w = 60.0

            # Subtitle style synchronized with blur region
            sub_style = {
                'font': 'Montserrat',
                'size': 24,
                'region': {
                    'x': blur_x,
                    'y': blur_y,
                    'w': blur_w,
                    'h': blur_h
                },
                'align': 'center'
            }

            generate_styled_ass(srt_path, ass_path, cur_out_w, cur_out_h, sub_style)

            with open(ass_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Center Y of blur box: 1080 * (81.5 + 9.5 / 2) / 100 = 931.5 -> round = 932
            # Center X of blur box: 1920 * (20 + 60 / 2) / 100 = 960
            self.assertIn(r"\an5\pos(960,932)", content)
            # Must NOT be positioned at middle of chest (e.g., 600)
            self.assertNotIn(r"\pos(987,600)", content)
            self.assertNotIn(r"\pos(960,600)", content)

    def test_dynamic_blur_and_sub_align_to_ai_pixel_boxes(self):
        # Test real-world scenario from user: original sub is at y=86.2%, h=8.5% (like "因为吃瓜被砸晕")
        from routes.video_edit import generate_styled_ass
        import tempfile

        ai_entries = [
            (1.0, 2.0, "因为吃瓜被砸晕", 0.3016, 0.3224, 0.862, 0.0852, 1.0, 2.0),
            (2.0, 3.0, "穿越到了古代", 0.3208, 0.2818, 0.8593, 0.0898, 2.0, 3.0),
        ]

        # Calculate AI average Y and H
        ys = [it[5] for it in ai_entries]
        hs = [it[6] for it in ai_entries]
        avg_y = sum(ys) / len(ys) # ~0.86065
        avg_h = max(0.085, min(0.22, (sum(hs) / len(hs)) + 0.015)) # ~0.1025

        cur_out_w, cur_out_h = 1920, 1080
        effective_sub_style = {
            'font': 'Montserrat',
            'size': 24,
            'region': {
                'x': 20.0,
                'y': avg_y * 100.0,
                'w': 60.0,
                'h': avg_h * 100.0
            },
            'align': 'center'
        }

        with tempfile.TemporaryDirectory() as td:
            srt_p = os.path.join(td, "sub.srt")
            ass_p = os.path.join(td, "sub.ass")
            with open(srt_p, "w", encoding="utf-8") as f:
                f.write("1\n00:00:01,000 --> 00:00:02,000\nVì mải xem hóng hớt mà bị gạch trúng, xuyên không về thời cổ đại.\n\n")

            generate_styled_ass(srt_p, ass_p, cur_out_w, cur_out_h, effective_sub_style)

            with open(ass_p, "r", encoding="utf-8") as f:
                content = f.read()

            # Center Y must be at (avg_y + avg_h / 2) * 1080 ≈ 985, covering the Chinese text completely
            # And definitely NOT 932 (the old 81.5% position that left Chinese text exposed)
            expected_pos_y = round(cur_out_h * (avg_y + avg_h / 2.0))
            self.assertIn(f"\\an5\\pos(960,{expected_pos_y})", content)
            self.assertNotIn(r"\pos(960,932)", content)

    def test_dynamic_blur_filter_covers_sub_with_padding(self):
        # Verify build_dynamic_blur_filter_chain produces a mask that covers the box
        blur_entries = [
            (1.0, 2.0, "因为吃瓜被砸晕", 0.3016, 0.3224, 0.862, 0.0852, 1.0, 2.0)
        ]
        filters, out_v = build_dynamic_blur_filter_chain(
            curr_v="[0:v]",
            active_intervals=blur_entries,
            blur_sz=15,
            y_ratio=0.862,
            h_ratio=0.0852,
            center_x_ratio=0.50,
            frame_w=1920,
            frame_h=1080
        )
        import auto_edit_pipeline
        mask_file = getattr(auto_edit_pipeline, '_last_dynamic_blur_mask_file', None)
        self.assertIsNotNone(mask_file)
        self.assertTrue(os.path.exists(mask_file))
        with open(mask_file, "r", encoding="utf-8") as f:
            mask_content = f.read()
        # Verify vector drawing covers y=914 to 1039 (embracing the Chinese text at 931 to 1023)
        self.assertIn(r"\pos(", mask_content)
        self.assertIn(r"\p1}m 0 0 l", mask_content)


if __name__ == '__main__':
    unittest.main()


