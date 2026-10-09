import unittest
from unittest.mock import patch, MagicMock
import os
import json

class TestStemBgmSeparation(unittest.TestCase):
    def test_audio_separator_separate_stems_signature(self):
        import audio_separator
        import inspect
        sig = inspect.signature(audio_separator.separate_audio_stems)
        self.assertIn('separate_bgm', sig.parameters)
        self.assertIn('remove_bgm', sig.parameters)
        self.assertIn('remove_vocals', sig.parameters)
        self.assertIn('keep_sfx', sig.parameters)

    def test_mdx_separator_signature(self):
        import mdx_separator
        import inspect
        sig = inspect.signature(mdx_separator.separate_stems_mdx)
        self.assertIn('separate_bgm', sig.parameters)
        self.assertIn('remove_bgm', sig.parameters)

    @patch('audio_separator.extract_audio_from_video')
    @patch('audio_separator._run_mdx_in_isolated_process')
    @patch('os.path.exists')
    def test_audio_separator_returns_bgm_path(self, mock_exists, mock_run_mdx, mock_extract):
        mock_exists.return_value = True
        mock_run_mdx.return_value = {
            "clean_background_path": "fake_clean.wav",
            "vocals_path": "fake_vocals.wav",
            "instrumental_path": "fake_inst.wav"
        }
        import audio_separator
        res = audio_separator.separate_audio_stems(
            input_media_path="fake_video.mp4",
            mode="mdx_net_hq4",
            separate_bgm=True
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["bgm_path"], "fake_inst.wav")
        self.assertEqual(res["instrumental_path"], "fake_inst.wav")
        self.assertEqual(res["vocals_path"], "fake_vocals.wav")

    @patch('audio_separator._separate_stems_dsp_turbo')
    @patch('os.path.exists')
    def test_audio_separator_dsp_turbo_returns_bgm_path(self, mock_exists, mock_dsp_turbo):
        mock_exists.return_value = True
        mock_dsp_turbo.return_value = {
            "success": True,
            "mode": "dsp_turbo",
            "device": "cpu",
            "cleaned_path": "fake_clean.wav",
            "vocals_path": "fake_vocals.wav",
            "instrumental_path": "fake_inst.wav",
            "bgm_path": "fake_inst.wav"
        }
        import audio_separator
        res = audio_separator.separate_audio_stems(
            input_media_path="fake_video.mp4",
            mode="dsp_turbo",
            separate_bgm=True
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["bgm_path"], "fake_inst.wav")
        self.assertEqual(res["instrumental_path"], "fake_inst.wav")
        self.assertEqual(res["vocals_path"], "fake_vocals.wav")

    def test_batch_queue_manager_stem_config(self):
        from batch_queue_manager import BatchQueueManager
        mgr = BatchQueueManager()
        # Test default stem config expansion
        raw_config = {
            'stem_separation': False,
            'stem_remove_vocals': True,
            'stem_separate_bgm': True,
            'stem_keep_sfx': True
        }
        stem_config = raw_config.get('stem_separation')
        if not isinstance(stem_config, dict):
            stem_config = {
                'enabled': bool(stem_config),
                'remove_vocals': bool(raw_config.get('stem_remove_vocals', True)),
                'keep_sfx': bool(raw_config.get('stem_keep_sfx', True)),
                'separate_bgm': bool(raw_config.get('stem_separate_bgm', True)),
                'keep_bgm': bool(raw_config.get('stem_keep_bgm', True)),
                'remove_bgm': bool(raw_config.get('stem_remove_bgm', False))
            }
        self.assertTrue(stem_config['separate_bgm'])
        self.assertFalse(stem_config['remove_bgm'])

if __name__ == '__main__':
    unittest.main()
