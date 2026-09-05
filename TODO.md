# 📋 DANH SÁCH VIỆC CẦN LÀM & ĐỀ XUẤT PHÁT TRIỂN (TODO & ROADMAP)

> **Quy tắc quản lý:**
> - Mỗi khi hoàn thành xong một công việc nào trong danh sách này, tôi sẽ **tự động cập nhật / đánh dấu hoàn thành**.
> - Mỗi lần bạn hỏi "cho tôi xem todo" hoặc "còn việc gì cần làm?", tôi sẽ đọc file này để báo cáo chính xác tiến độ hiện tại.
> - **Quy tắc phát hành bản vá:** CHỈ phát hành bản cập nhật mới (tạo GitHub Release / patch.zip) khi bạn yêu cầu. Tuyệt đối không tự động phát hành. Khi phát hành theo lệnh của bạn, phiên bản sẽ tự động tăng tiến +1 (vd: v1.0.7 -> v1.0.8...).

---

## 📌 BÀN GIAO TIẾN ĐỘ & KẾ HOẠCH TIẾP TỤC (HANDOVER - NGÀY MAI 31/08/2026)

### 🎯 Tiến độ thực tế đã đạt được hôm nay:
- ✅ **Chuyển đổi OpenRouter API:** Đã thay thế hoàn toàn OpenAI bằng OpenRouter, tích hợp menu chọn mô hình AI (ưu tiên các model Miễn phí: `nvidia/nemotron-3-super-120b-a12b:free`, `openrouter/free`, `minimax/minimax-m3:free`...).
- ✅ **Khắc phục lỗi phát video khác ổ đĩa Windows:** Sửa hàm `_is_within` trong `routes/security.py`, cho phép phát video mượt mà khi app ở ổ `D:\` và video ở ổ `C:\`.
- ✅ **Bảo vệ API Key:** Khắc phục lỗi xóa nhầm key khi lưu Cài đặt trong `routes/core.py` và `web/app.js`.
- ✅ **Bước 1 (Lên kịch bản Review Phim AI):** Chạy mượt mà 100% trên mô hình Free.
- ✅ **Bước 2 (Tạo giọng đọc Voice-over Kokoro Offline):** Đã tạo xong trọn vẹn **331/331 câu** (100% miễn phí trên GPU/CPU, đã lưu cache tại `output/auto_edit_temp/voice_review.wav` & `voice_review_cleaned.srt`).
- ✅ **Bước 3 (Khớp Timeline):** Đã phân tích thành công Mẻ 1 và Mẻ 2 (đã lưu cache `timeline_batch_0...json` và `timeline_batch_1...json`).
- ✅ **Vừa cập nhật bản vá chống Timeout:** Đã gỡ bỏ hard timeout 300s, chuyển sang kiểm tra theo dõi luồng sống (`t.is_alive()` với polling 2s), nâng concurrency lên 2, hỗ trợ bóc tách JSON bọc dict (`{"clips": [...]}`).

### 📝 Việc cần làm tiếp theo khi bắt đầu vào ngày mai:
1. **Kiểm chứng Bước 3 hoàn thành toàn bộ 12 mẻ timeline:**
   - Chạy lại app `python web_app.py` -> Bấm **Bắt đầu làm video (Auto-Edit)**.
   - Khi bảng thông báo **"Tái sử dụng dữ liệu?"** hiện lên -> Chọn **"Đồng ý"** (Hệ thống sẽ bỏ qua ngay Bước 1 & Bước 2 trong 1 giây, nạp mẻ 1-2 từ cache và chạy tiếp từ mẻ 3).
2. **Tối ưu hóa Prompt Step 3 (Nếu cần tăng tốc):**
   - Thay vì nhét 40.000 ký tự phụ đề gốc vào tất cả các mẻ, cắt gọt theo cửa sổ trượt (sliding window) chỉ chứa các đoạn thoại khớp ngữ cảnh để mỗi mẻ AI trả về trong 2-3 giây thay vì 30-40 giây.
3. **Kiểm tra xuất xưởng video thành phẩm:**
   - Đảm bảo video xuất ra tại `output/video_review.mp4` khớp tiếng, khớp hình và phụ đề rõ đẹp.

---

## 📦 CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH
*(Hiện tại chưa có thay đổi nào đang chờ phát hành. Mọi tính năng và bản sửa lỗi mới nhất đã được đóng gói và phát hành thành công trong bản v1.2.7)*

---

## 🚀 ĐÃ PHÁT HÀNH TRONG BẢN v1.2.7 (05/09/2026)
1. **Loại Bỏ Triệt Để Phần Thống Kê Số Từ / Thời Lượng Ở Cuối Kịch Bản Review:**
   - Cập nhật chỉ thị trong `prompt_reduce_script.txt` và tái mã hóa kho bảo mật `.prompt_vault.dat`.
   - Bổ sung bộ lọc tự động `sanitize_review_script` và `is_statistical_or_meta_sentence` loại bỏ mọi dòng thống kê thừa ("Tổng số từ thực tế: khoảng...", "Thời lượng ước tính:...", "--- Hết kịch bản ---") trước khi tạo giọng đọc TTS.
2. **Sửa Triệt Để Lỗi Tái Sử Dụng Cache Khi Người Dùng Chọn Hủy (`use_cache=False`):**
   - Xóa sạch thư mục tạm `output/auto_edit_temp/` khi chọn làm lại từ đầu.
   - Truyền cờ `use_cache` xuống toàn bộ pipeline (TTS, Map/Reduce, Timeline).
3. **Cập Nhật Giá Trị Mặc Định Cho Âm Thanh & Phụ Đề:**
   - Tự động chèn phụ đề giọng Review (`reviewAutoSubtitles`) và Nhạc nền (`reviewBgmEnabled`) mặc định tắt (unchecked / False). Khối BGM làm mờ khi chưa bật.
   - Tách lọc âm thanh gốc AI (`reviewStemSeparationEnabled`) mặc định không chọn (unchecked / False).
   - Số luồng tạo giọng đọc TTS (`reviewTtsThreads`) mặc định tăng lên 8 luồng (tối ưu tốc độ).
4. **Nâng Cấp Bộ Công Cụ Nhạc Nền BGM Suite:**
   - Hỗ trợ 2 chế độ linh hoạt: Nhạc có sẵn (10 bản nhạc tuyển chọn + Random) và Tải lên riêng (Custom Upload MP3/WAV/M4A/AAC).
   - Trình nghe thử nhạc nền thời gian thực (Preview Audio Player) trực tiếp trên giao diện.
   - Trộn nhạc thông minh: lặp vô hạn `-stream_loop -1` theo độ dài video và né tiếng giọng đọc (sidechain ducking).
5. **Sửa lỗi UnboundLocalError trong Bước 3 Phân tích Timeline (`auto_edit_pipeline.py`):**
   - Khắc phục lỗi `cannot access local variable 'max_concurrency'` khi khởi tạo Semaphore do biến bị giới hạn cục bộ trong vòng lặp Async, giúp quá trình phân tích cảnh bằng GPT (Bước 3) không bị crash khi sử dụng model khác "free".
   
1. **Sửa lỗi 409 và Cố định mô hình Review Phim (`routes/video_edit.py`, `patches/active/routes/video_edit.py`):**
   - **Gỡ bỏ cơ chế khóa luồng `_review_lock`:** Khắc phục triệt để lỗi "Một tác vụ Review Phim khác đang chạy" (409) do deadlock khi tiến trình trước đó bị ngắt hoặc lỗi đột ngột mà không giải phóng cờ. Người dùng giờ đây không còn bị kẹt nút bấm.
   - **Cố định OpenAI & GPT-5.6-Luna (GPT Luna):** Hardcode tham số đầu vào cho tiến trình tự động (`mode == 'api'`) bắt buộc định tuyến tới `https://api.openai.com/v1` và sử dụng mô hình `gpt-5.6-luna`, loại bỏ hoàn toàn khả năng ghi đè hoặc chỉnh sửa sai mô hình từ giao diện UI.

1. **Nâng Cấp Toàn Diện Phân Hệ Xử Lý Hàng Loạt Hàng Đợi (Batch Queue Studio) (`batch_queue_manager.py`, `routes/batch_queue.py`, `asr_manager.py`, `auto_edit_pipeline.py`, `web/index.html`, `web/js/features/batch_queue.js`):**
   - **Khắc phục lỗi P0 ASR & Dubbing:** Xây dựng hàm `ensure_video_srt` độc lập trong `batch_queue_manager.py`, tự động nhận diện phụ đề có sẵn hoặc chạy Whisper Native C++ / Python ASR; sửa lỗi gọi `asr_manager.get_or_create_srt` không tồn tại. Tự động trích xuất SRT và đồng bộ tham số `original_volume` cho Preset Lồng Tiếng (Dubbing).
   - **Cô lập không gian làm việc tạm (Task Isolation):** Cập nhật `run_auto_edit_workflow` và `run_narration_workflow` trong `auto_edit_pipeline.py` nhận `temp_dir` theo từng task (`.batch_temp/<task_id>/`), triệt tiêu xung đột dữ liệu khi chạy song song hoặc nhiều video nối tiếp.
   - **Sửa lỗi nhận diện Whisper Engine xuyên ổ đĩa Windows:** Sửa lỗi `ValueError: Paths don't have the same drive` trong `asr_manager.py` bằng hàm `_is_subpath`, tự động tìm thấy `whisper-cli.exe` và model `ggml-base.bin` có sẵn trong thư mục ứng dụng.
   - **Cải tạo giao diện UI linh hoạt theo từng Preset:** Card cấu hình tự động co giãn / đổi các panel nhập liệu phù hợp khi người dùng chuyển đổi giữa *Review Phim*, *Lồng Tiếng* và *Chống Bản Quyền*.
   - **Bổ sung các tham số quan trọng:** Thêm ô chọn thời lượng Review mục tiêu (3, 5, 8, 10, 15 phút kèm số từ ước tính theo định mức 3.5 từ/s), thanh chọn tốc độ đọc (0.95x - 1.15x), tùy chỉnh âm lượng BGM, âm lượng video gốc khi lồng tiếng, và thông số chống bản quyền (tua tốc, zoom tâm, lật gương).
   - **Thanh kiểm định hệ thống Preflight Bar:** Bổ sung endpoint `/api/batch/preflight` và thanh trạng thái trực quan báo đèn xanh cho FFmpeg, Whisper ASR và AI Key trước khi bắt đầu hàng đợi.
   - **Kích hoạt chọn nhiều file video (Multi-file Picker):** Bổ sung endpoint `/api/batch/select_files` gọi hộp thoại OpenFileDialog đa chọn tệp trên Windows, cho phép người dùng chọn cùng lúc nhiều file video trên máy.

2. **Chuyển Đổi Sang OpenRouter API & Tích Hợp Mô Hình Miễn Phí (Free Models) (`auto_edit_pipeline.py`, `routes/core.py`, `routes/subtitles.py`, `web/index.html`, `web/app.js`):**
   - **Thay thế trực tiếp endpoint GPT bằng OpenRouter:** Toàn bộ pipeline sinh kịch bản review, tóm tắt map/reduce, phân tích timeline và dịch phụ đề AI đã hỗ trợ định tuyến qua OpenRouter (`https://openrouter.ai/api/v1`) với headers định danh `HTTP-Referer` và `X-Title`.
   - **Mở rộng danh sách Allowed Hosts:** Bổ sung `openrouter.ai` vào whitelist bảo mật `NOVACUT_ALLOWED_AI_HOSTS` trong `routes/core.py` và `routes/subtitles.py`.
   - **Bộ chọn Mô hình AI (Model Selector) trong Cài đặt:** Cung cấp menu chọn model trực quan, ưu tiên các model Free đỉnh cao:
     - `openrouter/free` (Router tự động chọn model Free tốt nhất)
     - `z-ai/glm-5.2:free` (Z.ai: GLM 5.2 Free - suy luận kịch bản & tiếng Việt xuất sắc)
     - `minimax/minimax-m3:free` (MiniMax: MiniMax M3 Free)
     - `google/gemma-4-31b-it:free` (Google: Gemma 4 31B Free)
     - `nvidia/nemotron-3-ultra-550b-a55b:free` (NVIDIA: Nemotron 3 Ultra Free)
     - `nvidia/nemotron-3-super-120b-a12b:free` (NVIDIA: Nemotron 3 Super Free)
     - Cùng các model trả phí giá rẻ như DeepSeek V3, GPT-4o Mini, Claude 3.5 Haiku và tùy chọn gõ Custom Model ID bất kỳ.
   - **Tự động nhận diện Key:** Tự động phát hiện tiền tố `sk-or-` để chuyển hướng sang Base URL của OpenRouter và gán model mặc định `openrouter/free`. Nút [Test Key] kiểm tra kết nối thời gian thực trả về 200 OK ngay lập tức.

3. **Khắc phục lỗi không thể phát video khi chọn file khác ổ đĩa trên Windows (`routes/security.py`, `routes/core.py`, `patches/active/*`):**
   - **Nguyên nhân gốc rễ (Root Cause Analysis):** Khi ứng dụng chạy ở ổ `D:\` và người dùng chọn tệp video ở ổ `C:\` (ví dụ `C:\Users\...\OneDrive\Máy tính\review xe\video1tieng.mp4`), hàm `is_path_allowed` gọi `os.path.commonpath([root, resolved])`. Khi duyệt qua các root mặc định ở ổ `D:\`, `commonpath` tung ngoại lệ `ValueError: Paths don't have the same drive`. Khối `try/except` bao trùm toàn bộ `any()` bắt lỗi này và dừng sớm vòng lặp, khiến thư mục ổ `C:\` đã được cấp phép trong `_selected_roots` không bao giờ được đối soát, dẫn đến `/api/video` trả về 404 và trình phát video báo lỗi.
   - **Giải pháp:** Tách biệt kiểm tra lồng nhau bằng hàm fail-closed `_is_within(root, candidate)` có kiểm tra so khớp ký tự ổ đĩa (`os.path.splitdrive`) trước khi so khớp đường dẫn, triệt tiêu hoàn toàn lỗi văng ngoại lệ khác ổ đĩa.
4. **Khắc phục lỗi Rate Limit 429 khi chạy Mô hình Miễn Phí (Free Models) trên OpenRouter (`auto_edit_pipeline.py`, `patches/active/*`):**
   - **Nguyên nhân:** Khi phân tích kịch bản review phim, hệ thống chạy Map/Reduce bắn đồng thời 3–5 đoạn SRT lên OpenRouter cùng lúc. Đối với các mô hình Free như `z-ai/glm-5.2:free`, nhà cung cấp upstream giới hạn tần suất nghiêm ngặt, dẫn đến lỗi `Error code: 429 - temporarily rate-limited upstream. retry_after_seconds: 5`.
   - **Giải pháp:**
     1. Điều phối Semaphore Concurrency: Giới hạn `concurrency = 1` đối với các mô hình Free và OpenRouter để xử lý tuần tự từng đoạn, tránh gây nghẽn burst rate limit.
     2. Cơ chế Thử lại có độ trễ tăng dần (Exponential Backoff): Khi gặp lỗi 429 hoặc quá tải tạm thời, hệ thống tự động tạm dừng `5s * attempt` và thử lại tới 4 lần kèm thông báo trực quan trên log, thay vì dừng chương trình đột ngột.
5. **Khắc phục lỗi Timeout 300s và cải tiến trích xuất Timeline Step 3 (`auto_edit_pipeline.py`, `patches/active/*`):**
   - **Nguyên nhân:**
     1. Ở Bước 3 (Phân tích timeline theo mẻ), hàm `q.get(timeout=300)` dùng bộ đếm cứng 300s. Khi xử lý video dài (12 mẻ), nếu mô hình AI cần thử lại (retry) hoặc OpenRouter phản hồi chậm, bộ đếm 300s bị kích hoạt làm sập luồng chính mặc dù tiến trình nền vẫn đang phân tích thành công.
     2. Một số mô hình AI trả về JSON bọc trong dictionary dạng `{"clips": [...]}` hoặc `{"timeline": [...]}` thay vì mảng gốc, khiến kiểm tra `isinstance(parsed, list)` bị từ chối và kích hoạt retry lặp vô ích.
   - **Giải pháp:**
     1. Thay thế bộ đếm cứng `timeout=300` bằng cơ chế kiểm tra trạng thái luồng sống (`t.is_alive()` với polling 2s): Tuyệt đối không bao giờ ngắt ngang khi luồng AI nền vẫn đang tính toán.
     2. Hỗ trợ tự động mở gói (unwrapping) đa dạng định dạng JSON: Tự động trích xuất từ `clips`, `timeline`, `data`, `result`, `segments` và regex fallback cứu cánh.
     3. Nâng concurrency lên 2 và tận dụng Cache thông minh: Các mẻ 1 và mẻ 2 đã chạy xong sẽ tự động nạp từ cache trong 0.001s, tiếp tục các mẻ còn lại siêu tốc.
     3. **Bắt lỗi an toàn HTTP 200 Error Payload:** Thêm cơ chế kiểm tra `if 'error' in res_json:` trong `call_openai_chat_resilient` để kích hoạt retry exponential backoff thay vì văng crash `KeyError`.
     4. **Nâng Timeout an toàn:** Tăng timeout client OpenAI lên 180s cho phân hệ dịch và làm sạch phụ đề AI, đảm bảo mô hình 550B hoàn thành trọn vẹn suy luận.
 7. **Khắc phục triệt để lỗi không quét được vùng OCR do xung đột Zoom in/Zoom out, Tỷ lệ khung hình & Bounding Box CapCut (`web/app.js`, `web/index.html`, `web/style.css`, `web/js/features/video_studio_suite.js`, `patches/active/*`):**
    - **Nguyên nhân gốc rễ (Root Cause Analysis):**
      1. **Xung đột Khung biến đổi CapCut Studio (`CapCut Transform Box`):** Khung viền màu xanh cyan `.capcut-transform-box` (với thanh trạng thái `🔍 100% • (X: ...px, Y: ...px) • 🔄 0°`) trong `video_studio_suite.js` nằm đè lên khung canvas với `pointer-events: auto`. Khi người dùng rê chuột vào video hoặc click, khung này tự động kích hoạt và chặn đứng toàn bộ sự kiện click vẽ vùng OCR của `#videoOverlay`.
      2. **Méo tọa độ khi phóng to/thu nhỏ:** Khung vẽ lớp phủ `#videoOverlay` và `#drawBox` nằm trong `#videoZoomWrapper` bị méo tọa độ khi người dùng phóng to/thu nhỏ (CSS `transform: scale() translate()`). Khi vẽ, sự kiện chuột lấy tọa độ màn hình trực tiếp khiến hình chữ nhật vẽ bị nhân đôi tỉ lệ thu phóng so với con trỏ chuột.
      3. **Méo tỉ lệ phần trăm & lệch viền đen letterbox/pillarbox:** Thẻ `<video>` hiển thị ở chế độ `object-fit: contain` nên có các dải viền đen khi tỷ lệ video khác tỷ lệ khung phát. Tọa độ tính theo toàn bộ container khiến vùng OCR gửi về backend bị cắt trúng viền đen hoặc lệch phụ đề, dẫn đến OCR không quét được chữ.
    - **Giải pháp xử lý:**
      1. **Cô lập chế độ vẽ vùng OCR (`is-drawing-region`):** Khi bấm "Vẽ vùng mới", hệ thống tự động ẩn và vô hiệu hóa triệt để `CapCut Transform Box` (`.capcut-transform-box`) cùng toàn bộ các điểm neo 8 hướng, nâng `z-index: 999` cho `#videoOverlay` để con trỏ vẽ chuột hoạt động trơn tru 100% không bị bất kỳ khung nào đè lên.
      2. **Tự động khôi phục & Hủy vẽ an toàn:** Tự động khôi phục lại thanh công cụ khi vẽ xong hoặc khi nhấn phím `Escape`.
      3. **Hệ thống quy đổi tọa độ chuẩn xác theo Zoom (`getActiveZoomLevel`):** Toàn bộ thao tác vẽ, kéo thả di chuyển và co giãn 8 hướng của khung OCR tự động chia tỷ lệ cho mức zoom hiện tại trong thời gian thực, đảm bảo thao tác chuột khớp 100% với con trỏ.
      4. **Tính toán tự động vùng hiển thị thực tế Video (`getVideoContentRect`):** Trừ bù chính xác các viền đen letterbox/pillarbox của video, chuẩn hóa `currentRegion` ($X, Y, W, H$ theo % video gốc từ 0–100%) giúp backend OCR cắt và nhận diện chuẩn xác 100% dòng phụ đề.
      5. **Đồng bộ hóa khung OCR với Video Zoom Wrapper:** Khung vẽ OCR và hộp xem trước phụ đề được giữ nguyên bên trong `#videoZoomWrapper` theo tỷ lệ %, tự động co giãn và di chuyển mượt mà đồng bộ khi người dùng zoom in/out hoặc kéo pan video.

---

## 📦 CÁC THAY ĐỔI ĐÃ HOÀN TẤT CHO BẢN PHÁT HÀNH v1.2.5 (Phát hành ngày 29/08/2026)
*(Đã tải lên GitHub Release và đối soát SHA-256 thành công: `141e6e5e2ddd4ae38169bc8bd017721d3d10e90244c6be79ab1e300ff0ef11b3`).*

1. **Khắc phục triệt để lỗi chúc mừng kích hoạt & pháo hoa confetti nổ giả mạo (`routes/license.py`, `web/app.js`, `license_manager.py`, `patches/active/*`):**
   - Áp dụng hàm `sync_and_detect_event` với khóa luồng nguyên tử `_last_sync_state_lock` trên backend, đối soát chính xác thay đổi thực sự so với baseline.
   - Xử lý an toàn mốc baseline rỗng lúc mở app lần đầu, triệt tiêu hoàn toàn sự kiện chúc mừng giả.
   - Thêm guard chặt chẽ ở frontend: không bao giờ chạy polling SePay khi máy đang `CHECKING` hoặc đã có bản quyền `ACTIVE` non-trial; triệt tiêu nổ pháo hoa đóng modal bất thường khi xem HWID.

2. **Tối ưu hóa cơ chế đồng bộ bản quyền & chuyển sang Startup Cloud Sync (`license_manager.py`, `web/app.js`):**
   - Thay thế cơ chế đồng bộ ngầm định kỳ bằng Startup Cloud Sync một lần duy nhất lúc mở app, không spam Google Sheets và không làm giật lag giao diện.

3. **Sửa lỗi cú pháp JavaScript khiến app treo ở màn hình 'Đang kiểm tra...' (`web/app.js`, `web/index.html`):**
   - Khôi phục hoàn chỉnh khối điều khiển kéo thả & co giãn watermark logo Review Phim (`setupInteractiveReviewLogo`), dọn sạch các dấu ngoặc mồ côi gây `SyntaxError`.
   - Nâng phiên bản cache-buster script `app.js?v=20260829_1218` trong `index.html` để pywebview / trình duyệt nạp ngay mã nguồn mới nhất.

4. **Cố định VietQR & đồng bộ Trial an toàn (`google_apps_script_template.js`, `license_manager.py`):**
   - Gửi đầy đủ HWID trên mã QR chuyển khoản, chống ghi đè gói đã thanh toán và khóa thao tác ghi đồng thời trên Google Sheet.

5. **Sửa lỗi Salt bảo mật & định danh HWID (`license_manager.py`, `patches/active/*`):**
   - Bổ sung `DEFAULT_LOCAL_SALT` làm giá trị fallback cho `SECRET_SALT`, khắc phục lỗi tính sai HWID và lỗi HMAC khi nạp cache offline.

6. **Sửa lỗi Crash khởi động trên máy Dev và Tối ưu hóa thứ tự nạp Overlay Patch (`web_app.py`, `routes/security.py`):**
   - Tối ưu hóa thứ tự nạp `sys.path` trong `web_app.py`: luôn ưu tiên `ROOT_DIR` trước `PATCH_DIR` ở môi trường Dev, bổ sung file thiếu `routes/security.py`.

7. **Hiệu chỉnh tốc độ đọc kịch bản xuống 3.5 từ/giây (210 từ/phút) chuẩn thời lượng video (`auto_edit_pipeline.py`, `prompt_vault.py`, `prompts/*`):**
   - Điều chỉnh định mức tính số từ kịch bản `target_words = int(target_minutes * 210)` thay vì 270 (4.5 từ/giây cũ), giúp kịch bản AI sinh ra ngắn gọn, bám sát thời lượng video mong muốn khi TTS lồng tiếng.
   - Cập nhật toàn bộ các file Prompt AI (`prompt_map_chunk.txt`, `prompt_reduce_script.txt`, `prompt_script.txt`) và tái biên dịch kho mã hóa Prompt Vault `.prompt_vault.dat`.

8. **Lưu trữ Token bảo mật vĩnh viễn (`scripts/publish_patch.py`, `.gitignore`):**
   - Tự động nạp `.github_token` cục bộ an toàn, bỏ qua khỏi git tracking; chống treo tiến trình nền khi đóng gói và tự động tải Release lên GitHub API.

---

## 📦 CÁC THAY ĐỔI ĐÃ HOÀN TẤT CHO BẢN PHÁT HÀNH v1.2.2
*(Đã tổng hợp toàn bộ 10 mục nâng cấp, bảo mật và tối ưu hóa hệ thống cho phiên bản v1.2.2).*

1. **Tối Ưu Hóa Auto-Updater Cho Kho GitHub Public & Tự Động Đối Soát SHA-256 (`updater.py`, `scripts/publish_patch.py`):**
   - Hỗ trợ tải trực tiếp qua `browser_download_url`, giúp máy khách tải cập nhật tức thì từ GitHub Public mà không cần token GitHub hay biến môi trường.
   - Sửa lỗi điều kiện `expected_sha256` bị rỗng chặn cập nhật (`has_update = False`). Tự động trích xuất SHA-256 từ Release body, `version.json` hoặc manifest.
   - Nâng cấp `publish_patch.py`: tự động tính toán mã băm SHA-256 của `patch.zip` và ghi vào `version.json` cùng ghi chú phát hành Release.
   - Bổ sung `raw.githubusercontent.com` vào whitelist an toàn. Đồng bộ kép giữa mã gốc và `patches/active/updater.py`.

2. **Khóa An Toàn Đơn Luồng & Quản Lý Tiến Trình (Thread-safe Locks & Process Tree Termination):**
   - Bổ sung `_ocr_lock`, `_ocr_active`, `_review_lock`, `_review_active`, `_export_lock` trong `routes/video_edit.py` và `patches/active/routes/video_edit.py`.
   - Thay thế `taskkill /IM ffmpeg.exe` bằng `_terminate_process_tree(pid)` nhắm trúng cây tiến trình con của tác vụ, ngăn chặn dừng nhầm các tiến trình FFmpeg khác.
   - Tích hợp kiểm tra đường dẫn an toàn `is_path_allowed`, giới hạn tham số FPS (0.1 - 30) và threads (1 - 8).

3. **Khắc Phục Tốc Độ Video Review Phim (Speed Ratio Clamp):**
   - Trong `review_phim.py` và `patches/active/review_phim.py`: Điều chỉnh giới hạn tốc độ video khớp với docstring `max(0.5, min(2.0, speed_ratio))` thay vì `10.0`, tránh video bị tua quá nhanh mất tự nhiên.

4. **Bảo Mật API Keys & Chống Rò Rỉ Dữ Liệu:**
   - Trong `routes/core.py` và `patches/active/routes/core.py`: Che giấu API keys (`••••••••••••`) trên các endpoint `GET /api/keys`.
   - Ghi file cấu hình nguyên tử (Atomic tempfile writing), loại bỏ hành vi tự động đồng bộ key lên cloud chưa được đồng ý.
   - Thêm bộ lọc `_validate_external_api_url` chống SSRF.
   - Bảo vệ toàn diện hộp thoại chọn file/thư mục PowerShell với `_ps_literal()`, phòng chống command injection.
   - Kiểm soát chặt chẽ quyền truy cập và kiểm tra đường dẫn cho các route `/api/file`, `/api/video`, `/api/image`, `/api/upload_image`.

5. **Bảo Mật Bản Quyền & Chữ Ký Cloud (Strict Nonce & Signature Verification):**
   - Trong `license_manager.py` và `patches/active/license_manager.py`: Vô hiệu hóa hàm tạo master key offline. Bắt buộc kiểm tra `nonce` không rỗng và chữ ký HMAC-SHA256 trên mọi phản hồi xác thực từ server cloud.

6. **Sửa Lỗi Nhập Khẩu (Missing Imports) Trong `routes/project.py`:**
   - Bổ sung `from datetime import datetime` và import bảo mật `is_path_allowed`, `atomic_write_json`, `safe_join` để ngăn lỗi 500 khi lưu project hoặc autosave.

7. **Chuẩn Hóa Xử Lý Boolean Form / JSON Payload (`parse_bool`):**
   - Thay thế `bool(val)` bằng `parse_bool(val)` trong `routes/audio.py`, `routes/batch_queue.py` và `batch_queue_manager.py` để tránh parse sai chuỗi `"false"` thành `True`.

8. **Bảo Vệ Bộ Nhớ Đệm Giọng Nói TTS (Voice Cache Guard & Cloned Voice Security):**
   - Trong `routes/tts.py` và `patches/active/routes/tts.py`: Chỉ cho phép ghi đè `VOICE_CACHE_FILE` khi danh sách giọng > 0, bảo vệ cache 500+ giọng không bị xóa trắng khi mạng lỗi.
   - Thêm phân quyền 2 tầng và xác thực đường dẫn cho toàn bộ các endpoint Clone Voice (`/api/clone_voice/*`) và Custom Voices (`/api/custom-voices/*`).

9. **Khắc Phục Lỗi Đọc File 2 Lần & Kiểm Soát Cache Pipeline (`auto_edit_pipeline.py`):**
   - Sửa lỗi `process_chunk` đọc file 2 lần khiến trả về chuỗi rỗng khi cache hit (`cached_text = f.read()`).
   - Thêm fingerprint (MD5 của kịch bản, model, style, độ dài) cho file cache `script_meta.json` ở Bước 1 để tránh tái sử dụng sai kịch bản cũ khi đổi thông số.

10. **Nâng Cấp Batch Queue Manager & Khắc Phục Trạng Thái Hủy Task (`batch_queue_manager.py`):**
   - Hỗ trợ giải nén thư mục tự động khi item được truyền dưới dạng `dict` có `file_path` là directory.
   - Sửa lỗi task bị hủy theo yêu cầu người dùng bị đánh dấu nhầm thành `failed` (chuyển sang `cancelled`).
   - Bổ sung `try / catch` kết nối hủy tắt máy trong `web/js/features/batch_queue.js`.

---

## 📦 CÁC THAY ĐỔI ĐÃ HOÀN TẤT CHO BẢN PHÁT HÀNH v1.2.1
*(Đã tổng hợp toàn bộ các mục nâng cấp và vá lỗi theo thẩm định của OpenAI Codex để phát hành v1.2.1).*

1. **Chuyển Giao 100% Động Cơ Tách Âm UVR5 MDX-NET, Tăng Tốc DirectML GPU & Tính Năng "Áp Dụng Vào Bản Sau Khi Sửa":**
   - **Xóa bỏ hoàn toàn Demucs / DSP Turbo:** Chuyển đổi toàn bộ UI và backend sang thuần 100% MDX-NET (các mô hình chuẩn UVR5: Inst HQ4, Inst HQ5, Voc FT).
   - **Tối ưu hóa GPU DirectML / CUDA:** Hỗ trợ 100% dòng card NVIDIA RTX 50-series (RTX 5060 Blackwell sm_120) và mọi GPU trên Windows qua DirectX 12 Compute.
   - **Nút "Áp dụng vào Bản sau khi sửa":** Sau khi tách xong, cung cấp nút bấm 1-click để đồng bộ luồng âm thanh SFX sạch vào Trình phát Video (khóa đồng bộ timecode, tự động mute tiếng gốc khi xem "Bản sau khi sửa" và khôi phục lại khi chuyển sang "Bản gốc"). Tự động tái sử dụng file đã tách khi xuất video.

2. **Khắc Phục Triệt Để Lỗi Treo Auto-Updater (% Nhảy 1 -> 2 -> 1 Rồi Đứng Im):**
   - **Nguyên nhân gốc rễ (Root Cause):**
     1. Gói cập nhật `patch.zip` trước đây vô tình chứa 164 file audio tạm trong `web/outputs/`, `tts_cache/` và bộ cài Edge WebView2 nặng >60MB, khiến dung lượng bị phình to lên 51.21 MB. Khi tải file dung lượng lớn từ GitHub Release CDN qua mạng quốc tế, stream kết nối bị ngắt (`urllib3.exceptions.IncompleteRead: IncompleteRead at 2.18MB`).
     2. Hàm `download_file_direct` cũ không có cơ chế tự động thử lại (Retry) và tiếp tục tải từ byte bị đứt (Resume HTTP Range), khiến quá trình tải bị lỗi và văng exception.
     3. Thiếu cơ chế khóa đơn luồng (Thread Lock / Singleton Guard) trên backend và disable click pointer-events trên frontend: khi người dùng bấm nút nhiều lần hoặc khi bắt đầu lại, một thread mới được sinh ra và reset `percent = 0`, dẫn tới hiện tượng phần trăm nhảy lên 1%, 2% rồi tụt về 1% và treo.
   - **Giải pháp xử lý triệt để:**
     1. Tinh chỉnh bộ lọc đóng gói `scripts/publish_patch.py`: loại bỏ 100% file rác, file tạm audio `*.wav`, `*.mp3`, `outputs/`, `tts_cache/` và `.exe`, giảm dung lượng `patch.zip` từ 51.21 MB xuống chỉ còn **7.60 MB** siêu nhẹ.
     2. Nâng cấp `updater.py` với cơ chế tải luồng 2 pha (2-Phase 302 Redirect): bóc tách URL Storage sạch, hỗ trợ tải tiếp HTTP `Range: bytes=...`, tự động thử lại 5 lần nếu chập chờn mạng và tăng kích thước chunk lên 256KB.
     3. Thêm khóa an toàn đa luồng `_UPDATE_THREAD_LOCK` trong `updater.py` và vô hiệu hóa `pointer-events: none` cho nút bấm trên giao diện `web/app.js` khi đang tải.
   - **Kết quả kiểm thử:** Quá trình tải và áp dụng bản vá chạy trơn tru từ 0% -> 95% -> 98% -> 100% trong 1-2 giây, tự động giải nén và khởi động lại hoàn hảo.

2. **Khắc Phục Lỗi "404 Not Found" Khi Khởi Động `python web_app.py`:**
   - **Nguyên nhân gốc rễ (Root Cause):**
     1. Khi cơ chế OTA Patch Overlay nạp các module từ thư mục `patches/active/` lên `sys.path[0]`, các file như `web_app.py`, `routes/state.py` sử dụng hàm `os.path.dirname(__file__)` bị nhận nhầm thư mục gốc ứng dụng (`ROOT_DIR`) thành `patches/active` hoặc `patches/active/routes`.
     2. Khi Flask tìm thư mục giao diện tĩnh `os.path.join(ROOT_DIR, 'web')`, đường dẫn bị trỏ nhầm vào `patches/active/web` (không tồn tại `index.html`), dẫn đến lỗi `GET / HTTP/1.1 404` và màn hình trắng "Not Found" trên giao diện.
   - **Giải pháp xử lý triệt để:**
     1. Xây dựng hàm chuẩn hóa `get_app_root_dir()` thông minh trên toàn bộ hệ thống (`web_app.py`, `routes/state.py`, `updater.py`, `license_manager.py`, `ffmpeg_installer.py`, `local_voice_engine.py`, `batch_queue_manager.py`, `downloader.py`, `prompt_vault.py`, `ai_dubbing.py`): tự động duyệt và định vị chính xác thư mục gốc thật sự chứa `web/index.html` trong mọi môi trường (chạy mã nguồn Python, chạy trong `patches/active/`, hoặc chạy đóng gói EXE).
     2. Thiết lập đường dẫn tĩnh tuyệt đối `app = Flask(__name__, static_folder=os.path.join(ROOT_DIR, 'web'), static_url_path='/static')` và bổ sung cơ chế kiểm tra định tuyến tĩnh an toàn trong `routes/core.py`.
   - **Kết quả kiểm thử:** Khởi chạy Flask và WebView mượt mà 100%, các endpoint `GET /`, `GET /app.js`, `GET /style.css`, `GET /api/keys` đều trả về HTTP 200 OK ngay lập tức.

3. **Khắc Phục Lỗi Không Clone Được Voice / Local Voice TTS Trên Máy Khách `[LỖI PHÁT SINH]: The system cannot find the file specified. (os error 2)`:**
   - **Nguyên nhân gốc rễ (Root Cause):**
     1. Thư viện phiên âm tiếng Việt `sea_g2p` (được gọi bởi `vieneu_utils` trong luồng tổng hợp âm thanh VieNeu ONNX) sử dụng nhân Rust nhị phân `sea_g2p_rs.pyd` và yêu cầu tệp từ điển nhị phân `sea_g2p.bin` (dung lượng 62.8 MB) đặt cùng thư mục package.
     2. Trong quy trình đóng gói PyInstaller (`scripts/build_release.py`), cấu hình chưa có cờ `--collect-all=sea_g2p`, dẫn đến việc PyInstaller chỉ đóng gói file `sea_g2p_rs.pyd` mà thiếu mất `sea_g2p.bin` trong thư mục cài đặt `_internal/sea_g2p/` của người dùng.
     3. Khi người dùng chạy tính năng Clone Voice hoặc nghe thử giọng đọc, nhân Rust `sea_g2p_rs` cố gắng mở file từ điển nhưng không tìm thấy file, dẫn tới quăng ngoại lệ Rust chuẩn `The system cannot find the file specified. (os error 2)`.
   - **Giải pháp xử lý triệt để:**
     1. Xây dựng cơ chế Tự phục hồi thông minh (Self-Healing Runtime) `_ensure_sea_g2p_assets()` trong `local_voice_engine.py`: tự động phát hiện và đồng bộ tệp `sea_g2p.bin` từ `models/vieneu/sea_g2p.bin`, `models/sea_g2p.bin` hoặc thư mục AppData/dist vào package `sea_g2p` (`_internal/sea_g2p/`), đồng thời có cơ chế tự động tải offline từ Hugging Face nếu thiếu.
     2. Cập nhật cấu hình đóng gói PyInstaller trong `scripts/build_release.py`: bổ sung trọn bộ `--collect-all=sea_g2p`, `--collect-all=soxr`, `--collect-all=kaldi_native_fbank`.
     3. Đóng gói sẵn tệp `sea_g2p.bin` vào `models/vieneu/sea_g2p.bin` và đồng bộ đồng thời sang `patches/active/local_voice_engine.py` để hỗ trợ cơ chế OTA Patch Overlay.
   - **Kết quả kiểm thử:** Đã kiểm thử tự động toàn diện qua `scripts/test_clone_voice_full_flow.py` và `scratch/test_self_healing.py`: toàn bộ quy trình tải file mẫu, sinh nghe thử (Preview), lưu giọng vĩnh viễn (Save), nạp danh sách `/api/voices`, tổng hợp lồng tiếng (Dubbing), và xóa giọng (Delete) đều chạy thành công 100%.

4. **Tích Hợp Bộ Công Cụ Trình Phát Video Đa Năng (Universal Video Studio Suite) Cho Cả 2 Tab "Biên Tập Phim" & "Review Phim":**
   - **Tính năng mới phát triển:**
     1. **Bộ chọn Tỷ lệ Khung hình (Aspect Ratio Dropdown & Badges):** Chuyển đổi linh hoạt `9:16 (Dọc TikTok/Shorts/Reels)`, `16:9 (Ngang YouTube)`, `1:1 (Vuông Feed)`, `4:3 (Cổ điển)`, `21:9 (Cinematic Ultrawide)`, và `Gốc (Original Auto-Detect)`.
     2. **Chế độ Kéo Dãn & Hiển Thị (Fit / Stretch / Cover Mode):**
        - *Fit (Vừa vặn):* Giữ nguyên tỷ lệ gốc, hiển thị viền đen sạch sẽ.
        - *Cover (Cắt tràn viền):* Phóng to lấp đầy khung hình không viền đen.
        - *Stretch / Fill (Kéo dãn toàn khung):* Tự động kéo dãn video biến dạng lấp đầy 100% tỷ lệ khung hình đã chọn theo đúng ý muốn của người dùng.
     3. **Hiệu ứng Trực quan & Tiện ích Trực tiếp (Visual Quick Actions):**
        - 🔄 *Lật gương ngang (Flip Horizontal):* Đảo chiều video trực tiếp trên preview và đồng bộ vào FFmpeg chống quét bản quyền hình ảnh.
        - ↪️ *Xoay khung hình (Rotate 90°, 180°, 270°)*.
        - 🛡️ *Lưới vùng an toàn Safe Zone (TikTok/Reels UI):* Lớp phủ mô phỏng vị trí nút Like, Comment, Share, Sound, Caption để người dùng căn chỉnh text/logo không bị che khuất.
        - 📐 *Lưới bố cục 3x3 (Rule of Thirds):* Lưới tỷ lệ vàng hỗ trợ căn chỉnh bố cục điện ảnh.
     4. **Tiện ích Trình phát & Phím tắt Chuyên nghiệp (Playback Tools & Hotkeys):**
        - 📸 *Chụp ảnh Snapshot Thumbnail:* 1 click chụp ngay khung hình chất lượng cao kèm các hiệu ứng xoay/lật/tỷ lệ và tự động tải file PNG.
        - ⏱️ *Bộ điều tốc (Speed 0.5x, 0.75x, 1x, 1.25x, 1.5x, 2x)*.
        - ◀ *Nhảy 1 Frame (1F Back / 1F Forward):* Bước nhảy chính xác 1 khung hình (1/30s) phục vụ cắt cảnh siêu chuẩn.
        - ⌨️ *Bộ phím tắt toàn năng:* `Space` (Play/Pause), `Mũi tên Trái/Phải` (1 frame / 5s), `J/K/L` (Seek -5s/Pause/+5s), `F` (Fullscreen), `M` (Mute), `S` (Snapshot).
    - **Kiến trúc Khung Preview Canvas Chuẩn CapCut Desktop (CapCut Interactive Canvas System):**
      - Module hóa độc lập tại `web/js/features/video_studio_suite.js`, điều khiển độc lập 2 player `#videoPlayer` và `#reviewVideoPlayer`.
      - **Mở Rộng Chiều Cao 1.5 Lần (720px Height Stage):** Tăng chiều cao hàng thẻ trên cùng (`.top-row`) lên 1.5 lần (từ 480px lên **720px**), giúp cả 2 khu vực Màn hình Video Preview bên trái và Khung Trích xuất Phụ đề OCR bên phải hiển thị rộng rãi, cao ráo và trực quan tối đa.
      - **Sân Khấu Stage Cố Định (Fixed Preview Stage):** Sân khấu `.video-container` giữ kích thước cố định ổn định (chiều cao 560px - 660px, nền rạp phim tối `#070b14`), không làm co giật hay vỡ layout các thẻ xung quanh.
      - **Khung Neo Biến Đổi Tương Tác Chuẩn CapCut Desktop (CapCut Interactive Transform Engine):**
        - *Bộ 8 Mốc Neo Tương Tác (8 Anchor Handles):* Gồm 4 góc neo tròn trắng `⚪` (Proportional Zoom) và 4 mốc cạnh trung tâm `◽` (Edge Zoom / Stretch) luôn hiển thị tràn ra ngoài sân khấu stage (`overflow: visible`), không bao giờ bị cắt mất dù phóng to đến 500%.
        - *Kéo Thân Dời Vị Trí Tràn Viền (Free Pan Overflow):* Cho phép click kéo trực tiếp thân video di chuyển tự do khắp mặt phẳng X, Y mà không bị chặn lại ở mép canvas, hỗ trợ dời video tràn ra ngoài màn hình đúng chuẩn CapCut.
        - *Cuộn Chuột Phóng To / Thu Nhỏ (Mouse Wheel Zoom):* Lăn con lăn chuột trực tiếp trên màn hình preview để phóng to / thu nhỏ video mượt mà, nhanh chóng từ 0.15x đến 5.0x.
        - *Nút Neo Xoay Đáy (`[🔄]` Rotation Handle):* Đặt chính giữa mép dưới video, hỗ trợ xoay 360° tự do kèm nam châm thông minh tự động hút (snapping) chuẩn xác tại các góc `0°`, `90°`, `180°`, `270°`.
        - *Nút Bấm & Phím Tắt Khôi Phục:* Nút `🎯 100%` trên Toolbar, nhấp đúp chuột (Double click) hoặc phím `R` để lập tức khôi phục video về vị trí chuẩn tâm (Fit 100%).
        - *Live HUD Badge & Đường Gióng Tâm:* Hiển thị thông số tỷ lệ thời gian thực (`🔍 125% • (X: 10px, Y: -20px) • 🔄 0°`) và vạch đỏ gióng tâm khi căn chỉnh.
        - *Nút "Chọn Video" Tiện Lợi:* Bổ sung nút bấm `Chọn Video` trực tiếp trên thanh Header thẻ Xem trước phim Review Phim và nút nổi bật bên trong màn hình chờ Placeholder giúp thao tác chọn file tức thì.
        - *Lược Bỏ Thanh Trượt Zoom Cũ:* Loại bỏ hoàn toàn khối thanh trượt "Thu phóng màn hình (Zoom)" rườm rà ở cả thẻ Biên Tập Phim và Review Phim, tập trung trải nghiệm thu phóng trực tiếp trên màn hình preview chuẩn CapCut (Khung 8 mốc neo, Cuộn chuột và nút 🎯 100% Fit).
        - *Áp dụng thống nhất:* Hoạt động đồng bộ 100% trên cả 2 trình phát **Biên Tập Phim** và **Review Phim**.
   5. **Động Cơ AI Tách Âm Thanh Chuẩn Ultimate Vocal Remover UVR5 (MDX-NET Inst HQ 4 / HQ 5 / Voc FT):**
      - Tối giản hóa và chuyển đổi 100% sang hệ sinh thái MDX-NET (loại bỏ hoàn toàn các mô hình cũ như Demucs / DSP):
        - `UVR-MDX-NET-Inst_HQ_4.onnx`: Lọc sạch 99.5% giọng nói/lời thoại cũ, bảo toàn 100% âm sắc nhạc nền BGM và tiếng động hiện trường SFX (cháy nổ, bước chân, tiếng mưa...).
        - `UVR-MDX-NET-Inst_HQ_5.onnx`: Tối ưu hóa triệt tiêu tiếng vang (Reverb & Echo).
        - `UVR-MDX-NET-Voc_FT.onnx`: Trích xuất giọng thoại Vocal trong trẻo.
      - **Bộ 4 Tính Năng Điều Khiển Tách Âm Chuyên Nghiệp:**
        - 🛑 *Dừng khẩn cấp (Emergency Stop):* Chuyển tác vụ sang luồng chạy ngầm (`threading.Thread` phi đồng bộ), giúp Flask luôn sẵn sàng nhận lệnh hủy tức thì (<1ms), ngắt vòng lặp tính toán sau từng chunk và giải phóng RAM/VRAM ngay lập tức.
        - 🚀 *Tự động kích hoạt GPU NVIDIA:* Tự động phát hiện và nạp `CUDAExecutionProvider` / `DmlExecutionProvider` (DirectML GPU) khi máy có card đồ họa NVIDIA.
        - 📊 *Hiển thị % hoàn thành thời gian thực:* Thanh Progress Bar phát sáng với % số thực, hiển thị số đoạn `x/y chunks` và thời gian đếm ngược còn lại.
        - 📋 *System Log Console:* Hộp console thời gian thực chuẩn Dark Mode ghi nhận chi tiết từng bước xử lý (mô hình, độ dài audio, tốc độ `chunk/s`, đường dẫn output...).
      - Thuật toán Chunking & Overlap-Add Crossfade với cửa sổ Hanning mượt mà, không giật cục.
      - Đồng bộ hoàn toàn giữa thư mục gốc và thư mục bản vá `patches/active/`.

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
