# -*- coding: utf-8 -*-
"""
test_batch_subtitle_inspector.py - Unit tests for AI Subtitle Inspector integration in Batch Video Editor
"""

import os
import unittest
import json
from unittest.mock import patch

from web_app import app
import subtitle_inspector

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestBatchSubtitleInspector(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_frontend_ui_elements_exist(self):
        """Kiểm tra các thành phần UI của Bot Soát Sub AI trong Biên tập hàng loạt"""
        index_html_path = os.path.join(ROOT_DIR, 'web', 'index.html')
        with open(index_html_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Kiểm tra nút bấm trên toolbar
        self.assertIn('btnBatchInspectSubtitles', content, "Phải có nút btnBatchInspectSubtitles trên toolbar batch editor")
        self.assertIn('🤖 Soát &amp; Bù Sub AI', content)

        # Kiểm tra toggle và speed mode trong card cài đặt
        self.assertIn('batch_enableSubtitleInspector', content, "Phải có toggle batch_enableSubtitleInspector")
        self.assertIn('batch_inspectorSpeedMode', content, "Phải có selector batch_inspectorSpeedMode")
        self.assertIn('batch_translationCleanMode', content, "Phải có selector batch_translationCleanMode")

    def test_batch_editor_js_functions_exist(self):
        """Kiểm tra mã nguồn JavaScript của module batch_editor.js"""
        js_path = os.path.join(ROOT_DIR, 'web', 'js', 'features', 'batch_editor.js')
        with open(js_path, 'r', encoding='utf-8') as f:
            content = f.read()

        self.assertIn('runSubtitleInspectionOnItem', content, "Phải export hàm runSubtitleInspectionOnItem")
        self.assertIn('startBatchSubtitleInspection', content, "Phải export hàm startBatchSubtitleInspection")
        self.assertIn('btnBatchInspectSubtitles', content, "Phải gắn event listener cho btnBatchInspectSubtitles")
        self.assertIn('batch_enableSubtitleInspector', content, "Phải đọc toggle batch_enableSubtitleInspector")
        self.assertIn('inspected', content, "Phải hỗ trợ badge trạng thái inspected")
        self.assertIn('translation_clean_mode', content, "Phải cấu hình translation_clean_mode")
        self.assertIn('translate_only', content, "Phải hỗ trợ chế độ translate_only")

    def test_api_inspect_and_auto_fix_pipeline(self):
        """Kiểm tra luồng API inspect và apply fixes với license bypass"""
        with patch('routes.subtitles._require_editor', return_value=None):
            # 1. Test API apply fixes
            original_subs = [
                {
                    "id": 1,
                    "start": "00:00:01,000",
                    "end": "00:00:03,000",
                    "startSeconds": 1.0,
                    "endSeconds": 3.0,
                    "text": "Câu thoại số 1"
                },
                {
                    "id": 2,
                    "start": "00:00:03,500",
                    "end": "00:00:04,500",
                    "startSeconds": 3.5,
                    "endSeconds": 4.5,
                    "text": "Câu thoại ma ảo không có trong video"
                }
            ]

            ghost_warnings = [
                {
                    "type": "ghost",
                    "sub_id": 2,
                    "sub_index": 1,
                    "text": "Câu thoại ma ảo không có trong video"
                }
            ]

            missing_warnings = [
                {
                    "type": "missing",
                    "start": "00:00:05,000",
                    "end": "00:00:07,500",
                    "start_sec": 5.0,
                    "end_sec": 7.5,
                    "text": "Câu thoại bị sót được AI tìm thấy"
                }
            ]

            fix_res = self.client.post('/api/subtitles/apply_inspector_fixes', json={
                "subtitles": original_subs,
                "missing_warnings": missing_warnings,
                "ghost_warnings": ghost_warnings,
                "remove_ghosts": True,
                "auto_add_missing": True
            })

            self.assertEqual(fix_res.status_code, 200)
            fix_data = fix_res.get_json()
            self.assertTrue(fix_data.get('success'))
            fixed_subs = fix_data.get('fixed_subtitles', [])

            # Kiểm tra: Câu ma id 2 phải bị loại bỏ
            ghost_found = any('ma ảo' in s.get('text', '') for s in fixed_subs)
            self.assertFalse(ghost_found, "Câu ma phải bị loại bỏ khỏi danh sách")

            # Kiểm tra: Câu sót phải được bổ sung vào
            missing_found = any('bị sót' in s.get('text', '') for s in fixed_subs)
            self.assertTrue(missing_found, "Câu sót phải được tự động bổ sung vào danh sách")

            # Kiểm tra số lượng câu sau khi sửa
            self.assertEqual(len(fixed_subs), 2)


if __name__ == '__main__':
    unittest.main()
