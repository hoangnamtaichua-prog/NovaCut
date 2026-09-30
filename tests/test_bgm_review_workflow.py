import unittest
import os
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')
from flask import Flask
from routes.video_edit import video_edit_bp

class TestBgmAndReviewWorkflow(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(video_edit_bp)
        self.client = self.app.test_client()

    def test_bgm_list(self):
        res = self.client.get('/api/bgm/list')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('status'), 'success')
        self.assertIn('tracks', data)
        self.assertIn('files', data)
        
        # Check if No-Copyright tracks exist
        tracks = data['tracks']
        self.assertGreater(len(tracks), 0)
        safe_tracks = [t for t in tracks if t.get('is_safe')]
        self.assertGreaterEqual(len(safe_tracks), 5, "At least 5 No-Copyright tracks should be available")
        print(f"Total BGM tracks: {len(tracks)}, Safe tracks: {len(safe_tracks)}")
        for st in safe_tracks:
            print(f"  -> {st['name']} ({st.get('genre')})")

    def test_pipeline_import(self):
        import auto_edit_pipeline
        self.assertTrue(hasattr(auto_edit_pipeline, 'run_auto_edit_workflow'))
        self.assertTrue(hasattr(auto_edit_pipeline, 'run_narration_workflow'))

if __name__ == '__main__':
    unittest.main()
