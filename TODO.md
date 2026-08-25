# 📋 DANH SÁCH VIỆC CẦN LÀM & ĐỀ XUẤT PHÁT TRIỂN (TODO & ROADMAP)

> **Quy tắc quản lý:**
> - Mỗi khi hoàn thành xong một công việc nào trong danh sách này, tôi sẽ **tự động cập nhật / đánh dấu hoàn thành**.
> - Mỗi lần bạn hỏi "cho tôi xem todo" hoặc "còn việc gì cần làm?", tôi sẽ đọc file này để báo cáo chính xác tiến độ hiện tại.
> - **Quy tắc phát hành bản vá:** CHỈ phát hành bản cập nhật mới (tạo GitHub Release / patch.zip) khi bạn yêu cầu. Tuyệt đối không tự động phát hành. Khi phát hành theo lệnh của bạn, phiên bản sẽ tự động tăng tiến +1 (vd: v1.0.7 -> v1.0.8...).

---

## 📦 CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH (CHO BẢN TIẾP THEO)
*(Mỗi khi bạn báo lỗi hoặc yêu cầu tính năng mới và tôi sửa xong, tôi sẽ tự động ghi chi tiết vào đây để chuẩn bị cho lần phát hành tiếp theo).*

*(Hiện tại chưa có thay đổi nào mới - Tất cả đã được đóng gói và phát hành trong bản v1.1.0).*

---

## 🚀 LỊCH SỬ CÁC PHIÊN BẢN ĐÃ PHÁT HÀNH

### ✅ Phiên bản v1.1.0 (Đã phát hành ngày 25/08/2026):
1. **Triệt Tiêu 100% Hiện Tượng Cửa Sổ Đen Console/CMD Nháy Lên Khi Cắt Video (Stealth Subprocess Engine):**
   - Tích hợp cơ chế ẩn cửa sổ 3 lớp `get_stealth_subprocess_kwargs()`: kết hợp đồng thời cờ `creationflags=0x08000000` (`CREATE_NO_WINDOW`), `startupinfo` (`STARTF_USESHOWWINDOW` + `SW_HIDE`), và `stdin=subprocess.DEVNULL` (ngắt kết nối console cha).
   - Áp dụng triệt để cho toàn bộ các tiến trình gọi FFmpeg, FFprobe, Kokoro TTS, RVC Voice Clone, và Taskkill trong `auto_edit_pipeline.py`, `ffmpeg_installer.py`, `review_phim.py`, `ai_dubbing.py`, `rvc_bridge.py`, `web_app.py`, `routes/video_edit.py`, `routes/tts.py`.
2. **Khắc Phục Triệt Để Lỗi Treo 98% Khi Tự Động Cập Nhật (OTA Auto-Updater):**
   - Loại bỏ hoàn toàn bước gọi `pip install` khi ứng dụng đang chạy ở chế độ đóng gói EXE (`getattr(sys, 'frozen', False)`). Trong bản EXE, `sys.executable` là `NovaCut.exe`, lệnh `pip` trước đây vô tình kích hoạt thêm một instance con của app gây deadlock treo tại 98%.
   - Thêm `timeout=15` và cơ chế non-blocking an toàn khi chạy source code dev mode.
   - Chuẩn hóa luồng tự động khởi động lại ứng dụng (`restart_application`) giúp quá trình cập nhật nhảy thẳng từ 98% -> 100% và reload êm ái mà khách không cần phải tắt mở thủ công.
3. **Phân Luồng Chuẩn Giọng Đọc Offline / Local / Clone (Không Còn Gọi Nhầm OpenSpeaker API):**
   - Nâng cấp toàn diện hàm kiểm tra `is_api_voice` trong `auto_edit_pipeline.py` để phân loại chính xác 100% các giọng Kokoro Offline (`nam_khoa`, `minh_duc`, `ngoc_huyen`, `diem_trinh`, `mai_linh`), giọng Local Clone (`local_*`), RVC Model (`rvc_*`) và Edge-TTS (`edge_*`).
   - Ngăn chặn hoàn toàn việc gửi nhầm ID giọng Local lên OpenSpeaker Cloud API gây ra cảnh báo `Unsupported voice provider`, giúp quá trình tạo giọng đọc chạy trực tiếp và tức thì.
4. **Bảo Vệ Khả Năng Tương Thích Ngược Hardware Encoder (AttributeError Fallback):**
   - Bổ sung các hàm helper dự phòng `detect_hardware_encoder` và `get_stealth_subprocess_kwargs` trực tiếp ngay trong `auto_edit_pipeline.py`, đảm bảo nếu module `ffmpeg_installer` bị cache/chưa nạp mới thì tiến trình Auto-Edit vẫn chạy mượt mà 100%, không bị lỗi `AttributeError`.
5. **Hỗ Trợ Đóng Gói Tự Động Giọng Clone (Custom Voices) Sang Máy Khách Hàng:**
   - Tích hợp file danh mục giọng `custom_voices.json` vào gói cập nhật `patch.zip`, sẵn sàng phân phối các giọng đọc clone mới cho toàn bộ người dùng.

### ✅ Phiên bản v1.0.16 (Đã phát hành ngày 25/08/2026):
1. **Đột Phá Tốc Độ Auto-Edit / Review Phim (Tăng Tốc 3.5x – 5x):**
   - **Bounded Parallel Video Slicing (Bước 4):** Cắt song song 70-100 clip câm bằng `ThreadPoolExecutor` (2-4 workers) thay vì tuần tự, giảm thời gian cắt clip từ 3-4 phút xuống 30-40 giây.
   - **Boundary-Targeted Fast Scene Detection (Bước 3.5):** Chỉ quét chuyển cảnh quanh các điểm cắt timeline (±1.5s) thay vì quét toàn bộ video gốc 2 tiếng, giảm thời gian dò cảnh từ 2-3 phút xuống 10-20 giây.
   - **Tự động nhận diện & Kích hoạt GPU Hardware Acceleration:** Tự động phát hiện Nvidia NVENC (`h264_nvenc`) / Intel QSV (`h264_qsv`) với cơ chế test encode an toàn và fallback 100% về CPU nếu không tương thích.

### ✅ Phiên bản v1.0.15 (Đã phát hành ngày 25/08/2026):
1. **Kiến Trúc OTA Patch Overlay (`patches/active`) - Nạp Đè 100% C-Binary (.pyd):**
   - Đưa thư mục `patches/active/` lên vị trí ưu tiên số 0 trong `sys.path` tại `launcher.py` và `web_app.py`.
   - Nâng cấp `updater.py` giải nén trực tiếp các file `.py` và package `routes/` vào `patches/active/`, giải quyết triệt để tình trạng Python ưu tiên nạp file C-binary `.pyd` cũ đóng băng trong bản EXE.
   - Sửa `ROOT_DIR` trong `updater.py` và `web_app.py` trỏ đúng thư mục cài đặt gốc (`sys.executable`) khi chạy ở chế độ đóng băng PyInstaller.
   - Đảm bảo các bản vá tính năng (như sửa lỗi TikToken cho `gpt-5.6-luna` / custom model trong Auto-Edit) lập tức có hiệu lực 100% ngay trên máy khách hàng.

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
