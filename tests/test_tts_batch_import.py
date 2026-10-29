import unittest
import os
import io
import sys
import json
import tempfile
import shutil

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from web_app import app
from routes.tts import extract_text_and_stats_from_bytes


class TestTTSBatchImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()

    def test_extract_text_and_stats_txt(self):
        txt_bytes = "Đây là văn bản thử nghiệm kịch bản chương một của câu chuyện.".encode('utf-8')
        res = extract_text_and_stats_from_bytes("chuong_01.txt", txt_bytes)
        self.assertEqual(res['filename'], 'chuong_01.txt')
        self.assertEqual(res['title'], 'chuong_01')
        self.assertIn("chương một", res['text'])
        self.assertGreater(res['stats']['word_count'], 5)
        self.assertGreater(res['stats']['char_count'], 20)

    def test_import_batch_files_api(self):
        file1 = (io.BytesIO("Nội dung kịch bản tập 1: Hoàng tử xuất hiện.".encode('utf-8')), 'tap_01.txt')
        file2 = (io.BytesIO("1\n00:00:01,000 --> 00:00:03,000\nNội dung kịch bản tập 2: Công chúa trở về.\n".encode('utf-8')), 'tap_02.srt')

        data = {
            'files': [file1, file2]
        }
        res = self.client.post('/api/tts/import_batch_files', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        res_json = res.get_json()
        self.assertTrue(res_json.get('success'))
        self.assertEqual(res_json.get('total'), 2)
        items = res_json.get('items', [])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['filename'], 'tap_01.txt')
        self.assertIn("Hoàng tử xuất hiện", items[0]['text'])
        self.assertEqual(items[1]['filename'], 'tap_02.srt')
        self.assertIn("Công chúa trở về", items[1]['text'])
        self.assertNotIn("-->", items[1]['text'])

    def test_import_batch_folder_api(self):
        temp_dir = tempfile.mkdtemp(prefix="tts_batch_test_")
        try:
            # Create files with numeric names to test natural sorting: chap_1, chap_2, chap_10
            with open(os.path.join(temp_dir, 'chap_10.txt'), 'w', encoding='utf-8') as f:
                f.write("Tập 10: Trận chiến kết thúc.")
            with open(os.path.join(temp_dir, 'chap_1.txt'), 'w', encoding='utf-8') as f:
                f.write("Tập 1: Khởi đầu cuộc phiêu lưu.")
            with open(os.path.join(temp_dir, 'chap_2.txt'), 'w', encoding='utf-8') as f:
                f.write("Tập 2: Đồng đội mới gia nhập.")

            res = self.client.post('/api/tts/import_batch_folder', json={'folder_path': temp_dir})
            self.assertEqual(res.status_code, 200)
            res_json = res.get_json()
            self.assertTrue(res_json.get('success'))
            self.assertEqual(res_json.get('total'), 3)

            # Natural sort should ensure: chap_1, chap_2, chap_10 (not chap_1, chap_10, chap_2)
            items = res_json.get('items', [])
            self.assertEqual(items[0]['filename'], 'chap_1.txt')
            self.assertEqual(items[1]['filename'], 'chap_2.txt')
            self.assertEqual(items[2]['filename'], 'chap_10.txt')
            self.assertIn("Khởi đầu", items[0]['text'])
            self.assertIn("Đồng đội", items[1]['text'])
            self.assertIn("Trận chiến", items[2]['text'])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == '__main__':
    unittest.main()
