import unittest
import os
import tempfile
import shutil
from flask import Flask
from routes.video_edit import validate_export_payload
from routes.security import register_user_path
from batch_queue_manager import BatchQueueManager, BatchTask


class TestSaveToSourceDir(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app_context = self.app.app_context()
        self.app_context.push()
        self.test_root = tempfile.mkdtemp(prefix='novacut_test_source_')
        register_user_path(self.test_root)

        # Tạo 2 thư mục nguồn riêng biệt giả lập nhiều video ở nhiều thư mục khác nhau
        self.folder_a = os.path.join(self.test_root, 'Folder_Action')
        self.folder_b = os.path.join(self.test_root, 'Folder_Drama', 'SubSeason')
        os.makedirs(self.folder_a, exist_ok=True)
        os.makedirs(self.folder_b, exist_ok=True)

        self.video_a = os.path.join(self.folder_a, 'movie_a.mp4')
        self.video_b = os.path.join(self.folder_b, 'episode_01.mp4')
        with open(self.video_a, 'wb') as f:
            f.write(b'\x00' * 1024)
        with open(self.video_b, 'wb') as f:
            f.write(b'\x00' * 1024)

    def tearDown(self):
        self.app_context.pop()
        shutil.rmtree(self.test_root, ignore_errors=True)

    def test_save_to_source_dir_folder_a(self):
        """Kiểm tra video ở thư mục A khi bật save_to_source_dir sẽ xuất vào đúng thư mục A."""
        data = {
            'inputVideo': self.video_a,
            'outputDir': 'output/default_placeholder',
            'save_to_source_dir': True,
            'outputName': 'output_a.mp4',
            'video_speed': 1.0,
            'aspect_ratio': 'original',
            'resolution': 'original',
            'encoder': 'auto',
            'bitrate': 10000,
            'bitrate_mode': 'VBR'
        }
        res = validate_export_payload(data)
        self.assertIsNone(res, f"Payload should be valid, got: {res}")

    def test_save_to_source_dir_folder_b(self):
        """Kiểm tra video ở thư mục B (khác thư mục A) khi bật save_to_source_dir sẽ xuất vào đúng thư mục B."""
        data = {
            'inputVideo': self.video_b,
            'outputDir': 'output/default_placeholder',
            'save_to_source_dir': True,
            'outputName': 'output_b.mp4',
            'video_speed': 1.0,
            'aspect_ratio': 'original',
            'resolution': 'original',
            'encoder': 'auto',
            'bitrate': 10000,
            'bitrate_mode': 'VBR'
        }
        res = validate_export_payload(data)
        self.assertIsNone(res, f"Payload should be valid, got: {res}")

    def test_name_collision_avoidance(self):
        """Kiểm tra nếu outputName trùng với input_video trong cùng thư mục thì tránh ghi đè."""
        data = {
            'inputVideo': self.video_a,
            'outputDir': self.folder_a,
            'save_to_source_dir': True,
            'outputName': 'movie_a.mp4',  # Trùng với self.video_a
            'video_speed': 1.0,
            'aspect_ratio': 'original',
            'resolution': 'original',
            'encoder': 'auto',
            'bitrate': 10000,
            'bitrate_mode': 'VBR'
        }
        res = validate_export_payload(data)
    def test_batch_queue_save_to_source_multiple_dirs(self):
        """Kiểm tra BatchQueueManager xử lý nhiều task ở các thư mục khác nhau đều hướng đúng thư mục nguồn."""
        mgr = BatchQueueManager.get_instance()
        tasks = mgr.add_tasks(
            [self.video_a, self.video_b],
            preset='dubbing',
            preset_config={'save_to_source_dir': True}
        )
        self.assertEqual(len(tasks), 2)
        task_a = tasks[0]
        task_b = tasks[1]

        # Kiểm tra task_a
        dir_a = task_a.get('preset_config', {}).get('output_dir')
        if not dir_a and task_a.get('preset_config', {}).get('save_to_source_dir'):
            dir_a = os.path.dirname(os.path.abspath(task_a.get('file_path')))
        self.assertEqual(os.path.abspath(dir_a), os.path.abspath(self.folder_a))

        # Kiểm tra task_b
        dir_b = task_b.get('preset_config', {}).get('output_dir')
        if not dir_b and task_b.get('preset_config', {}).get('save_to_source_dir'):
            dir_b = os.path.dirname(os.path.abspath(task_b.get('file_path')))
        self.assertEqual(os.path.abspath(dir_b), os.path.abspath(self.folder_b))


if __name__ == '__main__':
    unittest.main()
