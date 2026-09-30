import os
import shutil
import json
import unittest
from unittest.mock import patch, MagicMock

from web_app import app
from subtitle_postprocessor import (
    time_to_seconds,
    seconds_to_srt_time,
    is_valid_translation,
    validate_subtitles_for_export,
    deterministic_normalize_subtitles,
    export_subtitles_to_srt_file
)
import custom_voices
import local_voice_engine
from ocr_module import get_editor_temp_dir

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestBatchEditorFixes(unittest.TestCase):
    def setUp(self):
        self.app = app.test_client()
        self.test_dir = os.path.join(ROOT_DIR, 'scratch', 'test_batch_fixes_suite')
        self.output_dir = os.path.join(self.test_dir, 'output')
        os.makedirs(self.output_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    # -------------------------------------------------------------------------
    # 1. Voice nam ra nam, voice nu ra nu, khong bao gio fallback cung ve Ngoc Huyen
    # -------------------------------------------------------------------------
    def test_gender_and_language_preservation_in_fallbacks(self):
        """Yeu cau 1: Voice nam luon ra nam, voice nu luon ra nu, khong fallback ve Ngoc Huyen."""
        # 1. Male Vietnamese voice fallback to Edge
        male_fallback = custom_voices.get_fallback_voice('local_minh_duc', target_provider='edge')
        profile = custom_voices.resolve_voice_profile(male_fallback)
        self.assertEqual(profile['gender'], 'male')
        self.assertNotIn('HoaiMy', male_fallback)
        self.assertNotIn('ngoc_huyen', male_fallback)

        # 2. Female Vietnamese voice fallback
        female_fallback = custom_voices.get_fallback_voice('local_ngoc_huyen', target_provider='edge')
        f_profile = custom_voices.resolve_voice_profile(female_fallback)
        self.assertEqual(f_profile['gender'], 'female')

        # 3. English Male voice MUST NOT fallback to Vietnamese Female (Ngoc Huyen)
        en_male_fallback = custom_voices.get_fallback_voice('edge_en-US-GuyNeural', target_provider='kokoro')
        en_profile = custom_voices.resolve_voice_profile(en_male_fallback)
        self.assertEqual(en_profile['gender'], 'male')
        self.assertIn('en', en_profile['lang'].lower())
        self.assertNotIn('ngoc_huyen', en_male_fallback)
        self.assertNotIn('HoaiMy', en_male_fallback)

        # 4. Error raised when no matching fallback exists if raise_on_missing=True
        with self.assertRaises(ValueError):
            custom_voices.get_fallback_voice('invalid_unknown_voice_xyz', target_provider='nonexistent_provider', raise_on_missing=True)

    def test_local_voice_engine_preset_selection_respects_gender(self):
        """local_voice_engine chon preset phai dung gioi tinh, khong hardcode ve Ngoc Huyen."""
        # Male voice
        male_preset = local_voice_engine.select_preset_for_voice('local_minh_duc', gender='male', lang='vi')
        self.assertTrue('Minh Đức' in male_preset or 'minh_duc' in male_preset.lower())

        # Female voice
        female_preset = local_voice_engine.select_preset_for_voice('local_ngoc_huyen', gender='female', lang='vi')
        self.assertTrue('Ngọc Huyền' in female_preset or 'ngoc_huyen' in female_preset.lower())

        # English Male voice
        en_male_preset = local_voice_engine.select_preset_for_voice('kokoro_am_adam', gender='male', lang='en')
        self.assertNotIn('ngoc_huyen', en_male_preset)

    # -------------------------------------------------------------------------
    # 2. Preview phai doc dung ngon ngu & cache da nhan to
    # -------------------------------------------------------------------------
    def test_voice_preview_language_and_multi_factor_cache(self):
        """Yeu cau 2: Preview phai doc dung ngon ngu cua voice va cache du voice+text+locale+speed+version."""
        # 1. Preview text mapping
        en_text = custom_voices.get_default_preview_text('en-US')
        self.assertIn('preview', en_text.lower())
        self.assertNotIn('Chào bạn, đây là', en_text)

        vi_text = custom_voices.get_default_preview_text('vi-VN')
        self.assertIn('giọng đọc', vi_text)

        zh_text = custom_voices.get_default_preview_text('zh-CN')
        self.assertTrue(any(ord(c) > 0x4e00 for c in zh_text))

        # 2. Preview API endpoint rejects language mismatch or properly applies locale
        res = self.app.post('/api/tts/preview', json={
            'voice': 'edge_en-US-GuyNeural',
            'lang': 'en',
            'locale': 'en-US',
            'gender': 'male',
            'speed': 1.0,
            # Gửi text tiếng Việt sai ngôn ngữ -> backend phải báo lỗi hoặc từ chối mismatch
            'text': 'Xin chào đây là tiếng Việt thử nghiệm'
        })
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertIn('mismatch', data['error'].lower())

    # -------------------------------------------------------------------------
    # 3. Khi subtitles_enabled=false, tuyet doi khong burn-in subtitle
    # -------------------------------------------------------------------------
    def test_subtitles_disabled_guarantees_no_burnin_filter(self):
        """Yeu cau 3: subtitles_enabled=false thi backend khong duoc tao filter subtitles/ass."""
        from routes.video_edit import sanitize_filter_complex_graph

        # gia lap filter complex co subtitles filter
        graph_with_subs = "scale=1920:1080,subtitles='C\\:/temp/test.srt',fps=30"
        cleaned_graph = sanitize_filter_complex_graph(graph_with_subs, subtitles_enabled=False)
        self.assertNotIn('subtitles=', cleaned_graph)
        self.assertNotIn('test.srt', cleaned_graph)

        # gia lap ass filter
        graph_with_ass = "scale=1920:1080,ass='C\\:/temp/test.ass':fontsdir='C\\:/fonts',boxblur=2"
        cleaned_ass = sanitize_filter_complex_graph(graph_with_ass, subtitles_enabled=False)
        self.assertNotIn('ass=', cleaned_ass)
        self.assertNotIn('test.ass', cleaned_ass)

    # -------------------------------------------------------------------------
    # 4. Hau kiem SRT deterministic: sort, drop loi, overlap, gop duplicate < 0.7s
    # -------------------------------------------------------------------------
    def test_deterministic_srt_postprocessor(self):
        """Yeu cau 4: Sort, xoa loi, xu ly overlap, gop duplicate neu khoang cach < 0.7s, danh lai ID."""
        raw_subs = [
            # 1. Sai thu tu (start tre hon cau sau)
            {
                'id': 99,
                'start': '00:00:05,000',
                'end': '00:00:07,000',
                'text': 'Câu thứ hai',
                'translation': 'Câu thứ hai'
            },
            # 2. Cau dau tien
            {
                'id': 1,
                'start': '00:00:01,000',
                'end': '00:00:03,000',
                'text': 'Câu đầu tiên',
                'translation': 'Câu đầu tiên'
            },
            # 3. Cau trung lap ngay sau do cach 0.3s (< 0.7s) -> Bat buoc phai gop
            {
                'id': 2,
                'start': '00:00:03,300',
                'end': '00:00:04,500',
                'text': 'Câu đầu tiên',
                'translation': 'Câu đầu tiên'
            },
            # 4. Cau loi timestamp (end <= start) -> Bat buoc phai loai bo
            {
                'id': 3,
                'start': '00:00:10,000',
                'end': '00:00:09,000',
                'text': 'Câu rác lỗi',
                'translation': 'Câu rác lỗi'
            },
            # 5. Cau overlap voi cau truoc
            {
                'id': 4,
                'start': '00:00:06,500',  # de len cau 05,000 - 07,000
                'end': '00:00:08,000',
                'text': 'Câu thứ ba',
                'translation': 'Câu thứ ba'
            }
        ]

        normalized = deterministic_normalize_subtitles(raw_subs, min_gap_sec=0.7)

        # Kiem tra ket qua
        # 1. Cau loi bi xoa -> khong con "Câu rác lỗi"
        texts = [s['text'] for s in normalized]
        self.assertNotIn('Câu rác lỗi', texts)

        # 2. Cau trung lap cach 0.3s (< 0.7s) da duoc gop vao cau dau tien
        self.assertEqual(texts.count('Câu đầu tiên'), 1)
        first_sub = normalized[0]
        self.assertEqual(first_sub['id'], 1)
        self.assertEqual(first_sub['start'], '00:00:01,000')
        # Thoi gian ket thuc phai keo dai den 00:00:04,500
        self.assertEqual(first_sub['end'], '00:00:04,500')

        # 3. Thu tu da duoc sap xep lai theo thoi gian
        for i in range(len(normalized) - 1):
            curr_start = time_to_seconds(normalized[i]['start'])
            next_start = time_to_seconds(normalized[i+1]['start'])
            self.assertLessEqual(curr_start, next_start)

        # 4. ID duoc danh lai tu 1 den N lien tuc
        expected_ids = list(range(1, len(normalized) + 1))
        actual_ids = [s['id'] for s in normalized]
        self.assertEqual(actual_ids, expected_ids)

    def test_duplicate_gap_greater_than_threshold_not_merged(self):
        """Neu khoang cach >= 0.7s thi khong duoc tu tien gop cau."""
        subs = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:03,000', 'text': 'Xin chào', 'translation': 'Xin chào'},
            # Gap la 1.0s (> 0.7s) -> khong gop
            {'id': 2, 'start': '00:00:04,000', 'end': '00:00:06,000', 'text': 'Xin chào', 'translation': 'Xin chào'}
        ]
        norm = deterministic_normalize_subtitles(subs, min_gap_sec=0.7)
        self.assertEqual(len(norm), 2)

    def test_deterministic_normalize_preserves_custom_ids_when_reindex_false(self):
        """Kiem tra reindex=False bao toan nguyen ven ID cua cac chunk (vi du 101..103)."""
        subs = [
            {'id': 101, 'start': '00:01:00,000', 'end': '00:01:02,000', 'text': 'Câu 101', 'translation': 'Dịch 101'},
            {'id': 102, 'start': '00:01:03,000', 'end': '00:01:05,000', 'text': 'Câu 102', 'translation': 'Dịch 102'},
            {'id': 103, 'start': '00:01:06,000', 'end': '00:01:08,000', 'text': 'Câu 103', 'translation': 'Dịch 103'},
        ]
        norm = deterministic_normalize_subtitles(subs, reindex=False)
        self.assertEqual(len(norm), 3)
        self.assertEqual([s['id'] for s in norm], [101, 102, 103])

    # -------------------------------------------------------------------------
    # 5. Khong cho export neu con cau chua dich, song ngu, hoac sai target language
    # -------------------------------------------------------------------------
    def test_subtitle_validator_rejects_untranslated_and_corrupt(self):
        """Yeu cau 5: Chan export neu con chua dich, con chu Han, song ngu hoac sai target lang."""
        # 1. Ban dich con chu Han khi dich sang tieng Viet
        bad_subs_zh = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:03,000', 'text': '你好', 'translation': '你好世界'}
        ]
        is_val, errors, _ = validate_subtitles_for_export(bad_subs_zh, target_lang='vi')
        reason = '; '.join(errors)
        self.assertFalse(is_val)
        self.assertTrue('chữ Hán' in reason or 'không hợp lệ' in reason)

        # 2. Ban dich rong
        bad_subs_empty = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:02,000', 'text': 'Hello', 'translation': ''}
        ]
        is_val, errors, _ = validate_subtitles_for_export(bad_subs_empty, target_lang='vi')
        reason = '; '.join(errors)
        self.assertFalse(is_val)
        self.assertIn('Chưa có bản dịch', reason)

        # 3. Ban dich chua thong bao loi API
        bad_subs_err = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:03,000', 'text': 'Hello', 'translation': '[Lỗi API Quota Exceeded]'}
        ]
        is_val, errors, _ = validate_subtitles_for_export(bad_subs_err, target_lang='vi')
        reason = '; '.join(errors)
        self.assertFalse(is_val)
        self.assertTrue('lỗi' in reason.lower() or 'không hợp lệ' in reason.lower())

        # 4. Target la tieng Anh nhung ban dich lai ra tieng Viet co dau
        bad_subs_en = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:03,000', 'text': '你好', 'translation': 'Xin chào các bạn'}
        ]
        is_val, errors, _ = validate_subtitles_for_export(bad_subs_en, target_lang='en')
        reason = '; '.join(errors)
        self.assertFalse(is_val)
        self.assertTrue('tiếng Việt' in reason or 'không hợp lệ' in reason)

        # 5. Ban dich hop le
        good_subs = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:03,000', 'text': '你好', 'translation': 'Xin chào bạn'}
        ]
        is_val, errors, _ = validate_subtitles_for_export(good_subs, target_lang='vi')
        self.assertTrue(is_val)

    # -------------------------------------------------------------------------
    # 6 & 7. Fresh run khong dung bat ky cache/artifact cu nao
    # -------------------------------------------------------------------------
    def test_fresh_run_purges_and_ignores_cached_artifacts(self):
        """Yeu cau 7: fresh_run=true phai xoa sach temp artifacts cu va khong dung cached dub/manifest."""
        video_name = 'test_video_flow.mp4'
        video_path = os.path.join(self.test_dir, video_name)
        with open(video_path, 'wb') as f:
            f.write(b'fake_video_bytes')

        editor_temp = get_editor_temp_dir(self.output_dir, video_path)
        os.makedirs(editor_temp, exist_ok=True)

        # Tao cac file cache rac gia lap
        stale_dub = os.path.join(editor_temp, 'dubbed_timeline.wav')
        stale_stem = os.path.join(editor_temp, 'stem_cleaned.wav')
        stale_boxes = os.path.join(editor_temp, 'ai_blur_boxes.json')
        stale_manifest = os.path.join(editor_temp, 'tts_manifest.json')

        for p in [stale_dub, stale_stem, stale_boxes, stale_manifest]:
            with open(p, 'w', encoding='utf-8') as f:
                f.write('stale cache data')
            self.assertTrue(os.path.exists(p))

        # Goi api check cache voi fresh_run=True
        res = self.app.post('/api/editor/check_cache', json={
            'input_video': video_path,
            'output_dir': self.output_dir,
            'fresh_run': True
        })
        self.assertEqual(res.status_code, 200)
        d = res.get_json()
        self.assertFalse(d['has_cache'])

        # Xac minh cac file cache rac da bi don dep sach se
        self.assertFalse(os.path.exists(stale_dub))
        self.assertFalse(os.path.exists(stale_stem))
        self.assertFalse(os.path.exists(stale_boxes))
        self.assertFalse(os.path.exists(stale_manifest))

    # -------------------------------------------------------------------------
    # 8. Khong ghi de SRT nguon mac dinh
    # -------------------------------------------------------------------------
    def test_source_srt_not_overwritten_by_default(self):
        """Yeu cau 8: Xuat SRT mac dinh luu sang _novacut.srt, khong de len .srt goc cua nguoi dung."""
        video_path = os.path.join(self.test_dir, 'my_movie.mp4')
        with open(video_path, 'wb') as f:
            f.write(b'dummy')

        source_srt = os.path.join(self.test_dir, 'my_movie.srt')
        with open(source_srt, 'w', encoding='utf-8') as f:
            f.write("1\n00:00:01,000 --> 00:00:02,000\nOriginal Subtitle\n")

        new_subtitles = [
            {'id': 1, 'start': '00:00:01,000', 'end': '00:00:02,000', 'text': 'Original Subtitle', 'translation': 'Phụ đề mới đã dịch'}
        ]

        # Goi export_temp mac dinh (replace_original = False)
        res = self.app.post('/api/subtitles/export_temp', json={
            'video_path': video_path,
            'target_srt_path': source_srt,
            'replace_original': False,
            'subtitles': new_subtitles
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        saved_path = data.get('srt_path', '')

        # File duoc luu phai la _novacut.srt
        self.assertIn('_novacut.srt', saved_path)
        self.assertTrue(os.path.exists(saved_path))

        # File goc phai duoc bao toan 100%
        with open(source_srt, 'r', encoding='utf-8') as f:
            original_content = f.read()
        self.assertIn('Original Subtitle', original_content)
        self.assertNotIn('Phụ đề mới đã dịch', original_content)

    def test_translate_subtitles_preserves_chunk_ids(self):
        """Kiem tra /api/translate_subtitles khong duoc danh lai ID thanh 1..N khi dich chunk (vi du ID 101..103)."""
        subs = [
            {'id': 101, 'start': '00:01:00,000', 'end': '00:01:02,000', 'text': 'Xin chào', 'translation': 'Hello'},
            {'id': 102, 'start': '00:01:03,000', 'end': '00:01:05,000', 'text': 'Tạm biệt', 'translation': 'Goodbye'},
            {'id': 103, 'start': '00:01:06,000', 'end': '00:01:08,000', 'text': 'Cảm ơn', 'translation': 'Thank you'}
        ]
        with patch('local_ai_manager.translate_subtitles_local') as mock_local:
            mock_local.return_value = (subs, {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20})
            res = self.app.post('/api/translate_subtitles', json={
                'mode': 'local',
                'subtitles': subs,
                'source_lang': 'vi',
                'target_lang': 'en'
            })
            self.assertEqual(res.status_code, 200)
            data = res.get_json()
            returned_subs = data.get('subtitles', [])
            self.assertEqual(len(returned_subs), 3)
            self.assertEqual([s['id'] for s in returned_subs], [101, 102, 103])
    def test_normalize_dedup_handles_read_srt_format(self):
        """Kiem tra deterministic_normalize_subtitles khong bao gio bi rot phu de tu /api/read_srt."""
        read_srt_subs = [
            {
                'id': '1',
                'time': '00:00:00.440 - 00:00:03.480',
                'startSeconds': 0.44,
                'endSeconds': 3.48,
                'text': '这台宝马640GT到底经历了什么？',
                'translation': ''
            },
            {
                'id': '2',
                'time': '00:00:03.800 - 00:00:06.120',
                'startSeconds': 3.80,
                'endSeconds': 6.12,
                'text': '车贩子修事故车成本有多低？',
                'translation': ''
            }
        ]
        norm = deterministic_normalize_subtitles(read_srt_subs, min_gap_sec=0.7)
        self.assertEqual(len(norm), 2)
        self.assertEqual(norm[0]['startSeconds'], 0.44)
        self.assertEqual(norm[0]['endSeconds'], 3.48)
        self.assertEqual(norm[1]['startSeconds'], 3.80)
        self.assertEqual(norm[1]['endSeconds'], 6.12)
        self.assertIn('start', norm[0])
        self.assertIn('end', norm[0])
        self.assertIn('time', norm[0])

    def test_api_subtitles_normalize_dedup_endpoint(self):
        """Kiem tra endpoint POST /api/subtitles/normalize_dedup."""
        subs = [
            {
                'id': '1',
                'startSeconds': 1.0,
                'endSeconds': 3.0,
                'text': 'Hello world',
                'translation': 'Xin chào thế giới'
            },
            {
                'id': '2',
                'startSeconds': 3.2,
                'endSeconds': 5.0,
                'text': 'Goodbye',
                'translation': 'Tạm biệt'
            }
        ]
        res = self.app.post('/api/subtitles/normalize_dedup', json={
            'subtitles': subs,
            'min_gap_sec': 0.7
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(len(data.get('subtitles', [])), 2)
        s0 = data['subtitles'][0]
        self.assertEqual(s0['startSeconds'], 1.0)
        self.assertEqual(s0['endSeconds'], 3.0)
        self.assertEqual(s0['translation'], 'Xin chào thế giới')

    def test_validate_subtitles_for_export_en(self):
        """Kiem tra validate_subtitles_for_export voi target_lang='en'."""
        en_subs = [
            {
                'id': 1,
                'startSeconds': 1.0,
                'endSeconds': 3.0,
                'text': '这台宝马640GT到底经历了什么？',
                'translation': 'What exactly happened to this BMW 640GT?'
            }
        ]
        is_val, errs, inv_ids = validate_subtitles_for_export(en_subs, target_lang='en')
        self.assertTrue(is_val)
        self.assertEqual(len(errs), 0)
        self.assertEqual(len(inv_ids), 0)


if __name__ == '__main__':
    unittest.main()

