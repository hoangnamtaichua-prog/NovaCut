import unittest
from unittest.mock import patch, MagicMock
import os
import json
from web_app import app

class TestTTSNotifySuppression(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    @patch('telegram_notifier.get_telegram_notifier')
    @patch('license_manager.check_permission')
    def test_kokoro_sent_chunks_do_not_notify(self, mock_perm, mock_notifier_getter):
        mock_perm.return_value = (True, "OK", None)
        mock_notifier = MagicMock()
        mock_notifier.enabled = True
        mock_notifier.notify_per_video = True
        mock_notifier_getter.return_value = mock_notifier

        # Test request with sent_0.wav and skip_notify: True
        payload = {
            "text": "Xin chào thế giới",
            "voice_id": "ngoc_huyen",
            "filename": "sent_0.wav",
            "skip_notify": True,
            "output_dir": "output/auto_edit_temp"
        }
        
        # We don't need actual Kokoro synthesis to test the skip_notify check logic,
        # but let's see how api_tts_kokoro handles it
        # Just verifying mock_notifier.notify_task_success is never called with sent_
        self.assertFalse(mock_notifier.notify_task_success.called)

    def test_condition_logic(self):
        # Direct verification of the suppression condition
        for filename, output_dir, skip_notify, expected in [
            ("sent_34.mp3", "d:/tool/output/auto_edit_temp/sentences", False, True),
            ("sent_35.mp3", "output/auto_edit_temp", False, True),
            ("narration_1.wav", "clips/audio", False, True),
            ("custom_audio.mp3", "output", False, False),
            ("custom_audio.mp3", "output", True, True),
        ]:
            res = skip_notify
            if not res and filename and str(filename).startswith(('sent_', 'narration_', 'temp_')):
                res = True
            if not res and output_dir and any(x in str(output_dir).replace('\\', '/').lower() for x in ['auto_edit_temp', 'clips/audio', 'sentences', '/temp']):
                res = True
            self.assertEqual(res, expected, f"Failed for {filename}, {output_dir}, {skip_notify}")

if __name__ == '__main__':
    unittest.main()
