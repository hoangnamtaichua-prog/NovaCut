import unittest
from unittest.mock import patch, MagicMock
import auto_edit_pipeline

class TestStemSeparationProgressLogging(unittest.TestCase):
    @patch('audio_separator.separate_audio_stems')
    def test_run_audio_separator_with_progress_emits_logs(self, mock_separate):
        def fake_separate(input_media_path, output_dir, mode, device, progress_cb, logger_cb, cancel_check_cb):
            # Simulate MDX progress calls
            progress_cb(20, "Đang tách âm AI (20%): đoạn 1/10 [còn ~100s]")
            progress_cb(50, "Đang tách âm AI (50%): đoạn 5/10 [còn ~50s]")
            progress_cb(90, "Đang tách âm AI (90%): đoạn 9/10 [còn ~10s]")
            return {"cleaned_path": "fake_cleaned.wav"}

        mock_separate.side_effect = fake_separate

        logs = []
        def mock_log(msg):
            logs.append(msg)
            return f"data: {msg}\n\n"

        gen = auto_edit_pipeline.run_audio_separator_with_progress(
            video_path="test_video.mp4",
            output_dir="test_output",
            mode="mdx_net_hq4",
            device="auto",
            log_func=mock_log
        )

        res = None
        for item in gen:
            pass

        # Verify logs were captured in System Log format
        self.assertTrue(any("Đang tách âm AI (20%): đoạn 1/10" in l for l in logs))
        self.assertTrue(any("Đang tách âm AI (50%): đoạn 5/10" in l for l in logs))
        self.assertTrue(any("Đang tách âm AI (90%): đoạn 9/10" in l for l in logs))

if __name__ == '__main__':
    unittest.main()
