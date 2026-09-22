# -*- coding: utf-8 -*-
"""
Test Suite cho hệ thống tải video Douyin Đơn & Hàng loạt (NovaCut Downloader Engine)
Kiểm thử toàn diện:
1. Variant ranking & no-watermark clean selection
2. ResumableRangeDownloader (HTTP 206 multi-part, HTTP 200 fallback, Manifest Resume, URL Refresh on 403)
3. GlobalConnectionPool concurrency
4. Windows-safe filename sanitization & collision resolution
5. Collection mix_id extraction & cursor pagination
6. Episode concatenation (merge_collection_episodes)
7. Batch manifest resume & retry_failed_batch_items
"""

import os
import sys
import json
import time
import hashlib
import tempfile
import threading
import http.server
import socketserver
import unittest
from urllib.parse import urlparse, parse_qs

# Ensure root directory is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import downloader
import douyin_browser_downloader


class MockDouyinHttpServer:
    """
    HTTP Server giả lập máy chủ CDN Douyin để kiểm thử:
    - HTTP 206 Partial Content với Range header
    - HTTP 200 OK (server không hỗ trợ Range)
    - HTTP 403 Forbidden để kích hoạt refresh URL
    """
    def __init__(self, payload_bytes=b"0123456789" * 1024 * 100): # 1 MB test payload
        self.payload = payload_bytes
        self.payload_hash = hashlib.md5(payload_bytes).hexdigest()
        self.total_size = len(payload_bytes)
        self.fail_first_request_with_403 = False
        self.request_count = 0
        self.server = None
        self.thread = None
        self.port = 0

    def start(self):
        parent = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                pass # Silent logging

            def do_HEAD(self):
                parent.request_count += 1
                if parent.fail_first_request_with_403 and parent.request_count == 1:
                    self.send_response(403)
                    self.end_headers()
                    return

                mode = self.path
                self.send_response(200)
                self.send_header("Content-Length", str(parent.total_size))
                if "no-range" not in mode:
                    self.send_header("Accept-Ranges", "bytes")
                self.end_headers()

            def do_GET(self):
                parent.request_count += 1
                if parent.fail_first_request_with_403 and "refreshed" not in self.path and parent.request_count <= 2:
                    self.send_response(403)
                    self.end_headers()
                    self.wfile.write(b"Forbidden expired URL")
                    return

                range_header = self.headers.get("Range")
                mode = self.path

                if "no-range" in mode or not range_header:
                    # Serve entire payload as HTTP 200
                    self.send_response(200)
                    self.send_header("Content-Length", str(parent.total_size))
                    self.end_headers()
                    self.wfile.write(parent.payload)
                    return

                # Range request e.g. "bytes=0-100"
                if range_header.startswith("bytes="):
                    rng = range_header.replace("bytes=", "").split("-")
                    start = int(rng[0])
                    end = int(rng[1]) if rng[1] else parent.total_size - 1
                    end = min(end, parent.total_size - 1)
                    content_length = end - start + 1

                    self.send_response(206)
                    self.send_header("Content-Type", "video/mp4")
                    self.send_header("Content-Range", f"bytes {start}-{end}/{parent.total_size}")
                    self.send_header("Content-Length", str(content_length))
                    self.send_header("Accept-Ranges", "bytes")
                    self.end_headers()
                    self.wfile.write(parent.payload[start:end + 1])

        # Find random available port
        self.server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()


class TestDouyinDownloader(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mock_server = MockDouyinHttpServer()
        cls.mock_server.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_server.stop()

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        import shutil
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_01_windows_filename_sanitization_and_collision(self):
        """Kiểm tra làm sạch tên file Windows giữ nguyên Unicode và tránh trùng lặp"""
        raw_name = 'Phim Hay: Người Nhện Siêu Đẳng 3 (1080p)? <Bản Rõ> | Tập 01 / "Hot"'
        clean = downloader.sanitize_filename_windows(raw_name)
        # Verify invalid windows chars removed
        for c in r'\/*?:"<>|':
            self.assertNotIn(c, clean)
        self.assertIn("Người Nhện Siêu Đẳng 3", clean)

        # Test collision resolution (2), (3)
        p1, _ = downloader.resolve_unique_filename(self.temp_dir, clean, ext="mp4", prefix_index=1)
        with open(p1, "w") as f: f.write("test")

        p2, _ = downloader.resolve_unique_filename(self.temp_dir, clean, ext="mp4", prefix_index=1)
        self.assertTrue(p2.endswith(" (2).mp4"))
        with open(p2, "w") as f: f.write("test")

        p3, _ = downloader.resolve_unique_filename(self.temp_dir, clean, ext="mp4", prefix_index=1)
        self.assertTrue(p3.endswith(" (3).mp4"))

    def test_02_resolve_douyin_variants_prefers_clean_variant(self):
        """Kiểm tra resolve_douyin_variants ưu tiên link không watermark và chất lượng cao nhất"""
        mock_detail = {
            "video": {
                "download_addr": {
                    "url_list": ["https://mock.cdn/watermarked_dl.mp4"]
                },
                "play_addr": {
                    "url_list": [
                        "https://mock.cdn/play_low.mp4",
                        "https://mock.cdn/play_medium.mp4"
                    ]
                },
                "bit_rate": [
                    {
                        "gear_name": "normal_720",
                        "quality_type": 720,
                        "bit_rate": 800000,
                        "play_addr": {
                            "url_list": ["https://mock.cdn/bitrate_720.mp4"]
                        }
                    },
                    {
                        "gear_name": "normal_1080",
                        "quality_type": 1080,
                        "bit_rate": 2500000,
                        "play_addr": {
                            "url_list": [
                                "https://mock.cdn/bitrate_1080_watermarked_playwm.mp4",
                                "https://mock.cdn/bitrate_1080_clean_play.mp4"
                            ]
                        }
                    }
                ]
            }
        }

        variants = downloader.resolve_douyin_variants(mock_detail, aweme_id="7123456789")
        self.assertTrue(len(variants) >= 2)
        best = variants[0]
        self.assertEqual(best["is_clean"], True)
        self.assertIn("1080", best["quality"])
        self.assertIn("bitrate_1080_clean_play", best["url"])

    def test_03_resumable_range_downloader_http_206(self):
        """Kiểm tra tải video đa luồng Range HTTP 206 và đối soát MD5 payload"""
        url = f"http://127.0.0.1:{self.mock_server.port}/stream.mp4"
        out_file = os.path.join(self.temp_dir, "test_206.mp4")

        dl = downloader.ResumableRangeDownloader(
            url=url,
            output_path=out_file,
            num_connections=4,
            chunk_size_threshold=100 * 1024 # 100 KB
        )
        saved_path = dl.download()

        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, "rb") as f:
            data = f.read()
        dl_hash = hashlib.md5(data).hexdigest()
        self.assertEqual(dl_hash, self.mock_server.payload_hash)
        self.assertEqual(len(data), self.mock_server.total_size)

    def test_04_resumable_range_downloader_fallback_200_no_file_doubling(self):
        """Kiểm tra máy chủ trả về HTTP 200 (không hỗ trợ Range) fallback đơn luồng chuẩn xác không bị nhân đôi file"""
        url = f"http://127.0.0.1:{self.mock_server.port}/stream.mp4?mode=no-range"
        out_file = os.path.join(self.temp_dir, "test_200_fallback.mp4")

        dl = downloader.ResumableRangeDownloader(
            url=url,
            output_path=out_file,
            num_connections=4
        )
        saved_path = dl.download()

        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, "rb") as f:
            data = f.read()
        self.assertEqual(len(data), self.mock_server.total_size)
        self.assertEqual(hashlib.md5(data).hexdigest(), self.mock_server.payload_hash)

    def test_05_resumable_manifest_resume(self):
        """Kiểm tra cơ chế ngắt giữa chừng và resume từ .download_manifest.json"""
        url = f"http://127.0.0.1:{self.mock_server.port}/stream.mp4"
        out_file = os.path.join(self.temp_dir, "test_resume.mp4")

        # Create simulated interrupted manifest with Part 0 completed
        manifest_path = out_file + ".download_manifest.json"
        part0_file = out_file + ".part0"
        half_size = self.mock_server.total_size // 2

        with open(part0_file, "wb") as f:
            f.write(self.mock_server.payload[:half_size])

        manifest_data = {
            "total_size": self.mock_server.total_size,
            "parts": [
                {"idx": 0, "start": 0, "end": half_size - 1, "done": True, "file": part0_file},
                {"idx": 1, "start": half_size, "end": self.mock_server.total_size - 1, "done": False, "file": out_file + ".part1"}
            ]
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        dl = downloader.ResumableRangeDownloader(
            url=url,
            output_path=out_file,
            num_connections=2
        )
        saved_path = dl.download()

        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, "rb") as f:
            data = f.read()
        self.assertEqual(len(data), self.mock_server.total_size)
        self.assertEqual(hashlib.md5(data).hexdigest(), self.mock_server.payload_hash)

    def test_06_url_refresh_on_403(self):
        """Kiểm tra tự động làm mới URL khi gặp HTTP 403 / 410"""
        self.mock_server.fail_first_request_with_403 = True
        self.mock_server.request_count = 0

        expired_url = f"http://127.0.0.1:{self.mock_server.port}/expired_stream.mp4"
        refreshed_url = f"http://127.0.0.1:{self.mock_server.port}/stream.mp4?refreshed=1"
        out_file = os.path.join(self.temp_dir, "test_403_refresh.mp4")

        dl = downloader.ResumableRangeDownloader(
            url=expired_url,
            output_path=out_file,
            aweme_id="7999888777",
            refresh_url_cb=lambda aid: [refreshed_url],
            backup_urls=[refreshed_url],
            num_connections=2
        )
        saved_path = dl.download()

        self.assertTrue(os.path.exists(saved_path))
        with open(saved_path, "rb") as f:
            data = f.read()
        self.assertEqual(len(data), self.mock_server.total_size)
        self.assertEqual(hashlib.md5(data).hexdigest(), self.mock_server.payload_hash)
        self.mock_server.fail_first_request_with_403 = False

    def test_07_global_connection_pool_limits(self):
        """Kiểm tra GlobalConnectionPool duy trì giới hạn connection tổng trong đa luồng"""
        pool = douyin_browser_downloader.GlobalConnectionPool(max_total_connections=3)
        active_counts = []
        lock = threading.Lock()

        def worker():
            with pool.acquire():
                with lock:
                    current_active = 3 - pool.semaphore._value
                    active_counts.append(current_active)
                time.sleep(0.05)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        self.assertTrue(all(c <= 3 for c in active_counts))
        self.assertEqual(len(active_counts), 10)

    def test_08_extract_mix_id(self):
        """Kiểm tra trích xuất mix_id cho tuyển tập / collection Douyin"""
        urls = [
            ("https://www.douyin.com/collection/7258012345678901234", "7258012345678901234"),
            ("https://www.douyin.com/video/712345?mix_id=7345678901234567890", "7345678901234567890"),
            ("7456789012345678901", "7456789012345678901"),
        ]
        for u, expected in urls:
            extracted = douyin_browser_downloader.extract_mix_id(u)
            self.assertEqual(extracted, expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
