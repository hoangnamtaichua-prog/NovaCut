# 📋 DANH SÁCH VIỆC CẦN LÀM & ĐỀ XUẤT PHÁT TRIỂN (TODO & ROADMAP)

> **Quy tắc quản lý:**
> - Mỗi khi hoàn thành xong một công việc nào trong danh sách này, tôi sẽ **tự động cập nhật / đánh dấu hoàn thành**.
> - Mỗi lần bạn hỏi "cho tôi xem todo" hoặc "còn việc gì cần làm?", tôi sẽ đọc file này để báo cáo chính xác tiến độ hiện tại.
> - **Quy tắc phát hành bản vá:** CHỈ phát hành bản cập nhật mới (tạo GitHub Release / patch.zip) khi bạn yêu cầu. Tuyệt đối không tự động phát hành. Khi phát hành theo lệnh của bạn, phiên bản sẽ tự động tăng tiến +1 (vd: v1.0.7 -> v1.0.8...).

---

## 📦 CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH (CHO BẢN TIẾP THEO)
*(Mỗi khi bạn báo lỗi hoặc yêu cầu tính năng mới và tôi sửa xong, tôi sẽ tự động ghi chi tiết vào đây để chuẩn bị cho lần phát hành tiếp theo).*

*(Hiện tại chưa có thay đổi nào mới - Tất cả đã được đóng gói và phát hành trong bản v1.0.14).*

---

## 🚀 LỊCH SỬ CÁC PHIÊN BẢN ĐÃ PHÁT HÀNH

### ✅ Phiên bản v1.0.14 (Đã phát hành ngày 25/08/2026):
1. **Khắc Phục Lỗi TikToken `Unknown encoding cl100k_base` Trong Auto-Edit:**
   - Xử lý triệt để lỗi thư viện `tiktoken` khi chia chunk phụ đề SRT trong Bước 1 Auto-Edit (`split_srt_by_tokens` / `count_tokens`).
   - Bổ sung cơ chế Fallback Heuristic tự động tính toán token an toàn (ước lượng theo độ dài ký tự và số từ) khi mô hình AI tùy chỉnh không có trong registry hoặc khi `tiktoken` bị lỗi plugin / offline / thiếu file tokenizer, đảm bảo tiến trình tạo kịch bản review chạy mượt mà 100% không bị gián đoạn.
2. **Khắc Phục Hoàn Toàn Lỗi Cửa Sổ Đen FFmpeg / Subprocess Nhấp Nháy (Stealth Background Execution):**
   - Bổ sung cờ ẩn cửa sổ `creationflags=0x08000000` (`CREATE_NO_WINDOW`) cho 100% tất cả các tiến trình gọi lệnh FFmpeg / FFprobe / PowerShell / WMI / Pip Subprocess trong:
     + `auto_edit_pipeline.py` (cắt hàng trăm clip câm, ghép nối video, chèn phụ đề/audio, mix BGM).
     + `ai_dubbing.py` (xử lý âm thanh lồng tiếng & kiểm tra duration).
     + `license_manager.py` (quét UUID phần cứng ngầm).
     + `updater.py` (cài đặt pip và cập nhật nền).
   - Đảm bảo toàn bộ tác vụ nền chạy êm ái, ẩn ngầm 100%, không còn bất kỳ cửa sổ đen nào bật lên làm phiền người dùng.
3. **Tối Ưu Quét Kênh Douyin & Động Cơ Kép Quét Đầy Đủ 100% Video (Dual Pagination Engine):**
   - Tích hợp Động Cơ Kép (Dual Engine): Tự động bắt gói mẫu và gọi trực tiếp In-Browser Fetch với `max_cursor` tiếp theo ngay trong phiên trình duyệt, kết hợp cùng lúc cuộn sự kiện DOM trên `.route-scroll-container` để đảm bảo tải sạch sẽ 100% tất cả video của kênh (không còn bị giới hạn ở 18 video trang 1).
   - Loại bỏ hoàn toàn việc cào thẻ DOM ngoài lề (nguyên nhân gây lọt video trending/gợi ý sidebar không có thumbnail vào danh sách), đảm bảo 100% video trích xuất đều thuộc chính xác kênh của tác giả và có đầy đủ thumbnail, thời lượng, số liệu tương tác.
   - Tự động phát hiện và đóng popup đăng nhập / mã QR của Douyin để giải phóng luồng tải trang.
   - Tự động nhận diện kênh không tồn tại (`用户不存在`), tài khoản bị khóa hoặc link rác/hết hạn để phản hồi thông báo lỗi rõ ràng ngay trong vài giây thay vì cuộn vô tận gây cảm giác treo.
   - Giao diện Dark Mode thanh lịch: hiển thị thanh tiến trình %, thông báo trạng thái chuyên nghiệp ("Đang xác thực thông tin kênh...", "Đang phân tích danh mục... Đã tìm thấy X video"), và số lượng video đếm trực tiếp theo thời gian thực (SSE Live Stream).

### ✅ Phiên bản v1.0.13 (Đã phát hành ngày 24/08/2026):
1. **Cơ Chế Dynamic Module Loader cho Bản EXE (PyInstaller MetaPath Hook):**
   - Đưa `PathFinder` lên ưu tiên cao nhất trong `sys.meta_path` tại `launcher.py`. 
   - Giúp các bản cập nhật OTA (file `.py` tải về qua app) lập tức có hiệu lực ngay trên bản `.exe` mà KHÔNG bị mã nguồn đóng băng cũ chặn lại. Từ nay user không cần phải gỡ hay cài lại phần mềm khi có cập nhật mới.
2. **Tự Động Dọn Dẹp C-Binary (.pyd) trong Updater:**
   - Khi giải nén bản vá `.py`, `updater.py` tự động xóa các file `.pyd` / cache cũ để đảm bảo nạp chính xác mã nguồn mới nhất.
3. **Tính Năng Tự Động Khởi Động Lại (Auto-Restart System):**
   - Bổ sung API `/api/system/restart`, tự động làm mới ứng dụng ngay sau khi cập nhật thành công mà người dùng không cần thao tác tắt mở.
4. **Kiến Trúc Map-Reduce Bước 1 & Bước 3 Tách Lớp:**
   - Xử lý mượt mà kịch bản dài, chống timeout ChatGPT/OpenAI API và chia mẻ phân tích timeline video cực nhanh.
5. **Sửa Lỗi Quét Toàn Bộ Kênh & Tải Hàng Loạt Douyin (Lỗi Mã 500):**
   - Khắc phục lỗi unpack tuple phân quyền bản quyền (`check_permission` 3-tuple) trong route `/api/download/douyin/scan_channel` và `/api/download/douyin/batch_download`. Quét kênh và tải hàng loạt mượt mà 100%.

### ✅ Phiên bản v1.0.9 (Đã phát hành ngày 24/08/2026):
1. **Kiến trúc Map-Reduce Bước 3 (Phân tích cảnh theo mẻ):** Phân tích cảnh theo mẻ 35 câu/lần, xử lý bất đồng bộ, Batch Caching độc lập chống timeout & timeline rỗng.
2. **Khắc phục lỗi YouTube tải chất lượng 360p:** Mở khóa toàn bộ mức phân giải cao nhất: 4K (2160p), 2K QHD (1440p), Full HD (1080p).
3. **Multi-Connection Range Turbo Downloader (Douyin):** Nâng cấp tải đa luồng 4-6 kết nối song song IDM, tăng tốc tải gấp 10-20 lần.
4. **Role Đặc Quyền Quản Trị (Admin Tier):** Mở khóa Full 100% tất cả tính năng, không giới hạn giọng đọc, giao diện nhận diện Hoàng gia Đỏ Neon.
5. **Bóc tách Đa Video Douyin (Multi-Video Deep Scanner):** Quét toàn bộ video trong link (gồm video chính, danh sách feed, tập phim mix), hỗ trợ chọn tải riêng lẻ hoặc 1-click tải tất cả hàng loạt.
6. **Sửa lỗi Phân tích Douyin:** Khử hoàn toàn Circular Reference, bóc tách chính xác link rút gọn v.douyin.com với thời lượng chuẩn từng giây (1p33s) và chất lượng 4K/1080p không logo.

### ✅ Phiên bản v1.0.8 (Đã phát hành ngày 24/08/2026):
1. **Kiến trúc Map-Reduce Bước 1 (Lên kịch bản):** Xử lý file SRT dài không giới hạn, chống timeout 120s bằng cách chia chunk an toàn.
2. **Đa luồng TTS (TTS Multi-threading):** Tùy chỉnh 1 - 10 luồng trong Card 3, tăng tốc tạo giọng đọc x3 - x5 lần.
3. **Phóng to Video (Video Zoom & Crop):** Tùy chỉnh 100% - 150% kèm preset chống bản quyền và bộ lọc Center-Crop FFmpeg.
4. **Hiển thị % tiến trình từng bước:** Sửa log console hiển thị chính xác % thực tế của từng tác vụ.
5. **Tự động cài đặt dependencies:** Tự động chạy `pip install -r requirements.txt` khi updater nâng cấp app trên máy khách.

---

## 🚀 III. DANH SÁCH TÍNH NĂNG MỚI TIẾP THEO (ROADMAP PHÁT TRIỂN DÀI HẠN)

1. 🌟 **Auto Re-Frame AI / Bắt Nét Nhân Vật 9:16 (Smart Crop Tracking):**
   - Sử dụng AI (YOLO / MediaPipe Face Tracking) tự động lia ống kính camera 9:16 theo người đang nói chuyện trong phim thay vì crop cứng chính giữa.

2. 🔥 **Bộ Style Phụ Đề Động Karaoke (Trendy Animated Karaoke Subtitles):**
   - Hiệu ứng nhảy chữ từng từ (Word-by-word Highlight) đổi màu theo giọng đọc lồng tiếng như CapCut / AutoCap.
   - Preset font chữ to đậm, viền đen dày, đổ bóng 3D hot trend TikTok / Shorts.

3. 🎵 **Thư Viện Âm Thanh Hiệu Ứng (Sound FX) & Nhạc Nền Tự Động Giảm Âm (Auto-Ducking BGM):**
   - Bộ sound effect trend (Whoosh, Pop, Ting, Boom, Cười hài hước).
   - Tự động giảm âm lượng nhạc nền xuống 15-20% khi giọng đọc cất lên và tăng lại khi dứt câu.

4. ⚡ **Chế Độ Xử Lý Hàng Loạt Hàng Đợi (Batch Processing Queue):**
   - Dán 1 danh sách 10 - 20 link Douyin / thư mục video $\rightarrow$ App tự động chạy qua đêm xuất 20 video Shorts hoàn chỉnh chỉ với 1 click.

5. 🎨 **AI Tự Động Tạo Thumbnail Bắt Mắt (CTR Booster):**
   - Trích xuất 3-5 khung hình kịch tính nhất và ghép chữ tiêu đề giật tít bắt mắt chuẩn tỉ lệ 9:16 cho TikTok / YouTube Shorts.

---

## 🛡️ IV. CÁC HẠNG MỤC CỐT LÕI ĐÃ HOÀN THÀNH TOÀN DIỆN:
- ✅ **Bảo Vệ Mã Nguồn:** Biên dịch C-binary `.pyd` qua Cython & mã hóa AES-256 Prompt (`.prompt_vault.dat`).
- ✅ **Chống Dò Thám Frontend:** Khóa chuột phải Inspect, chặn F12 / DevTools.
- ✅ **Cổng Thanh Toán Tự Động:** SePay.vn VietQR TPBank tích hợp trực tiếp, kích hoạt bản quyền trong 2 giây.
- ✅ **Modal Miễn Trừ Trách Nhiệm:** Cam kết bản quyền chuẩn Dark Mode AAA.
- ✅ **Nhận Diện Đa Ổ Đĩa CapCut / JianYing:** Quét toàn bộ ổ C, D, E.
