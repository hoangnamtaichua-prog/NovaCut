Bạn là kỹ sư Python/Flask/Playwright/FFmpeg. Hãy sửa trực tiếp repository hiện tại để hoàn thiện tải video Douyin đơn và tải hàng loạt.

Đọc trước báo cáo tại REPORT_DOUYIN_DOWNLOAD_AUDIT.md và kiểm tra các file:
- downloader.py
- douyin_browser_downloader.py
- routes/download.py
- batch_queue_manager.py
- web/app.js
- các bản tương ứng trong patches/active

Mục tiêu bắt buộc:
1. Tải bản Douyin không watermark khi nguồn/API có cung cấp bản sạch.
2. Chọn variant có độ phân giải/bitrate cao nhất thực tế; không chọn URL chỉ dựa vào phần tử cuối của url_list.
3. Tải toàn bộ video của kênh và một collection/mix trực tiếp; phân trang đến has_more=0, dedupe aweme_id, giữ thứ tự mix_order.
4. Tải nhanh video dài 3–4 giờ và nhiều video đồng thời nhưng có giới hạn connection tổng.
5. Resume sau khi dừng, retry lỗi mạng, refresh URL khi 403/410.
6. Giữ tên tiêu đề gốc theo giới hạn tên file Windows, xử lý collision không phá manifest.
7. Cho phép ghép các tập thành video dài: copy stream nếu tương thích, re-encode nếu không tương thích.

Ràng buộc thư viện:
- Ưu tiên requests, ThreadPoolExecutor/asyncio, ffmpeg_installer.py và FFmpeg/FFprobe hiện có.
- Chỉ bổ sung playwright nếu môi trường chưa có và Browser fallback vẫn cần; cài đúng virtual environment bằng python -m playwright install chromium.
- Không thêm aiohttp/httpx/aria2 wrapper hoặc ffmpeg-python nếu không chứng minh cần thiết.
- Không nâng yt-dlp/requests tùy tiện; ghi phiên bản vào requirements/lock file nếu thay đổi.
- Không tạo hai downloader Range khác nhau. Hợp nhất logic tải đơn và batch dùng một implementation.
- Sửa đồng bộ thư mục gốc và patches/active; kiểm tra import path của bản release.

Yêu cầu triển khai kỹ thuật:
A. Tạo resolver variant chung cho Douyin, lưu URL, nguồn, width, height, fps, bitrate, codec, quality_type. Ưu tiên bit_rate/download_addr/play_addr sạch; playwm=play chỉ là fallback cuối.
B. Range downloader phải bắt buộc kiểm tra HTTP 206 và Content-Range cho từng part. Nếu server trả 200, chuyển đơn luồng. Ghi manifest và part riêng để resume. Không nối part nếu kích thước/Content-Range sai.
C. Có retry exponential backoff + jitter; refresh metadata/link theo aweme_id khi URL hết hạn. Có kiểm tra ffprobe/hash sau tải.
D. Crawler kênh/collection phải phân trang bằng cursor/has_more; max_items=None nghĩa là lấy đến hết; lưu checkpoint để tiếp tục.
E. Batch scheduler cho phép cấu hình workers và connections_per_file, có giới hạn tổng connection, trạng thái từng item và Retry failed.
F. Thêm job ghép tập với thứ tự mix_order hoặc thứ tự người dùng; tạo manifest và giữ file gốc.
G. Mở rộng API và UI nhưng giữ tương thích payload cũ nếu có thể.

Trước khi sửa:
- Xác định chính xác hàm/route đang được gọi ở dev và release.
- Không xóa tính năng nền tảng khác.
- Không thay đổi thư viện hàng loạt.

Sau khi sửa:
- Chạy kiểm tra import và syntax.
- Viết test/mock cho Range 206 đúng, server trả 200, resume part, URL 403 refresh, pagination nhiều cursor, collection >50 item, collision tên, merge copy/re-encode.
- Chạy test ở mã gốc và patches/active.
- Báo cáo file đã sửa, thư viện đã thêm (nếu có), lệnh cài, test đã chạy, giới hạn còn lại.
- Nếu phát hiện Douyin không cung cấp bản sạch cho một video, trả trạng thái rõ ràng thay vì tuyên bố đã xóa watermark bằng hậu kỳ.

