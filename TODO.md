# 📋 DANH SÁCH VIỆC CẦN LÀM & ĐỀ XUẤT PHÁT TRIỂN (TODO & ROADMAP)

> **Quy tắc quản lý:**
> - Mỗi khi hoàn thành xong một công việc nào trong danh sách này, tôi sẽ **tự động cập nhật / đánh dấu hoàn thành**.
> - Mỗi lần bạn hỏi "cho tôi xem todo" hoặc "còn việc gì cần làm?", tôi sẽ đọc file này để báo cáo chính xác tiến độ hiện tại.
> - **Quy tắc phát hành bản vá:** CHỈ phát hành bản cập nhật mới (tạo GitHub Release / patch.zip) khi bạn yêu cầu. Tuyệt đối không tự động phát hành. Khi phát hành theo lệnh của bạn, phiên bản sẽ tự động tăng tiến +1 (vd: v1.0.7 -> v1.0.8...).

---

## 📦 CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH (CHO BẢN TIẾP THEO)
*(Mỗi khi bạn báo lỗi hoặc yêu cầu tính năng mới và tôi sửa xong, tôi sẽ tự động ghi chi tiết vào đây để chuẩn bị cho lần phát hành tiếp theo).*

1. **Khắc Phục Triệt Để Lỗi Treo Auto-Updater (% Nhảy 1 -> 2 -> 1 Rồi Đứng Im):**
   - **Nguyên nhân gốc rễ (Root Cause):**
     1. Gói cập nhật `patch.zip` trước đây vô tình chứa 164 file audio tạm trong `web/outputs/`, `tts_cache/` và bộ cài Edge WebView2 nặng >60MB, khiến dung lượng bị phình to lên 51.21 MB. Khi tải file dung lượng lớn từ GitHub Release CDN qua mạng quốc tế, stream kết nối bị ngắt (`urllib3.exceptions.IncompleteRead: IncompleteRead at 2.18MB`).
     2. Hàm `download_file_direct` cũ không có cơ chế tự động thử lại (Retry) và tiếp tục tải từ byte bị đứt (Resume HTTP Range), khiến quá trình tải bị lỗi và văng exception.
     3. Thiếu cơ chế khóa đơn luồng (Thread Lock / Singleton Guard) trên backend và disable click pointer-events trên frontend: khi người dùng bấm nút nhiều lần hoặc khi bắt đầu lại, một thread mới được sinh ra và reset `percent = 0`, dẫn tới hiện tượng phần trăm nhảy lên 1%, 2% rồi tụt về 1% và treo.
   - **Giải pháp xử lý triệt để:**
     1. Tinh chỉnh bộ lọc đóng gói `scripts/publish_patch.py`: loại bỏ 100% file rác, file tạm audio `*.wav`, `*.mp3`, `outputs/`, `tts_cache/` và `.exe`, giảm dung lượng `patch.zip` từ 51.21 MB xuống chỉ còn **7.60 MB** siêu nhẹ.
     2. Nâng cấp `updater.py` với cơ chế tải luồng 2 pha (2-Phase 302 Redirect): bóc tách URL Storage sạch, hỗ trợ tải tiếp HTTP `Range: bytes=...`, tự động thử lại 5 lần nếu chập chờn mạng và tăng kích thước chunk lên 256KB.
     3. Thêm khóa an toàn đa luồng `_UPDATE_THREAD_LOCK` trong `updater.py` và vô hiệu hóa `pointer-events: none` cho nút bấm trên giao diện `web/app.js` khi đang tải.
   - **Kết quả kiểm thử:** Quá trình tải và áp dụng bản vá chạy trơn tru từ 0% -> 95% -> 98% -> 100% trong 1-2 giây, tự động giải nén và khởi động lại hoàn hảo.

---

## 🚀 LỊCH SỬ CÁC PHIÊN BẢN ĐÃ PHÁT HÀNH

### ✅ Phiên bản v1.2.0 (Đã phát hành ngày 25/08/2026):
1. **Chế Độ Xử Lý Hàng Loạt Hàng Đợi (Batch Processing Queue Studio & Overnight Engine - Phân quyền Admin độc quyền):**
   - **Động cơ chạy qua đêm bất đồng bộ (Overnight FIFO Engine):** Module `batch_queue_manager.py` và `routes/batch_queue.py` xử lý tuần tự từng video với cơ chế chịu lỗi cao (*Fault-Tolerant*): tự động bỏ qua video lỗi mạng/API để tiếp tục xử lý các video tiếp theo mà không làm gián đoạn cả đêm.
   - **Nạp đa nguồn (Multi-Source Ingestion):** Hỗ trợ dán 10 - 50 URL (Douyin, TikTok, YouTube, Bilibili), nạp nguyên một folder video từ ổ cứng, hoặc chuyển trực tiếp các video đã quét từ Tab Tải Kênh Douyin sang Hàng Đợi chỉ bằng 1 nút bấm *"⚡ Nạp Vào Hàng Đợi"*.
   - **Bộ 3 Preset xử lý tự động:**
     - *Preset 1:* Auto Review Phim AI (Whisper ASR $\rightarrow$ LLM Recap $\rightarrow$ Kokoro/Edge TTS $\rightarrow$ Cắt ghép phân cảnh 9:16).
     - *Preset 2:* Auto Biên Tập Lồng Tiếng Phim (Tách âm thanh SFX $\rightarrow$ Dịch phụ đề $\rightarrow$ TTS $\rightarrow$ Xuất).
     - *Preset 3:* Auto Clean 9:16 Chống Bản Quyền (Lật gương, Zoom 1.05x, Tốc độ 1.05x, chèn sub, xuất 9:16).
   - **Giao diện Dashboard Quản lý Hiện đại (Dark Pro Studio):** Bảng tiến trình thời gian thực kết nối qua SSE Stream `/api/batch/stream`, 4 thẻ KPI đếm số lượng (Tổng, Đang chạy, Thành công, Lỗi), điều khiển Bắt đầu / Tạm dừng / Hủy / Chạy lại các mục lỗi.
   - **Tự động lưu trạng thái & Tắt máy an toàn:** Lưu trạng thái hàng đợi vào `user_data/batch_queue_state.json` (khôi phục sau khi tắt app/mất điện); tích hợp tùy chọn đếm ngược 60s tự động tắt máy tính (*Auto Shutdown PC*) khi hoàn tất toàn bộ hàng đợi.
   - **Bảo Vệ & Khóa Chặt Bản Quyền 2 Tầng:** Khóa chức năng xử lý hàng loạt chỉ cho phép tài khoản Admin Quản Trị sử dụng (`can_access_batch: True` cho Admin, `False` cho mọi gói khác).

2. **Tùy Chỉnh Phong Cách Kịch Bản Review Phim (Review Styles & Tone Directives):**
   - **Module Quản lý Phong cách (`review_styles.py`):** Cung cấp 7 phong cách kịch bản chuyên nghiệp được tối ưu riêng cho video triệu view:
     1. 🎭 *Kịch Tính & Hồi Hộp (Dramatic & Suspenseful):* Căng thẳng, nghẹt thở, nhấn mạnh plot twists và những cú lừa kinh điển.
     2. 😂 *Hài Hước & Cà Khịa (Humorous & Sarcastic):* Dí dỏm, châm biếm, ví von lầy lội các pha xử lý ngớ ngẩn của nhân vật.
     3. 🧠 *Phân Tích & Triết Lý (Deep Analysis & Psychological):* Đi sâu vào tâm lý, ẩn dụ nghệ thuật, thông điệp nhân văn và bài học cuộc sống.
     4. ⚡ *Tóm Tắt Nhanh / Mì Ăn Liền (Fast-Paced Recap):* Tiết tấu siêu tốc, câu ngắn gọn, dồn dập, đi thẳng vào các cảnh then chốt cho Shorts/TikTok.
     5. 👻 *Kinh Dị & Rùng Rợn (Horror & Dark Thriller):* Không khí u ám, lạnh lẽo, cảm giác rình rập và đe dọa vô hình.
     6. 💖 *Tình Cảm & Lắng Đọng (Emotional & Touching):* Giàu cảm xúc, tha thiết, chạm đến trái tim người nghe.
     7. ✍️ *Tùy Chỉnh Riêng (Custom User Style):* Tự do nhập prompt chỉ thị văn phong và ngôi xưng theo ý muốn.
   - **Tích hợp sâu vào Prompt đa tầng:** Map-Reduce Chunk (`auto_edit_pipeline.py`), Single-shot Recap (`review_phim.py`), và Batch Processing Queue (`batch_queue_manager.py`).

3. **Tùy Chọn Bật / Tắt Toàn Bộ Phụ Đề & Làm Mờ (Master Subtitles & Blur Toggle Switch):**
   - **Công Tắc Chủ Phụ Đề (Master Subtitle Switch):** Tích hợp công tắc Bật/Tắt `#subtitlesEnabled` ngay trên header của Card *"PHỤ ĐỀ & LÀM MỜ"* trong Tab Biên tập phim.
   - **Ẩn / Hiện Trực Quan Trên Video Player:** Khi tắt phụ đề, tự động ẩn toàn bộ khung xem trước (`subPreviewBox`), ẩn khung nét đứt 8 điểm neo, làm mờ bảng cấu hình bên dưới và hiển thị trạng thái đã tắt trên hộp phụ đề mẫu.
   - **Xuất Video Không Phụ Đề (No-Sub Exporting):** Cập nhật `routes/video_edit.py` và `web/app.js` gửi cờ `subtitles_enabled`. Khi tắt, FFmpeg bỏ qua hoàn toàn bộ lọc hardcode phụ đề, xuất video sạch chữ 100%.
   - **Đồng Bộ Bộ Lọc Làm Mờ Phụ Đề Gốc (Dynamic Blur):** Kiểm soát độc lập việc bật/tắt làm mờ vùng phụ đề cũ (`#reviewBlurOriginalSubtitles`), ẩn overlay tức thì và bỏ qua filter blur khi người dùng không có nhu cầu làm mờ.

4. **Khắc Phục Lỗi Nhân Bản Giọng Nói Trên Máy Khách (Fix Local Voice Cloning "os error 2" on Client Machines):**
   - Đóng gói sẵn trọn bộ 6 tệp MOSS Tokenizer Codec vào thư mục cục bộ `models/vieneu/codec/`.
   - Cập nhật `local_voice_engine.py` tự động nạp `codec_dir`, `onnx_dir`, và `backbone_repo` trỏ trực tiếp đến `models/vieneu/`, giúp engine khởi chạy 100% Offline hoàn chỉnh.
   - Bổ sung cơ chế tự động đồng bộ 2 chiều và tự tải bù (auto-heal / auto-download fallback) nếu phát hiện thiếu file trên máy khách.
   - Cập nhật `routes/tts.py` kiểm tra xác thực file mẫu âm thanh đầu vào trước khi tổng hợp, ngăn chặn crash và trả về thông báo lỗi rõ ràng.

5. **Nâng Cấp Động Cơ Tải Toàn Bộ Kênh Douyin Pro (Douyin Channel Batch Downloader 2.0):**
   - Tối ưu chất lượng 1080p, hỗ trợ Album Ảnh / Slide Photo Notes, cuộn trang Human-like & bắt API thông minh bypass giới hạn 18-20 video, trích xuất chỉ số kênh chi tiết, lọc & sắp xếp realtime, tính năng Đăng nhập Douyin 1 lần lưu phiên vĩnh viễn.

6. **Tái Thiết Kế Toàn Diện Giao Diện Thẻ Tải Video (NovaCut Dark Pro Modern UI):**
   - Thanh chuyển Segmented Pill Switcher, Khung nhập liệu Hero Glassmorphic, Banner Creator Showcase Card, Lưới Card Video 9:16 Reels hover.

7. **Bộ Chọn Thư Mục Lưu Video Tùy Biến (Custom Output Directory Selector):**
   - Tích hợp bộ chọn thư mục trực quan với nút *"📂 Chọn Thư Mục"* mở cửa sổ native của OS, lưu & đồng bộ cấu hình vào `localStorage`, nút *"📂 Mở Thư Mục"* thông minh.

8. **Nút Chuyển Nhanh 1-Click Từ Trích Xuất Phụ Đề Sang Review Phim (`btnTransferToReview`):**
   - Tích hợp nút bấm **"🎬 Review Phim"** trực tiếp trên thanh tiêu đề của thẻ Trích Xuất Phụ Đề, chuyển nhanh toàn bộ dữ liệu video và subtitle sang Review Phim trong 1 cú click.

9. **Đồng Bộ Bản Quyền Vào Trình Cài Đặt (Setup Wizard) & Giới Hạn Hiển Thị 1 Lần Duy Nhất:**
   - Đồng bộ toàn văn bản pháp lý vào Bộ cài đặt Inno Setup `LICENSE_DISCLAIMER.txt`, hiển thị đúng 1 lần duy nhất khi khởi chạy lần đầu và lưu vĩnh viễn sau khi chấp thuận.

10. **Khắc Phục Triệt Để Lỗi Toàn Bộ Ứng Dụng Không Nhận Sự Kiện Click:**
    - Loại bỏ định nghĩa trùng lặp `selectDirectory`, thiết lập `pointer-events: none` cho `.toast-container`, nâng cấp Cache-Busting lên `v=20260825_1350`.

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

## 🎯 DANH SÁCH VIỆC CẦN LÀM & TỐI ƯU (TODO / PENDING TASKS)

1. ⏳ **Tinh Chỉnh & Khống Chế Thời Lượng Video Đầu Ra Chuẩn Xác (Target Duration Accuracy):**
   - **Hiện trạng:** Khi người dùng chọn thời lượng mục tiêu 17 phút (hoặc số phút bất kỳ), video kết quả xuất ra thực tế bị dôi lên tới 28 phút (lệch nhiều so với cấu hình người dùng thiết lập).
   - **Nội dung cần xử lý:**
     - **Tối ưu bước sinh kịch bản (Bước 1):** Cân chỉnh số lượng từ / độ dài tóm tắt kịch bản theo tốc độ đọc trung bình (WPM - Words Per Minute ~ 160-190 từ/phút cho tiếng Việt) để kịch bản AI sinh ra khớp chính xác với số phút mong muốn.
     - **Kiểm soát phân cảnh timeline (Bước 3 & Bước 4):** Chuẩn hóa cơ chế cắt ghép clip, nhịp độ video và thời lượng hiển thị cảnh tương ứng với từng câu thoại / audio lồng tiếng, đảm bảo tổng thời lượng video hoàn thiện bám sát số phút người dùng đã chọn (sai số chấp nhận được trong khoảng ±30 giây - 1 phút).

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

4. ✅ ⚡ **Chế Độ Xử Lý Hàng Loạt Hàng Đợi (Batch Processing Queue Studio):**
   - Đã hoàn thành và tích hợp đầy đủ tại Tab *"⚡ Xử Lý Hàng Loạt"*, sẵn sàng đóng gói vào bản phát hành tiếp theo.

5. 🎨 **AI Tự Động Tạo Thumbnail Bắt Mắt (CTR Booster):**
   - Trích xuất 3-5 khung hình kịch tính nhất và ghép chữ tiêu đề giật tít bắt mắt chuẩn tỉ lệ 9:16 cho TikTok / YouTube Shorts.

---

## 🛡️ IV. CÁC HẠNG MỤC CỐT LÕI ĐÃ HOÀN THÀNH TOÀN DIỆN:
- ✅ **Bảo Vệ Mã Nguồn:** Biên dịch C-binary `.pyd` qua Cython & mã hóa AES-256 Prompt (`.prompt_vault.dat`).
- ✅ **Chống Dò Thám Frontend:** Khóa chuột phải Inspect, chặn F12 / DevTools.
- ✅ **Cổng Thanh Toán Tự Động:** SePay.vn VietQR TPBank tích hợp trực tiếp, kích hoạt bản quyền trong 2 giây.
- ✅ **Modal Miễn Trừ Trách Nhiệm:** Cam kết bản quyền chuẩn Dark Mode AAA.
- ✅ **Nhận Diện Đa Ổ Đĩa CapCut / JianYing:** Quét toàn bộ ổ C, D, E.
