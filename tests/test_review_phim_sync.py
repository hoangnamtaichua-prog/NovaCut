import unittest
import os
import shutil
import tempfile
import subprocess
import json
import timeline_sanitizer
import auto_edit_pipeline
import ffmpeg_installer

class TestReviewPhimTimelineResolver(unittest.TestCase):
    def setUp(self):
        self.voice_entries = [
            (0.0, 3.5, "Câu thứ nhất của phần mở đầu review phim."),
            (3.5, 7.0, "Câu thứ hai kể về hoàn cảnh ngặt nghèo của nhân vật chính."),
            (7.0, 8.0, "Câu ngắn."),  # Clip ngắn 1.0s < min_clip_duration 1.2s -> Sẽ được gộp
            (8.0, 12.0, "Câu thứ tư kết thúc phân đoạn mở màn và bước vào cao trào.")
        ]
        self.mock_llm_timeline = [
            {"voice_ref": 1, "start": 10.0, "end": 13.5},
            {"voice_ref": 2, "start": 20.0, "end": 24.2},
            {"voice_ref": 3, "start": 30.0, "end": 31.0},
            {"voice_ref": 4, "start": 35.0, "end": 39.0}
        ]
        self.mock_scene_cuts = [10.2, 13.8, 20.1, 24.0, 30.05, 35.0, 39.2]

    def test_resolver_schema_and_sync(self):
        """Kiểm tra Resolver sinh đầy đủ các trường schema và video_duration khớp 100% voice_duration."""
        resolved, logs = timeline_sanitizer.resolve_timeline_with_voice_clock(
            timeline=self.mock_llm_timeline,
            voice_entries=self.voice_entries,
            scene_cuts=self.mock_scene_cuts,
            snap_threshold=0.6,
            min_clip_duration=1.2,
            min_speed=0.85,
            max_speed=1.20
        )

        self.assertGreater(len(resolved), 0)
        for clip in resolved:
            # Kiểm tra 10 trường schema cốt lõi
            self.assertIn("source_start", clip)
            self.assertIn("source_end", clip)
            self.assertIn("source_duration", clip)
            self.assertIn("voice_start", clip)
            self.assertIn("voice_end", clip)
            self.assertIn("voice_duration", clip)
            self.assertIn("video_duration", clip)
            self.assertIn("video_speed", clip)
            self.assertIn("audio_tempo", clip)
            self.assertIn("voice_ref", clip)
            self.assertIn("voice_refs", clip)
            self.assertIn("subsegments", clip)
            self.assertIn("sync_error_ms", clip)

            # Kiểm tra đồng bộ tuyệt đối giữa video_duration và voice_duration
            self.assertAlmostEqual(clip["video_duration"], clip["voice_duration"], places=2)
            self.assertLessEqual(clip["sync_error_ms"], 10.0)

    def test_short_clip_merge_preserves_voice_mapping(self):
        """Kiểm tra khi gộp clip ngắn (< 1.2s), mapping voice_refs và subsegments được bảo toàn đầy đủ."""
        resolved, logs = timeline_sanitizer.resolve_timeline_with_voice_clock(
            timeline=self.mock_llm_timeline,
            voice_entries=self.voice_entries,
            scene_cuts=self.mock_scene_cuts,
            min_clip_duration=1.2
        )

        # Clip #3 có voice_duration 1.0s < 1.2s nên phải được gộp vào clip #4
        # Tổng số clips sau gộp phải là 3
        self.assertEqual(len(resolved), 3)

        # Tìm clip được gộp (chứa nhiều hơn 1 voice_ref)
        merged_clip = None
        for c in resolved:
            if len(c.get("voice_refs", [])) > 1:
                merged_clip = c
                break

        self.assertIsNotNone(merged_clip, "Phải có ít nhất 1 clip được gộp bảo toàn voice_refs.")
        self.assertIn(3, merged_clip["voice_refs"])
        self.assertIn(4, merged_clip["voice_refs"])
        self.assertEqual(len(merged_clip["subsegments"]), 2)
        # Tổng thời lượng phải bằng 1.0s + 4.0s = 5.0s
        self.assertAlmostEqual(merged_clip["voice_duration"], 5.0, places=2)
        self.assertAlmostEqual(merged_clip["video_duration"], 5.0, places=2)

    def test_speed_ratio_clamping(self):
        """Kiểm tra khi LLM đề xuất mốc quá chênh lệch (speed > max_speed), Resolver sẽ tự động clamp tốc độ."""
        extreme_timeline = [
            # voice 3.5s nhưng LLM cắt đoạn phim 10s (cần speed 2.85x > 1.20x)
            {"voice_ref": 1, "start": 0.0, "end": 10.0}
        ]
        resolved, logs = timeline_sanitizer.resolve_timeline_with_voice_clock(
            timeline=extreme_timeline,
            voice_entries=[(0.0, 3.5, "Test extreme speed")],
            scene_cuts=[],
            min_speed=0.85,
            max_speed=1.20
        )
        self.assertEqual(len(resolved), 1)
        clip = resolved[0]
        # Tốc độ phải được clamp về an toàn (1.0x) và source_end được điều chỉnh
        self.assertLessEqual(clip["video_speed"], 1.20)
        self.assertGreaterEqual(clip["video_speed"], 0.85)
        self.assertAlmostEqual(clip["video_duration"], 3.5, places=2)

    def test_pre_render_validator(self):
        """Kiểm tra Pre-Render Validator đánh giá chính xác P95, Max error, tổng thời lượng."""
        resolved, _ = timeline_sanitizer.resolve_timeline_with_voice_clock(
            timeline=self.mock_llm_timeline,
            voice_entries=self.voice_entries,
            scene_cuts=self.mock_scene_cuts
        )
        is_valid, report = timeline_sanitizer.validate_timeline(resolved)
        self.assertTrue(is_valid)
        self.assertLessEqual(report["p95_sync_error_ms"], 80.0)
        self.assertLessEqual(report["max_sync_error_ms"], 150.0)
        self.assertAlmostEqual(report["total_voice_duration"], report["total_video_duration"], places=2)


class TestFFmpegRenderAndPTSValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()
        cls.temp_dir = tempfile.mkdtemp(prefix="novacut_test_review_")
        
        # 1. Tạo video giả lập 10s 30fps bằng lavfi testsrc
        cls.test_video = os.path.join(cls.temp_dir, "test_source.mp4")
        cmd_vid = [
            cls.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'testsrc=duration=10:size=640x360:rate=30',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-g', '30',
            cls.test_video
        ]
        subprocess.run(cmd_vid, check=True)

        # 2. Tạo audio giả lập 4s sine wave
        cls.test_audio = os.path.join(cls.temp_dir, "test_voice.wav")
        cmd_aud = [
            cls.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'lavfi', '-i', 'sine=frequency=1000:duration=4',
            '-ar', '24000', '-ac', '1', '-c:a', 'pcm_s16le',
            cls.test_audio
        ]
        subprocess.run(cmd_aud, check=True)

    @classmethod
    def tearDownClass(cls):
        try:
            shutil.rmtree(cls.temp_dir)
        except Exception:
            pass

    def test_ffmpeg_setpts_speed_and_pts_continuity(self):
        """Kiểm tra FFmpeg áp dụng setpts=PTS/speed, stream normalization (FPS 30, timescale 90000) và PTS không drop."""
        clip_out = os.path.join(self.temp_dir, "rendered_clip.mp4")
        source_start = 1.0
        source_end = 5.0
        source_dur = 4.0
        target_dur = 3.2  # Tốc độ speed = 4.0 / 3.2 = 1.25x
        speed_ratio = source_dur / target_dur

        cmd = [
            self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-ss', f"{source_start:.3f}", '-t', f"{source_dur:.3f}",
            '-i', self.test_video,
            '-filter_complex', f"[0:v]setpts=PTS/{speed_ratio:.6f},fps=30,settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v]",
            '-map', '[v]',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-r', '30', '-video_track_timescale', '90000', '-g', '60', '-keyint_min', '60',
            '-t', f"{target_dur:.3f}",
            '-an',
            clip_out
        ]
        subprocess.run(cmd, check=True)

        self.assertTrue(os.path.exists(clip_out))

        # Kiểm tra bằng post-render validator
        is_valid, report = auto_edit_pipeline.validate_rendered_video(
            video_path=clip_out,
            expected_duration=target_dur,
            ffmpeg_path=self.ffmpeg_path
        )
        self.assertTrue(is_valid)
        self.assertFalse(report["pts_drop_detected"], "PTS không được có hiện tượng giảm/nhảy vọt.")
        self.assertLessEqual(report["drift_ms"], 60.0, "Độ lệch so với target duration phải < 60ms.")

    def test_multi_clip_concat_pts_continuity(self):
        """Kiểm tra nối nhiều clip chuẩn hóa bằng Concat Demuxer (-c copy) không bị lỗi PTS drop."""
        clip1_out = os.path.join(self.temp_dir, "multi_clip_0.mp4")
        clip2_out = os.path.join(self.temp_dir, "multi_clip_1.mp4")
        
        # Clip 1: 0s -> 2.5s, target 2.0s (speed = 1.25x)
        cmd1 = [
            self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-ss', '0.000', '-t', '2.500', '-i', self.test_video,
            '-filter_complex', "[0:v]setpts=PTS/1.25,fps=30,settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v]",
            '-map', '[v]', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-r', '30', '-video_track_timescale', '90000', '-g', '60', '-keyint_min', '60',
            '-t', '2.000', '-an', clip1_out
        ]
        subprocess.run(cmd1, check=True)

        # Clip 2: 3.0s -> 5.0s, target 2.0s (speed = 1.0x)
        cmd2 = [
            self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-ss', '3.000', '-t', '2.000', '-i', self.test_video,
            '-filter_complex', "[0:v]setpts=PTS/1.0,fps=30,settb=AVTB,setpts=PTS-STARTPTS,format=yuv420p[v]",
            '-map', '[v]', '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '22', '-pix_fmt', 'yuv420p',
            '-r', '30', '-video_track_timescale', '90000', '-g', '60', '-keyint_min', '60',
            '-t', '2.000', '-an', clip2_out
        ]
        subprocess.run(cmd2, check=True)

        # Nối bằng concat demuxer
        concat_txt = os.path.join(self.temp_dir, "concat_test.txt")
        with open(concat_txt, 'w', encoding='utf-8') as f:
            f.write(f"file '{os.path.basename(clip1_out)}'\n")
            f.write(f"file '{os.path.basename(clip2_out)}'\n")

        concat_out = os.path.join(self.temp_dir, "concat_joined.mp4")
        cmd_concat = [
            self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-f', 'concat', '-safe', '0', '-i', concat_txt,
            '-c', 'copy',
            concat_out
        ]
        subprocess.run(cmd_concat, check=True, cwd=self.temp_dir)

        # Mix với audio 4.0s
        final_test_out = os.path.join(self.temp_dir, "final_test_output.mp4")
        cmd_mix = [
            self.ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-i', concat_out, '-i', self.test_audio,
            '-map', '0:v', '-map', '1:a',
            '-c:v', 'copy', '-c:a', 'aac',
            final_test_out
        ]
        subprocess.run(cmd_mix, check=True)

        # Validate file cuối
        is_valid, rep = auto_edit_pipeline.validate_rendered_video(
            final_test_out,
            expected_duration=4.0,
            ffmpeg_path=self.ffmpeg_path
        )
        self.assertTrue(is_valid)
        self.assertFalse(rep["pts_drop_detected"], "Concat -c copy của các clip chuẩn hóa không được có PTS drop.")
        self.assertLessEqual(rep["drift_ms"], 80.0, "Tổng độ lệch video-voice phải <= 80ms.")

if __name__ == '__main__':
    unittest.main()
