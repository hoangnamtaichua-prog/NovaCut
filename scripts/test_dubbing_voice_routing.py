"""Exercise export voice validation without network or installed voice models."""
import ast
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class ExportVoiceRoutingTests(unittest.TestCase):
    def first_event(self, voice, provider=None, key=None):
        source = ast.parse((ROOT / 'ai_dubbing.py').read_text(encoding='utf-8'))
        functions = [node for node in source.body if isinstance(node, ast.FunctionDef)
                     and node.name in {'parse_time_str', 'build_dubbing_track_for_subtitles_generator'}]
        profile = types.SimpleNamespace(get_voice_by_id=lambda _: {'provider': provider})
        with tempfile.TemporaryDirectory() as directory:
            namespace = {'os': os, 'ROOT_DIR': directory,
                         'ffmpeg_installer': types.SimpleNamespace(ensure_ffmpeg=lambda: 'ffmpeg')}
            exec(compile(ast.Module(body=functions, type_ignores=[]), 'ai_dubbing.py', 'exec'), namespace)
            with patch.dict(sys.modules, {'custom_voices': profile}):
                generator = namespace['build_dubbing_track_for_subtitles_generator'](
                    [{'text': 'Xin chao', 'startSeconds': 0, 'endSeconds': 1}],
                    voice, 1.0, directory, open_speaker_key=key)
                try:
                    return next(generator)
                finally:
                    generator.close()

    def test_offline_and_custom_voices_do_not_require_key(self):
        for voice, provider in [('local_ngoc_huyen', None), ('clone_123', 'local_voice'),
                                ('custom_123', 'rvc'), ('rvc_test', None),
                                ('manh_dung', None), ('thanh_dat', None),
                                ('ngoc_huyen', None), ('edge_vi-VN-HoaiMyNeural', None)]:
            with self.subTest(voice=voice):
                self.assertIn('Khởi động', self.first_event(voice, provider)[1])

    def test_online_voice_requires_key(self):
        self.assertIn('LỖI API KEY', self.first_event('online_voice')[1])

    def test_online_voice_accepts_key(self):
        self.assertIn('Khởi động', self.first_event('online_voice', key='test-key')[1])


if __name__ == '__main__':
    unittest.main()
