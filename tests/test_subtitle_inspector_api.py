# -*- coding: utf-8 -*-
import unittest
import json
import os
from web_app import app
import license_manager

class TestSubtitleInspectorAPI(unittest.TestCase):

    def setUp(self):
        self.client = app.test_client()

    def test_apply_inspector_fixes_api(self):
        # Giả lập danh sách phụ đề ban đầu có câu 1 và câu 2 (ghost)
        subtitles = [
            {
                "id": 1,
                "start": "00:00:01,000",
                "end": "00:00:03,000",
                "startSeconds": 1.0,
                "endSeconds": 3.0,
                "text": "Câu hợp lệ"
            },
            {
                "id": 2,
                "start": "00:00:03,500",
                "end": "00:00:05,000",
                "startSeconds": 3.5,
                "endSeconds": 5.0,
                "text": "Câu ảo bị xóa"
            }
        ]

        # Danh sách câu missing cần thêm
        missing_to_add = [
            {
                "start": "00:00:06,000",
                "end": "00:00:08,000",
                "start_sec": 6.0,
                "end_sec": 8.0,
                "text": "Câu thoại mới vừa được bot tìm thấy"
            }
        ]

        # Yêu cầu xóa câu 2 (ghost)
        ghost_ids_to_remove = [2]

        response = self.client.post(
            '/api/subtitles/apply_inspector_fixes',
            data=json.dumps({
                "subtitles": subtitles,
                "missing_to_add": missing_to_add,
                "ghost_ids_to_remove": ghost_ids_to_remove
            }),
            content_type='application/json'
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('added_count'), 1)
        self.assertEqual(data.get('removed_count'), 1)

        result_subs = data.get('subtitles', [])
        # Danh sách phải có 2 câu: câu 1 cũ và câu missing mới
        self.assertEqual(len(result_subs), 2)
        # Câu 2 cũ không còn
        texts = [s['text'] for s in result_subs]
        self.assertIn("Câu hợp lệ", texts)
        self.assertIn("Câu thoại mới vừa được bot tìm thấy", texts)
        self.assertNotIn("Câu ảo bị xóa", texts)

if __name__ == '__main__':
    unittest.main()
