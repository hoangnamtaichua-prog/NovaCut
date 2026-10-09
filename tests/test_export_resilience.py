# -*- coding: utf-8 -*-
"""
Kiểm thử chuyên sâu tính bền bỉ của cơ chế xuất video (Export Resilience Test Suite):
1. Giải mã SSE dòng dở dang, cắt ngang byte UTF-8 và JSON event.
2. Tính độc lập của Job Worker khi kết nối HTTP ngắt.
3. Cơ chế khôi phục và bù sự kiện SSE qua ?after=<seq>.
4. Nhịp tim độc lập (Heartbeat emission) chống timeout.
5. Kiểm định mã băm (Fingerprint) và Manifest bảo toàn giọng đọc TTS.
6. An toàn tệp đầu ra qua cơ chế ghi nguyên tử .part.mp4.
7. Quản lý dọn dẹp tiến trình con khi hủy bỏ tác vụ.
8. Tương thích ngược các REST API endpoints của Flask.
"""

import os
import sys
import time
import json
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch, MagicMock

from export_job_manager import ExportJob, ExportJobManager, JobStage, JobState
from routes.video_edit import (
    compute_tts_fingerprint,
    is_tts_manifest_valid,
    save_tts_manifest
)
from web_app import app


class TestExportResilience(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='novacut_test_resilience_')
        self.client = app.test_client()

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sse_line_buffer_and_chunk_split(self):
        """
        Kiểm tra bộ phân tích SSE theo logic lineBuffer của frontend:
        Dữ liệu đến bị chia cắt ngẫu nhiên ở giữa ký tự UTF-8 đa byte tiếng Việt
        hoặc ở giữa chuỗi JSON [EVENT:SUCCESS].
        """
        raw_events = (
            "id: 1\n"
            "data: [EVENT:STAGE] {\"stage\": \"preparing\", \"progress\": 10}\n\n"
            "id: 2\n"
            "data: 🎙️ Đang tạo lồng tiếng: Xin chào Việt Nam hào khí Đông A\n\n"
            "id: 3\n"
            "data: [EVENT:SUCCESS] {\"path\": \"C:\\\\output\\\\test.mp4\", \"size_mb\": 45.2}\n\n"
        )
        raw_bytes = raw_events.encode('utf-8')

        # Mô phỏng nhận dữ liệu qua các chunk kích thước nhỏ (7 bytes mỗi chunk)
        # gây cắt ngang ký tự tiếng Việt 3 byte và dòng phân cách
        chunk_size = 7
        chunks = [raw_bytes[i:i + chunk_size] for i in range(0, len(raw_bytes), chunk_size)]

        import codecs
        decoder = codecs.getincrementaldecoder('utf-8')()
        line_buffer = ""
        received_lines = []
        events_parsed = []

        for ch in chunks:
            line_buffer += decoder.decode(ch)
            parts = line_buffer.split('\n')
            line_buffer = parts.pop()
            for pl in parts:
                received_lines.append(pl)
                pl_clean = pl.strip()
                if pl_clean.startswith('data: [EVENT:SUCCESS]'):
                    json_str = pl_clean.replace('data: [EVENT:SUCCESS]', '').strip()
                    events_parsed.append(json.loads(json_str))

        if line_buffer.strip():
            received_lines.append(line_buffer)

        self.assertEqual(len(events_parsed), 1)
        self.assertEqual(events_parsed[0]['size_mb'], 45.2)
        # Kiểm tra nội dung tiếng Việt có dấu được bảo toàn 100% không bị vỡ font
        joined_text = "\n".join(received_lines)
        self.assertIn("Xin chào Việt Nam hào khí Đông A", joined_text)

    def test_job_worker_independence_from_http_disconnect(self):
        """
        Kiểm tra Job Worker chạy hoàn toàn độc lập với subscriber SSE.
        Khi subscriber ngắt kết nối (mô phỏng GeneratorExit / đóng tab),
        Worker vẫn tiếp tục chạy trong nền đến khi hoàn thành.
        """
        job = ExportJob(params={'test': True})

        worker_completed = threading.Event()

        def mock_background_worker(j):
            j.set_running()
            j.set_stage(JobStage.PREPARING, 10, "Bắt đầu...")
            time.sleep(0.05)
            j.emit_log("Đang xử lý bước 1")
            time.sleep(0.05)
            j.set_stage(JobStage.ENCODING, 50, "Đang biên mã...")
            time.sleep(0.05)
            j.set_success("C:\\test\\out.mp4", 12.5, history_id=101)
            worker_completed.set()

        t = threading.Thread(target=mock_background_worker, args=(job,), daemon=True)
        t.start()

        # Subscriber chỉ đọc 1 event đầu tiên rồi thoát đột ngột (mô phỏng client disconnect)
        gen = job.stream_events(start_seq=0)
        first_item = next(gen)
        self.assertIn("job_id:", first_item)
        del gen  # Đóng generator phía client

        # Xác nhận worker nền vẫn tiếp tục chạy và hoàn tất thành công
        finished = worker_completed.wait(timeout=2.0)
        self.assertTrue(finished, "Worker nền phải tiếp tục chạy sau khi subscriber ngắt")
        self.assertEqual(job.state, JobState.SUCCEEDED)
        self.assertEqual(job.output_path, "C:\\test\\out.mp4")

    def test_sse_reconnection_with_after_seq(self):
        """
        Kiểm tra cơ chế tái kết nối và bù sự kiện (Event Replay Buffer):
        Client đã nhận event seq=1..2, sau đó mất kết nối.
        Khi kết nối lại với ?after=2, server chỉ phát các sự kiện từ seq=3 trở đi.
        """
        job = ExportJob(params={})
        job.set_running()
        job.emit_log("Sự kiện 1")  # seq = 1
        job.emit_log("Sự kiện 2")  # seq = 2
        job.emit_log("Sự kiện 3")  # seq = 3
        job.emit_log("Sự kiện 4")  # seq = 4
        job.set_success("C:\\done.mp4", 10.0)  # seq = 5

        # Reconnect với start_seq = 2
        replayed_events = list(job.stream_events(start_seq=2, heartbeat_interval=1.0))
        replayed_text = "".join(replayed_events)

        self.assertNotIn("id: 1\n", replayed_text)
        self.assertNotIn("id: 2\n", replayed_text)
        self.assertIn("id: 3\n", replayed_text)
        self.assertIn("Sự kiện 3", replayed_text)
        self.assertIn("id: 4\n", replayed_text)
        self.assertIn("Sự kiện 4", replayed_text)
        self.assertIn("id: 5\n", replayed_text)
        self.assertIn("[EVENT:SUCCESS]", replayed_text)

    def test_heartbeat_emission_on_idle(self):
        """
        Kiểm tra việc phát heartbeat định kỳ độc lập khi tác vụ đang xử lý nặng
        mà không có log mới.
        """
        job = ExportJob(params={})
        job.set_running()
        job.set_stage(JobStage.STEM_SEPARATING, 35.0, "Tách giọng bằng AI...")

        # Đặt heartbeat_interval cực ngắn (0.1 giây) để kiểm thử nhanh
        gen = job.stream_events(start_seq=0, heartbeat_interval=0.1)
        header = next(gen)  # ": job_id: ..."
        stage_event = next(gen)  # "id: 1\ndata: [EVENT:STAGE] ..."
        self.assertIn("[EVENT:STAGE]", stage_event)

        # Sau đó không có event mới nào được push vào job, vòng lặp phải yield heartbeat
        hb_comment = next(gen)
        self.assertEqual(hb_comment, ": heartbeat\n\n")
        hb_data = next(gen)
        self.assertIn("[HEARTBEAT]", hb_data)
        self.assertIn("stem_separating", hb_data)

        job.set_success("C:\\done.mp4", 1.0)

    def test_tts_manifest_fingerprint_matching_and_rejection(self):
        """
        Kiểm tra hàm băm fingerprint và manifest lồng tiếng:
        - Giữ nguyên nội dung, giọng đọc, tốc độ -> Trùng khớp 100%, tái sử dụng.
        - Thay đổi nội dung câu phụ đề -> Sai lệch fingerprint, từ chối cache.
        - Thay đổi tốc độ hoặc giọng đọc -> Sai lệch fingerprint, từ chối cache.
        """
        subs_orig = [
            {"text": "Xin chào các bạn", "startSeconds": 0.0, "endSeconds": 2.5},
            {"text": "Chào mừng đến với tập phim hôm nay", "startSeconds": 2.8, "endSeconds": 5.2}
        ]
        voice_id = "voice_thai_son"
        speed = 1.15
        duration = 120.0

        # Tạo file audio giả lập dubbed_timeline.wav hợp lệ > 1000 bytes
        import wave
        wav_path = os.path.join(self.temp_dir, 'dubbed_timeline.wav')
        with wave.open(wav_path, 'wb') as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"\x00" * 32000)

        fp1 = compute_tts_fingerprint(subs_orig, voice_id, speed, duration)
        self.assertTrue(bool(fp1) and len(fp1) == 64, "Mã băm phải là chuỗi SHA-256 64 hex")

        # Lưu manifest vào thư mục tạm
        save_tts_manifest(self.temp_dir, fp1, voice_id, speed, duration, len(subs_orig))

        # Kiểm tra xác thực cùng thông số -> Phải HỢP LỆ
        self.assertTrue(is_tts_manifest_valid(self.temp_dir, fp1))

        # Thay đổi lời thoại câu 2 -> Phải BỊ TỪ CHỐI
        subs_modified = [
            {"text": "Xin chào các bạn", "startSeconds": 0.0, "endSeconds": 2.5},
            {"text": "Đây là kịch bản hoàn toàn mới", "startSeconds": 2.8, "endSeconds": 5.2}
        ]
        fp_modified = compute_tts_fingerprint(subs_modified, voice_id, speed, duration)
        self.assertNotEqual(fp1, fp_modified)
        self.assertFalse(is_tts_manifest_valid(self.temp_dir, fp_modified))

        # Thay đổi giọng đọc -> Phải BỊ TỪ CHỐI
        fp_diff_voice = compute_tts_fingerprint(subs_orig, "voice_ngoc_huyen", speed, duration)
        self.assertNotEqual(fp1, fp_diff_voice)
        self.assertFalse(is_tts_manifest_valid(self.temp_dir, fp_diff_voice))

        # Thay đổi tốc độ -> Phải BỊ TỪ CHỐI
        fp_diff_speed = compute_tts_fingerprint(subs_orig, voice_id, 1.25, duration)
        self.assertNotEqual(fp1, fp_diff_speed)
        self.assertFalse(is_tts_manifest_valid(self.temp_dir, fp_diff_speed))

    def test_atomic_file_rename_safety(self):
        """
        Kiểm tra an toàn file đầu ra:
        - Xuất vào .part.mp4 và rename sang .mp4 khi thành công.
        - Giữ nguyên video cũ nếu lần xuất sau gặp lỗi và dọn file part dở dang.
        """
        final_video = os.path.join(self.temp_dir, "movie_final.mp4")
        with open(final_video, "w", encoding="utf-8") as f:
            f.write("OLD_VIDEO_CONTENT_ORIGINAL")

        part_video = final_video + f".part_{os.getpid()}_{int(time.time())}.mp4"
        with open(part_video, "w", encoding="utf-8") as f:
            f.write("NEW_EXPORTED_VIDEO_CONTENT")

        # Giả lập xuất THÀNH CÔNG: atomic replace
        if os.path.exists(final_video):
            os.replace(part_video, final_video)
        else:
            os.rename(part_video, final_video)

        self.assertFalse(os.path.exists(part_video))
        with open(final_video, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "NEW_EXPORTED_VIDEO_CONTENT")

        # Giả lập lần xuất sau bị THẤT BẠI: file part dở dang bị xóa, video hiện tại được giữ nguyên
        bad_part = final_video + f".part_failed.mp4"
        with open(bad_part, "w", encoding="utf-8") as f:
            f.write("CORRUPTED_PARTIAL_DATA")

        # Giả lập logic finally: dọn part khi not export_succeeded
        if os.path.exists(bad_part):
            os.remove(bad_part)

        self.assertFalse(os.path.exists(bad_part))
        self.assertTrue(os.path.exists(final_video))
        with open(final_video, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "NEW_EXPORTED_VIDEO_CONTENT")

    def test_job_cancellation_and_process_cleanup(self):
        """
        Kiểm tra hủy tác vụ và dọn dẹp tiến trình con không để lại orphan process.
        """
        job = ExportJob(params={})
        job.set_running()

        mock_proc = MagicMock()
        mock_proc.pid = 999999
        mock_proc.poll.return_value = None  # Đang chạy

        job.register_process(mock_proc)
        self.assertIn(mock_proc, job._child_processes)

        with patch('export_job_manager._terminate_pid', return_value=True) as mock_kill:
            stopped = job.request_cancel(reason="Người dùng yêu cầu hủy")
            self.assertTrue(stopped)
            self.assertTrue(job.is_stopped())
            self.assertEqual(job.state, JobState.CANCELLING)
            mock_kill.assert_called_once_with(999999)
            self.assertEqual(len(job._child_processes), 0)

    @patch('routes.video_edit.is_path_allowed', return_value=True)
    @patch('routes.video_edit._require_permission', return_value=None)
    def test_flask_export_jobs_api_endpoints(self, mock_perm, mock_path):
        """
        Kiểm tra các REST API endpoints mới:
        - POST /api/export/jobs
        - GET /api/export/jobs/<id>
        - POST /api/export/jobs/<id>/cancel
        - GET /api/export_status
        """
        dummy_video = os.path.join(self.temp_dir, "input.mp4")
        with open(dummy_video, "wb") as f:
            f.write(b"RIFFdummyvideodata")

        payload = {
            'inputVideo': dummy_video,
            'outputDir': self.temp_dir,
            'outputName': 'test_resilience_api.mp4',
            'resolution': 'original',
            'encoder': 'libx264'
        }

        mgr = ExportJobManager()
        with patch('routes.video_edit.get_export_job_manager', return_value=mgr):
            with patch('routes.video_edit.execute_export_pipeline') as mock_pipe:
                res = self.client.post('/api/export/jobs', json=payload)
                self.assertEqual(res.status_code, 202)
                res_data = res.get_json()
                self.assertTrue(res_data.get('success'))
                job_id = res_data.get('job_id')
                self.assertIsNotNone(job_id)

                res_get = self.client.get(f'/api/export/jobs/{job_id}')
                self.assertEqual(res_get.status_code, 200)
                get_data = res_get.get_json()
                self.assertTrue(get_data.get('success'))
                self.assertEqual(get_data.get('job', {}).get('job_id'), job_id)

                res_cancel = self.client.post(f'/api/export/jobs/{job_id}/cancel')
                self.assertEqual(res_cancel.status_code, 200)
                cancel_data = res_cancel.get_json()
                self.assertTrue(cancel_data.get('success'))

                res_status = self.client.get('/api/export_status')
                self.assertEqual(res_status.status_code, 200)
                status_data = res_status.get_json()
                self.assertIn('active', status_data)


if __name__ == '__main__':
    unittest.main()
