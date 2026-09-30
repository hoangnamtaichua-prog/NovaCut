import unittest
import os
import json
import threading
import time
from unittest.mock import patch, MagicMock

from web_app import app
import routes.download as download_module


class TestDownloadQueueEndpoints(unittest.TestCase):
    """Kiểm thử tính năng tải nhiều video hàng chờ (Download Queue) và quản lý luồng tải."""

    def setUp(self):
        self.app = app.test_client()
        self.app.testing = True
        # Reset active downloads state
        with download_module._download_lock:
            download_module._active_downloads.clear()
            download_module._download_active = False

    def tearDown(self):
        with download_module._download_lock:
            download_module._active_downloads.clear()
            download_module._download_active = False

    @patch('license_manager.check_permission')
    def test_active_tasks_endpoint(self, mock_perm):
        """Kiểm tra API /api/download/active_tasks trả về danh sách và số lượng tác vụ đang tải."""
        mock_perm.return_value = (True, "OK", {})

        # When no active tasks
        res = self.app.get('/api/download/active_tasks')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['active_count'], 0)
        self.assertEqual(data['tasks'], [])

        # Add a mock active task
        with download_module._download_lock:
            download_module._active_downloads['task_001'] = {
                'cancel_event': threading.Event(),
                'url': 'https://www.youtube.com/watch?v=sample123',
                'start_time': time.time()
            }

        res = self.app.get('/api/download/active_tasks')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['active_count'], 1)
        self.assertEqual(data['tasks'][0]['task_id'], 'task_001')
        self.assertEqual(data['tasks'][0]['url'], 'https://www.youtube.com/watch?v=sample123')

    @patch('license_manager.check_permission')
    def test_cancel_endpoint_single_task(self, mock_perm):
        """Kiểm tra API /api/download/cancel với task_id cụ thể."""
        mock_perm.return_value = (True, "OK", {})

        cancel_ev = threading.Event()
        with download_module._download_lock:
            download_module._active_downloads['task_test_cancel'] = {
                'cancel_event': cancel_ev,
                'url': 'https://www.youtube.com/watch?v=cancel_me',
                'start_time': time.time()
            }

        self.assertFalse(cancel_ev.is_set())

        # Call cancel API for this task
        res = self.app.post('/api/download/cancel', json={'task_id': 'task_test_cancel'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['task_id'], 'task_test_cancel')
        self.assertTrue(cancel_ev.is_set())

    @patch('license_manager.check_permission')
    def test_cancel_endpoint_all_tasks(self, mock_perm):
        """Kiểm tra API /api/download/cancel với all=True hủy toàn bộ hàng chờ."""
        mock_perm.return_value = (True, "OK", {})

        ev1 = threading.Event()
        ev2 = threading.Event()
        with download_module._download_lock:
            download_module._active_downloads['task_1'] = {'cancel_event': ev1, 'url': 'https://www.youtube.com/watch?v=1', 'start_time': time.time()}
            download_module._active_downloads['task_2'] = {'cancel_event': ev2, 'url': 'https://www.youtube.com/watch?v=2', 'start_time': time.time()}

        res = self.app.post('/api/download/cancel', json={'all': True})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['cancelled_count'], 2)
        self.assertTrue(ev1.is_set())
        self.assertTrue(ev2.is_set())

    @patch('license_manager.check_permission')
    def test_concurrency_limit_enforcement(self, mock_perm):
        """Kiểm tra máy chủ giới hạn tối đa MAX_CONCURRENT_DOWNLOADS (5) và trả về HTTP 429."""
        mock_perm.return_value = (True, "OK", {})

        # Fill up 5 active tasks
        with download_module._download_lock:
            for i in range(download_module.MAX_CONCURRENT_DOWNLOADS):
                download_module._active_downloads[f'task_filler_{i}'] = {
                    'cancel_event': threading.Event(),
                    'url': f'https://www.youtube.com/watch?v=vid_{i}',
                    'start_time': time.time()
                }

        # Try to start a 6th download
        res = self.app.post('/api/download/start', json={
            'url': 'https://www.youtube.com/watch?v=extra_video',
            'task_id': 'task_overflow'
        })
        self.assertEqual(res.status_code, 429)
        data = res.get_json()
        self.assertIn('Đã đạt giới hạn tối đa số tác vụ tải đồng thời', data['error'])

    @patch('license_manager.check_permission')
    def test_permission_denied(self, mock_perm):
        """Kiểm tra trả về 403 Forbidden nếu không có quyền can_access_editor."""
        mock_perm.return_value = (False, "Gói của bạn chưa hỗ trợ tính năng này", {})

        res = self.app.post('/api/download/start', json={'url': 'https://www.youtube.com/watch?v=test'})
        self.assertEqual(res.status_code, 403)
        data = res.get_json()
        self.assertIn('chưa hỗ trợ', data['error'])

    @patch('license_manager.check_permission')
    def test_invalid_url_rejected(self, mock_perm):
        """Kiểm tra chặn các URL không hợp lệ hoặc không thuộc danh sách nền tảng cho phép."""
        mock_perm.return_value = (True, "OK", {})

        # Malicious local IP or invalid scheme
        res = self.app.post('/api/download/start', json={'url': 'http://127.0.0.1/video.mp4'})
        self.assertEqual(res.status_code, 400)
        data = res.get_json()
        self.assertIn('URL không hợp lệ', data['error'])


if __name__ == '__main__':
    unittest.main()
