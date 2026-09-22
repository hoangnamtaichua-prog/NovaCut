import unittest
import os
import shutil
import tempfile
import time
from unittest.mock import patch

from export_history import ExportHistoryService
from web_app import app


class TestExportHistoryServiceUnit(unittest.TestCase):
    """Kiểm thử tầng Service độc lập của Lịch sử xuất video."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='novacut_test_export_history_')
        self.db_path = os.path.join(self.temp_dir, 'test_export_history.sqlite3')
        self.service = ExportHistoryService(db_path=self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_sqlite_init_and_wal_mode(self):
        """Kiểm tra khởi tạo DB SQLite, chế độ WAL, busy_timeout và user_version."""
        with self.service._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            self.assertEqual(journal_mode.lower(), 'wal')

            cursor.execute("PRAGMA user_version;")
            user_ver = cursor.fetchone()[0]
            self.assertEqual(user_ver, 1)

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='exports';")
            tbl = cursor.fetchone()
            self.assertIsNotNone(tbl)

    def test_record_export_and_retrieve(self):
        """Kiểm tra ghi nhận export mới và tra cứu theo ID."""
        fake_video = os.path.join(self.temp_dir, 'video_test_1.mp4')
        with open(fake_video, 'wb') as f:
            f.write(b'0' * 5000)

        record_id = self.service.record_export(
            output_path=fake_video,
            source_tool='editor',
            source_kind='editor',
            export_run_id='run_test_001',
            params={'encoder': 'h264_nvenc', 'preset': 'p2'}
        )
        self.assertIsNotNone(record_id)
        self.assertTrue(bool(record_id))

        item = self.service.get_export_by_id(record_id)
        self.assertIsNotNone(item)
        self.assertEqual(item['filename'], 'video_test_1.mp4')
        self.assertEqual(item['source_tool'], 'editor')
        self.assertEqual(item['origin'], 'export')
        self.assertIsNotNone(item['completed_at'])
        self.assertEqual(item['params_json'].get('encoder'), 'h264_nvenc')
        self.assertEqual(item['file_status'], 'available')

    def test_idempotency_duplicate_event_key(self):
        """Kiểm tra tính bất biến / chống ghi trùng lặp (Idempotency) qua event_key."""
        fake_video = os.path.join(self.temp_dir, 'video_idempotent.mp4')
        with open(fake_video, 'wb') as f:
            f.write(b'1234567890')

        # Lần 1: Ghi thành công
        id1 = self.service.record_export(
            output_path=fake_video,
            source_tool='editor',
            export_run_id='run_duplicate_check',
            event_key='unique_key_abc_123'
        )

        # Lần 2: Ghi cùng event_key -> Phải trả về ID cũ, không tạo record mới
        id2 = self.service.record_export(
            output_path=fake_video,
            source_tool='editor',
            export_run_id='run_duplicate_check',
            event_key='unique_key_abc_123'
        )
        self.assertEqual(id1, id2)

        res = self.service.query_exports(search='video_idempotent.mp4')
        self.assertEqual(res['total'], 1)

    def test_path_normalization_and_unicode(self):
        """Kiểm tra hỗ trợ đường dẫn Unicode tiếng Việt và chuẩn hóa đường dẫn."""
        unicode_name = 'Phim Tóm Tắt 皇帝居然偷听我心声 - Tập 01.mp4'
        unicode_path = os.path.join(self.temp_dir, unicode_name)
        with open(unicode_path, 'wb') as f:
            f.write(b'unicode_video_content')

        record_id = self.service.record_export(
            output_path=unicode_path,
            source_tool='review',
            export_run_id='run_unicode_01'
        )
        item = self.service.get_export_by_id(record_id)
        self.assertEqual(item['filename'], unicode_name)

        # Tìm kiếm theo từ khóa tiếng Việt có dấu
        res = self.service.query_exports(search='Tóm Tắt')
        self.assertEqual(res['total'], 1)
        self.assertEqual(res['items'][0]['id'], record_id)

    def test_query_pagination_and_search(self):
        """Kiểm tra phân trang và tìm kiếm."""
        for i in range(15):
            p = os.path.join(self.temp_dir, f"video_batch_{i:02d}.mp4")
            with open(p, 'wb') as f:
                f.write(b'video')
            self.service.record_export(output_path=p, source_tool='editor', export_run_id=f"run_page_{i}")

        # Trang 1: 10 items
        res1 = self.service.query_exports(page=1, limit=10)
        self.assertEqual(res1['total'], 15)
        self.assertEqual(len(res1['items']), 10)
        self.assertEqual(res1['total_pages'], 2)

        # Trang 2: 5 items còn lại
        res2 = self.service.query_exports(page=2, limit=10)
        self.assertEqual(len(res2['items']), 5)

        # Tìm kiếm chính xác
        res_search = self.service.query_exports(search='video_batch_07')
        self.assertEqual(res_search['total'], 1)
        self.assertEqual(res_search['items'][0]['filename'], 'video_batch_07.mp4')

    def test_query_filter_by_tool_and_status(self):
        """Kiểm tra bộ lọc theo công cụ và trạng thái file."""
        f_avail = os.path.join(self.temp_dir, 'video_avail.mp4')
        with open(f_avail, 'wb') as f:
            f.write(b'available')

        f_missing = os.path.join(self.temp_dir, 'video_missing.mp4')
        with open(f_missing, 'wb') as f:
            f.write(b'will_delete')

        id_avail = self.service.record_export(output_path=f_avail, source_tool='editor', export_run_id='run_tool_1')
        id_missing = self.service.record_export(output_path=f_missing, source_tool='review', export_run_id='run_tool_2')

        # Xóa file thật trên đĩa để chuyển trạng thái sang missing
        os.remove(f_missing)

        # Lọc theo tool 'editor'
        res_editor = self.service.query_exports(source_tool='editor')
        self.assertEqual(res_editor['total'], 1)
        self.assertEqual(res_editor['items'][0]['id'], id_avail)

        # Lọc theo tool 'review'
        res_review = self.service.query_exports(source_tool='review')
        self.assertEqual(res_review['total'], 1)
        self.assertEqual(res_review['items'][0]['id'], id_missing)

        # Lọc theo trạng thái 'available'
        res_status_avail = self.service.query_exports(status='available')
        self.assertEqual(res_status_avail['total'], 1)
        self.assertEqual(res_status_avail['items'][0]['id'], id_avail)

        # Lọc theo trạng thái 'missing'
        res_status_missing = self.service.query_exports(status='missing')
        self.assertEqual(res_status_missing['total'], 1)
        self.assertEqual(res_status_missing['items'][0]['id'], id_missing)

    def test_delete_export_keeps_file_on_disk(self):
        """Kiểm tra xóa bản ghi trong DB nhưng file thật trên ổ đĩa KHÔNG bị xóa."""
        fake_video = os.path.join(self.temp_dir, 'video_safe_delete.mp4')
        with open(fake_video, 'wb') as f:
            f.write(b'important_user_video')

        record_id = self.service.record_export(output_path=fake_video, source_tool='editor', export_run_id='run_del_1')
        self.assertTrue(os.path.exists(fake_video))

        success = self.service.delete_export(record_id)
        self.assertTrue(success)

        # Kiểm tra DB đã bị xóa
        self.assertIsNone(self.service.get_export_by_id(record_id))

        # KIỂM TRA QUAN TRỌNG: File thật trên đĩa vẫn còn nguyên 100%
        self.assertTrue(os.path.exists(fake_video))
        self.assertEqual(os.path.getsize(fake_video), len(b'important_user_video'))

    def test_import_scan_and_commit_workflow(self):
        """Kiểm tra quy trình Scan -> Preview -> Commit của tính năng Nhập video cũ."""
        scan_folder = os.path.join(self.temp_dir, 'my_old_videos')
        sub_folder = os.path.join(scan_folder, 'season_1')
        os.makedirs(sub_folder, exist_ok=True)

        v1 = os.path.join(scan_folder, 'old_clip_1.mp4')
        v2 = os.path.join(sub_folder, 'old_clip_2.mkv')
        txt = os.path.join(scan_folder, 'not_a_video.txt')

        with open(v1, 'wb') as f: f.write(b'video1')
        with open(v2, 'wb') as f: f.write(b'video2')
        with open(txt, 'wb') as f: f.write(b'text file')

        # Bắt đầu scan đệ quy
        scan_id = self.service.start_import_scan(scan_folder, include_subfolders=True)
        self.assertIsNotNone(scan_id)

        # Chờ scan hoàn thành
        for _ in range(50):
            prog = self.service.get_import_scan_progress(scan_id)
            if prog and prog['status'] in ('completed', 'failed'):
                break
            time.sleep(0.05)

        self.assertEqual(prog['status'], 'completed')
        self.assertEqual(prog['found_count'], 2)  # v1 và v2, bỏ qua txt

        candidates = prog['candidates']
        self.assertEqual(len(candidates), 2)
        for c in candidates:
            self.assertFalse(c['already_exists'])

        # Commit candidates vào DB
        res = self.service.commit_import_candidates(scan_id, candidates)
        self.assertEqual(res['imported_count'], 2)
        self.assertEqual(res['skipped_count'], 0)

        # Kiểm tra DB sau khi commit
        exports = self.service.query_exports()
        self.assertEqual(exports['total'], 2)
        for item in exports['items']:
            self.assertEqual(item['origin'], 'import')
            self.assertEqual(item['source_tool'], 'import')
            # QUY TẮC BẮT BUỘC: Không bịa ngày xuất cho video import!
            self.assertIsNone(item['completed_at'])
            self.assertIsNotNone(item['imported_at'])


class TestExportHistoryApiIntegration(unittest.TestCase):
    """Kiểm thử tầng API tích hợp với Flask test_client."""

    def setUp(self):
        self.client = app.test_client()
        self.temp_dir = tempfile.mkdtemp(prefix='novacut_test_api_')

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_export_history_api(self):
        """Kiểm tra API GET /api/export-history."""
        res = self.client.get('/api/export-history')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertIn('items', data)
        self.assertIn('total', data)

    def test_unsupported_file_extension_rejected(self):
        """Kiểm tra mở file không phải video bị từ chối an toàn."""
        fake_bat = os.path.join(self.temp_dir, 'malicious.bat')
        with open(fake_bat, 'wb') as f:
            f.write(b'@echo off')

        from export_history import get_export_history_service
        svc = get_export_history_service()
        rec_id = svc.record_export(output_path=fake_bat, source_tool='editor', export_run_id='test_bat')

        res = self.client.post(f'/api/export-history/{rec_id}/open')
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertFalse(data['success'])
        self.assertEqual(data['error'], 'INVALID_FILE_TYPE')

    def test_open_and_reveal_not_found(self):
        """Kiểm tra mở ID không tồn tại trả về 404 rõ ràng."""
        res_open = self.client.post('/api/export-history/non_existent_uuid_12345/open')
        self.assertEqual(res_open.status_code, 404)

        res_reveal = self.client.post('/api/export-history/non_existent_uuid_12345/reveal')
        self.assertEqual(res_reveal.status_code, 404)

    def test_delete_api(self):
        """Kiểm tra API DELETE /api/export-history/<id>."""
        fake_video = os.path.join(self.temp_dir, 'test_api_delete.mp4')
        with open(fake_video, 'wb') as f:
            f.write(b'video content')

        from export_history import get_export_history_service
        svc = get_export_history_service()
        rec_id = svc.record_export(output_path=fake_video, source_tool='editor', export_run_id='run_api_del')

        # Xóa qua API
        res = self.client.delete(f'/api/export-history/{rec_id}')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])

        # File thật vẫn còn
        self.assertTrue(os.path.exists(fake_video))

    def test_concurrent_recording(self):
        """Kiểm thử ghi đồng thời từ nhiều luồng (Concurrency & Thread Safety)."""
        import concurrent.futures
        from export_history import get_export_history_service
        svc = get_export_history_service()

        videos = []
        for i in range(10):
            p = os.path.join(self.temp_dir, f"concurrent_{i}.mp4")
            with open(p, 'wb') as f:
                f.write(b'concurrent')
            videos.append(p)

        def record_task(path):
            return svc.record_export(output_path=path, source_tool='batch_queue', export_run_id='run_concurrent')

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(record_task, videos))

        self.assertEqual(len(results), 10)
        for r in results:
            self.assertIsNotNone(r)

    def test_offline_drive_status(self):
        """Kiểm tra trạng thái unreachable khi ổ đĩa không tồn tại."""
        from export_history import get_export_history_service
        svc = get_export_history_service()
        # Ổ đĩa Z thường không có trên Windows máy test
        status = svc.check_file_status('Z:\\non_existent_volume_9999\\video.mp4')
        self.assertEqual(status, 'unreachable')


if __name__ == '__main__':
    unittest.main()

