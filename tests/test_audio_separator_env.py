# -*- coding: utf-8 -*-
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

import audio_separator


class TestAudioSeparatorEnv(unittest.TestCase):
    def test_functional_python_rejects_windowsapps(self):
        fake_winapps = r"C:\Users\JohnDoe\AppData\Local\Microsoft\WindowsApps\python.exe"
        self.assertFalse(audio_separator._is_functional_python(fake_winapps))

    def test_functional_python_rejects_novacut_exe(self):
        fake_novacut = r"C:\Program Files\NovaCut\NovaCut.exe"
        self.assertFalse(audio_separator._is_functional_python(fake_novacut))

    def test_functional_python_rejects_nonexistent_path(self):
        fake_path = r"C:\NonExistent\Folder\python.exe"
        self.assertFalse(audio_separator._is_functional_python(fake_path))

    def test_functional_python_accepts_current_executable(self):
        self.assertTrue(audio_separator._is_functional_python(sys.executable))

    def test_clean_child_env_strips_pyinstaller_vars(self):
        with patch.dict(os.environ, {
            "PYTHONHOME": "C:\\_internal",
            "PYTHONPATH": "C:\\_internal\\site-packages",
            "PYTHONEXECUTABLE": "C:\\NovaCut.exe",
            "_MEIPASS": "C:\\temp\\meipass",
            "_MEIPASS2": "C:\\temp\\meipass2"
        }):
            cleaned = audio_separator._clean_child_env()
            for v in ["PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE", "_MEIPASS", "_MEIPASS2"]:
                self.assertNotIn(v, cleaned)
            self.assertEqual(cleaned.get("PYTHONIOENCODING"), "utf-8")
            self.assertEqual(cleaned.get("PYTHONUNBUFFERED"), "1")

    def test_registry_python_discovery_returns_list(self):
        pythons = audio_separator._find_pythons_in_registry()
        self.assertIsInstance(pythons, list)
        for p in pythons:
            self.assertTrue(os.path.isfile(p))


if __name__ == "__main__":
    unittest.main()
