# Báo cáo rà soát tải video Douyin

Ngày rà soát: 2026-09-18

## Kết luận

Luồng hiện tại gồm hai engine: downloader.py cho video đơn và douyin_browser_downloader.py cho quét kênh/tải batch. Các yêu cầu chưa được bảo đảm đầy đủ.

Lỗi nghiêm trọng nhất: download_stream_file (douyin_browser_downloader.py:686) gửi Range nhưng không kiểm tra HTTP 206 và Content-Range. Nếu máy chủ trả 200 cho một part, toàn bộ file bị ghi vào part rồi các part bị nối lại, tạo file hỏng. download_stream_with_resume trong downloader.py có cùng rủi ro ở nhánh Range. Nhánh đa luồng cũng chưa resume theo từng part.

Việc bỏ watermark hiện chỉ dựa vào replace("playwm", "play") tại downloader.py:429, 451 và douyin_browser_downloader.py:293, 301, 576, 639. Đây không phải bảo đảm bản sạch: URL có thể 403/hết hạn hoặc vẫn chứa watermark. Code cũng chọn url_list[-1], trong khi thứ tự URL không phải hợp đồng chất lượng. Cần chọn theo metadata variant thực tế và xác minh bằng ffprobe sau tải.

Tải kênh dựa vào Playwright/scroll (douyin_browser_downloader.py:175), có giới hạn scroll và dễ vỡ khi DOM/API thay đổi. Bộ sưu tập chỉ được phát hiện gián tiếp trong DOM (dòng 492), gọi mix API một lần với cursor=0,count=50; chưa nhận URL/ID collection trực tiếp và chưa phân trang. Batch lưu URL lúc scan, có thể hết hạn trước lúc worker tải. Tên batch thêm 001_, tên tải đơn thêm [video_id] và cắt/sanitize tiêu đề. Chưa có job/API/UI để ghép nhiều tập thành video dài.

## Vị trí mã

- downloader.py:395, 705, 897, 1256: resolver, chọn format, Range downloader và tải đơn.
- douyin_browser_downloader.py:175: quét kênh; :492: collection; :686: stream downloader; :821: batch.
- routes/download.py:403: API batch SSE; khoảng dòng 100: API tải đơn.
- batch_queue_manager.py:400 và :480: hàng đợi xử lý URL lần lượt.
- web/app.js:11567 trở đi: UI quét kênh/chọn video/tải batch.
- Bản tương ứng cần đồng bộ trong patches/active; downloader.py và douyin_browser_downloader.py ở hai nơi hiện đang trùng hash.

## Phương án sửa

### 1. Resolver chất lượng cao, không watermark

Tạo resolve_douyin_variants(detail) dùng chung cho cả tải đơn và batch. Mỗi variant gồm URL, nguồn dữ liệu, width, height, fps, bitrate, codec, quality_type. Ưu tiên bit_rate có thông số cao nhất, download_addr/bản gốc, play_addr sạch; chỉ dùng thay playwm=play ở fallback cuối. Không lấy URL theo vị trí cuối danh sách. Probe HEAD hoặc GET Range nhỏ, chọn URL thực sự trả được và có điểm chất lượng cao nhất. Khi 403/410, resolve lại theo aweme_id. Sau tải chạy ffprobe, lưu độ phân giải/bitrate thực tế. Nếu Douyin chỉ cung cấp bản đã đóng watermark thì không thể xóa bằng downloader.

### 2. Downloader bền vững cho file dài

Gộp hai downloader Range thành một implementation. Mỗi request phải kiểm tra status 206, Content-Range đúng start-end/total và kích thước part. Nếu server trả 200 thì bỏ đa luồng, chuyển đơn luồng. Ghi manifest JSON gồm URL, tổng byte, ETag/Last-Modified, part hoàn thành và retry; restart chỉ tải part thiếu. Retry exponential backoff + jitter; refresh URL khi 403/410. Cho phép cấu hình connections_per_file và tổng connection. Không nạp file vào RAM; album ảnh cũng stream ra đĩa. Probe/hash cuối file.

### 3. Kênh và bộ sưu tập

Tách ChannelSource, CollectionSource và AwemePaginator. Playwright chỉ dùng để cấp cookie/chữ ký hoặc fallback. Dùng cursor/has_more thay cho số vòng scroll; max_items=None chạy đến hết. Collection nhận URL hoặc mix_id trực tiếp, phân trang đến hết, dedupe aweme_id và lưu mix_order/create_time. Lưu checkpoint source_id,cursor,seen_ids để resume. Nếu bị giới hạn trả partial cùng số lượng và cursor, không báo thành công giả.

### 4. Batch nhanh

Worker mặc định 3, cho phép 1–6; connection/file mặc định 4, có giới hạn tổng. Refresh metadata/link ngay trước tải. SSE theo từng video: queued, resolving, downloading, retrying, completed, failed, merged. Dùng job_id/registry thread-safe thay vì biến global. Không tính batch thành công nếu còn failed/partial.

### 5. Tên file và ghép tập

Lưu original_title và file_stem (chỉ loại ký tự cấm Windows), collision dùng (2), (3); prefix_index mặc định tắt. Lưu manifest gồm title, aweme_id, source_url, mix_id, create_time.

Thêm job merge sau batch: sắp theo mix_order hoặc thứ tự người dùng; probe từng file; file tương thích dùng concat demuxer -c copy, file khác dùng filter_complex concat và H.264/AAC. Tạo Tên bộ sưu tập (merged).mp4, giữ file gốc, có hủy/resume.

## Sửa theo file

- downloader.py: thay chọn URL tại _format_single_douyin_detail; sửa download_stream_with_resume theo kiểm tra 206/manifest/resume; ffprobe sau tải; tên file theo original_title.
- douyin_browser_downloader.py: bỏ Range downloader riêng và gọi implementation chung; lưu toàn bộ variant; thêm collection_url/mix_id, pagination/checkpoint; refresh URL; sửa batch filename.
- routes/download.py: thêm source_type, channel_url, collection_url, mix_id, max_items, workers, connections_per_file, filename_mode, merge_mode; thêm job status/cancel/merge.
- web/app.js: chọn Video/Kênh/Bộ sưu tập; Best available; cấu hình worker/connection/retry/tên/ghép; lỗi từng video và Retry failed.
- Đồng bộ vào patches/active và kiểm tra import path của bản release.

## Tiêu chí nghiệm thu

1. Variant sạch được chọn, ffprobe cuối khớp độ phân giải/bitrate.
2. Mock server 206 đúng range cho hash đúng; 200 cho Range phải fallback, không lặp file.
3. Dừng giữa chừng rồi chạy lại chỉ tải part thiếu.
4. Video 3–4 giờ không tăng RAM theo dung lượng.
5. Fixture nhiều cursor thu đủ đến has_more=0, không trùng ID.
6. Collection trên 50 item phân trang đủ và đúng thứ tự.
7. Batch 20 video không vượt giới hạn connection; URL hết hạn được refresh.
8. Tên Unicode/ký tự cấm/trùng tên hợp lệ và manifest giữ title.
9. Merge tương thích dùng copy; khác codec re-encode; duration/stream đúng.
10. Chạy test ở cả dev và release overlay.

## Thứ tự triển khai

1. Sửa resolver variant và Range downloader.
2. Hợp nhất tải đơn/batch, refresh URL/retry.
3. Crawler pagination kênh/collection và checkpoint.
4. Tên file/manifest.
5. Scheduler giới hạn connection.
6. Backend concat rồi UI.
7. Test fixture/mock trước khi thử link Douyin thật.

## Thư viện và lưu ý tránh xung đột

### Đã có trong requirements.txt

- requests: HTTP resolver và downloader.
- yt-dlp: các nền tảng khác; không dùng làm downloader Douyin chính nếu resolver riêng đã hoạt động.
- flask: API.
- platformdirs: lưu trạng thái hàng đợi.
- pywebview: desktop UI.
- ffmpeg_installer.py và bin/ffmpeg.exe/ffprobe.exe: xử lý media hiện có của dự án.

### Có thể phải bổ sung

- playwright: bắt buộc nếu vẫn dùng Browser fallback/quét kênh bằng Chromium.
- Trình duyệt Playwright Chromium: chạy python -m playwright install chromium trong đúng môi trường Python của ứng dụng.

Không cài thêm thư viện HTTP downloader thứ hai (aiohttp/httpx/aria2 wrapper) nếu chưa có lý do rõ ràng; ưu tiên giữ requests hiện tại và dùng ThreadPoolExecutor/asyncio chuẩn thư viện.

Không cài ffmpeg-python để thay FFmpeg executable hiện có. Mã hiện tại gọi ffmpeg/ffprobe qua ffmpeg_installer.py; phải dùng cùng binary để tránh lệch codec, PATH và bản Windows.

Không nâng yt-dlp hoặc requests tùy tiện trong lúc sửa Douyin. Ghim phiên bản đã kiểm thử trong requirements-lock hoặc lock file riêng.

Playwright phải được cài vào cùng virtual environment mà web_app.py chạy. Không trộn browser profile giữa Edge người dùng và Chromium test. Giữ user_data_dir Douyin hiện có và đóng context sau mỗi job.

Nếu thêm thư viện, phải ghi rõ tên/version, lý do, thay đổi requirements/lock file, lệnh cài Windows và cách rollback.

Lệnh kiểm tra môi trường:

    python -c "import requests, yt_dlp, flask; print('python deps ok')"
    python -c "from playwright.sync_api import sync_playwright; print('playwright package ok')"
    python -m playwright install --dry-run chromium
    ffmpeg -version
    ffprobe -version
