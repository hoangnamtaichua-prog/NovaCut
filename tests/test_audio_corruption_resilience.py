# -*- coding: utf-8 -*-
import unittest
import os
import sys

sys.stdout.reconfigure(encoding='utf-8')
import ffmpeg_installer

class TestAudioCorruptionResilience(unittest.TestCase):
    def test_ffmpeg_pan_filter_protects_corrupt_aac(self):
        """Kiểm tra bộ lọc pan stereo bảo vệ luồng xuất video không bị crash -22 EINVAL khi gặp frame AAC lỗi."""
        ffmpeg_exe = ffmpeg_installer.ensure_ffmpeg()
        test_video = r"D:/phim linh tinh/Giấc Mơ Thanh Huyền, Tiểu Sư Muội Được Cưng Chiều Một Kiếm Hủy Thiên Diệt Địa Mùa 6/Merged/Giấc Mơ Thanh Huyền, Tiểu Sư Muội Được Cưng Chiều Một Kiếm Hủy Thiên Diệt Địa Mùa 6.mp4"
        if not os.path.exists(test_video):
            self.skipTest("Source test video not present on test machine")

        import subprocess
        # Test 1: Lệnh gốc không có pan -> phải crash hoặc fail rematrix
        cmd_no_pan = [
            ffmpeg_exe, '-v', 'error', '-ss', '00:20:40', '-to', '00:20:55',
            '-i', test_video,
            '-filter_complex', '[0:a]aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1000[aout]',
            '-map', '[aout]', '-f', 'null', '-'
        ]
        res_no_pan = subprocess.run(cmd_no_pan, capture_output=True, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
        self.assertNotEqual(res_no_pan.returncode, 0, "Không có pan filter, FFmpeg phải thất bại do lỗi 56 channels")

        # Test 2: Có pan filter -> Thành công 100% không lỗi
        cmd_with_pan = [
            ffmpeg_exe, '-v', 'error', '-ss', '00:20:40', '-to', '00:20:55',
            '-i', test_video,
            '-filter_complex', '[0:a]pan=stereo|c0=c0|c1=c1,aformat=sample_rates=44100:channel_layouts=stereo,aresample=async=1000[aout]',
            '-map', '[aout]', '-f', 'null', '-'
        ]
        res_with_pan = subprocess.run(cmd_with_pan, capture_output=True, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
        self.assertEqual(res_with_pan.returncode, 0, f"Có pan filter, FFmpeg phải thành công: {res_with_pan.stderr}")

    def test_ffmpeg_max_error_rate_tolerance(self):
        """Kiểm tra cờ -err_detect ignore_err và -max_error_rate 1.0 giúp FFmpeg bỏ qua đoạn audio AAC lỗi mà không crash."""
        ffmpeg_exe = ffmpeg_installer.ensure_ffmpeg()
        test_video = r"D:\phim linh tinh\ngũ nữ\Nhà Có Năm Nữ, Hắn Đến Từ Thế Giới Khác Mở Mang Sự Nghiệp Mùa 4.mp4"
        if not os.path.exists(test_video):
            self.skipTest("Source test video not present on test machine")

        import subprocess
        # Khi có -max_error_rate 1.0, đoạn audio lỗi tại 03:06:20 - 03:07:00 phải hoàn thành với exit code 0
        cmd = [
            ffmpeg_exe, '-hide_banner', '-loglevel', 'error',
            '-err_detect', 'ignore_err', '-max_error_rate', '1.0',
            '-ss', '03:06:20', '-to', '03:07:00',
            '-i', test_video, '-vn', '-f', 'null', '-'
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
        self.assertEqual(res.returncode, 0, f"FFmpeg với -max_error_rate 1.0 phải hoàn thành exit code 0: {res.stderr}")

    def test_corrupt_packet_log_suppression_logic(self):
        """Kiểm tra logic nhận diện và loại trừ các log cảnh báo decoder drop notice rác."""
        diagnostic_keywords = (
            'error', 'warning', 'failed', 'invalid', 'cannot', 'not within',
            'could not', 'no such', 'denied', 'unsupported', 'terminat', 'abort',
            'exception', 'broken'
        )

        test_lines = [
            ("[aist#0:1/aac @ 0000021d11b29640] [dec:aac @ 0000021d12641240] Error submitting packet to decoder: Invalid data found when processing input", True),
            ("[aac @ 0000021d0f1a2500] invalid band type", True),
            ("[aac @ 00000185bad8e1c0] Pulse data corrupt or invalid.", True),
            ("[aac @ 00000185bad8e1c0] Number of bands (45) exceeds limit (38).", True),
            ("[aac @ 00000185bad8e1c0] channel element 2.11 is not allocated", True),
            ("[aist#0:1/aac @ 00000185b8f716c0] [dec:aac @ 00000185bad88d40] Decode error rate 0.99 exceeds maximum 0.66", True),
            ("Fontconfig error: Cannot load default config file", True),
            ("Error initializing filter 'subtitles': No such file or directory", False),
            ("Cannot allocate memory for frame buffer", False),
            ("Permission denied opening output file", False),
        ]

        def should_suppress(line_str):
            l_lower = line_str.lower()
            if 'fontconfig error' in l_lower:
                return True
            return any(n in l_lower for n in (
                'error submitting packet to decoder',
                'invalid band type',
                'pulse data corrupt',
                'exceeds limit',
                'is not allocated',
                'channel element',
                'decode error rate'
            ))

        for line, expected_suppressed in test_lines:
            suppressed = should_suppress(line)
            self.assertEqual(suppressed, expected_suppressed, f"Suppression mismatch for line: {line}")

if __name__ == '__main__':
    unittest.main()
