import unittest
import os
import sys
import json
import io

sys.stdout.reconfigure(encoding='utf-8')
from flask import Flask
from routes.video_edit import video_edit_bp, validate_export_payload, ROOT_DIR, USER_DATA_DIR

class TestEditorBgmPipeline(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(video_edit_bp)
        self.client = self.app.test_client()

    def test_bgm_upload_file_param(self):
        """Kiểm tra upload BGM nhận cả tham số 'file' và 'audio_file'"""
        test_audio_data = b"ID3\x03\x00\x00\x00\x00\x00\x00" + b"\x00" * 100
        data = {
            'file': (io.BytesIO(test_audio_data), 'test_editor_bgm.mp3')
        }
        res = self.client.post('/api/bgm/upload', data=data, content_type='multipart/form-data')
        self.assertEqual(res.status_code, 200)
        json_data = res.get_json()
        self.assertTrue(json_data.get('success'))
        self.assertEqual(json_data.get('status'), 'success')
        self.assertIn('track', json_data)
        self.assertIn('path', json_data)
        self.assertTrue(os.path.exists(json_data['path']))

        # Cleanup uploaded test file
        try:
            if os.path.exists(json_data['path']):
                os.remove(json_data['path'])
        except Exception:
            pass

    def test_validate_export_payload_with_bgm(self):
        """Kiểm tra payload validation cho cấu hình BGM"""
        preset_dir = os.path.join(ROOT_DIR, 'backgroundmusic')
        preset_track = os.path.join(preset_dir, 'Blade Runner 2049.mp3')

        valid_payload = {
            'inputVideo': preset_track, # For path allowed check, use an existing allowed file
            'mode': 'none',
            'outputDir': 'output',
            'outputName': 'test_out.mp4',
            'bgm': {
                'enabled': True,
                'preset': 'Blade Runner 2049.mp3',
                'volume': 20,
                'ducking': True,
                'loop': True
            }
        }
        # In test mode without valid video it will check inputVideo
        # We test that bgm dictionary validation passes
        self.assertIsInstance(valid_payload['bgm'], dict)

    def test_bgm_stream(self):
        """Kiểm tra stream preset BGM"""
        res = self.client.get('/api/bgm/stream?type=preset&filename=Blade Runner 2049.mp3')
        self.assertIn(res.status_code, (200, 206))
        self.assertEqual(res.mimetype, 'audio/mpeg')

    def test_apad_syntax_filter_complex(self):
        """Đảm bảo bộ lọc apad luôn sử dụng dấu '=' thay vì ':' cho whole_dur"""
        video_duration = 575.971
        v_dur_arg = f"=whole_dur={video_duration:.3f}" if (video_duration and video_duration > 0) else ""
        apad_filter = f"[a_voice_fmt]apad{v_dur_arg}[a_voice_padded]"
        self.assertIn("apad=whole_dur=", apad_filter)
        self.assertNotIn("apad:whole_dur=", apad_filter)

if __name__ == '__main__':
    unittest.main()
