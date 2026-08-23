# Luồng Chức Năng Lõi (Core Feature Flows)

Tài liệu này ghi chú luồng hoạt động (Business Logic Flow) BẮT BUỘC của các chức năng lõi trong hệ thống.
**Tuyệt đối không được thay đổi các bước trong luồng này trừ khi có sự xác nhận từ User.** Mọi sửa đổi, tối ưu hoặc thêm chức năng phụ phải bám sát cấu trúc của các flow dưới đây để không gây ra lỗi lệch âm thanh, nháy hình, hoặc kẹt phụ đề.

---

## 1. Tự Động Cắt (Auto-Edit Pipeline - `auto_edit_pipeline.py`)
Luồng này dùng để tự động tạo một video review phim bằng cách bóc tách phụ đề gốc, dùng AI viết kịch bản, và cắt ghép video khớp với kịch bản đó.

**Flow Bắt Buộc:**
1. **Viết Kịch Bản:** Gửi `phụ đề gốc (SRT)` cho GPT để tạo `script` tóm tắt.
2. **Tạo Voice & Sub Tổng:** Tạo file âm thanh tổng (`voice_review.wav`) và file phụ đề tổng (`voice_review_cleaned.srt`) từ kịch bản (không chia nhỏ audio).
3. **Map Timeline:** Gửi `voice_review_cleaned.srt` và `phụ đề gốc` cho GPT để chọn các đoạn cảnh phim (start/end).
4. **Sanitize Timeline:** Dùng `timeline_sanitizer.py` dò điểm chuyển cảnh (scene cuts) và snap các điểm start/end về chuyển cảnh gần nhất để **né nháy hình**. (Tuyệt đối **không** dùng `setpts` đổi tốc độ video trong luồng này).
5. **Cắt Cảnh (Video Câm):** Dùng FFmpeg cắt các đoạn video đã snap, mute âm thanh gốc (`-an`), không chèn sub/audio ở bước này.
6. **Ghép (Concat):** Nối tất cả video câm lại thành `concat_silent.mp4`.
7. **Overlay Tổng (Bước Quan Trọng Nhất):** FFmpeg nhận `concat_silent.mp4`, ốp `voice_review.wav` và burn `voice_review_cleaned.srt` lên trên cùng một lúc. Đảm bảo đồng bộ 100%.

---

## 2. Biên Tập Phim Thủ Công (`review_phim.py`)
Luồng này cho phép User tự chèn JSON kịch bản (gồm start, end, narration) do GPT tạo ra vào phần mềm.

**Flow Bắt Buộc:**
1. **Nhận JSON:** Đọc mảng JSON chứa `[start, end, narration]` từ User.
2. **Xử lý Từng Clip:** Lặp qua từng object trong JSON:
   - Tạo TTS cho đoạn `narration` tương ứng (trả về audio_clip).
   - Tính toán tỷ lệ tốc độ: `speed_ratio = thời gian video (end - start) / thời gian audio_clip`.
   - Dùng FFmpeg cắt video từ `start` đến `end`, kèm theo bộ lọc `setpts` để nén/giãn tốc độ video khớp chính xác với audio. Chèn luôn `audio_clip` vào. (Lưu ý: Luồng này không làm sub).
3. **Ghép (Concat):** Nối các clip đã có âm thanh lại.
4. **Mix BGM & Xuất:** Chèn nhạc nền (nếu có) và xuất ra file Ngang (Youtube) + Dọc (TikTok).

---

## 3. Kể Lại Video (Narration Mode - `auto_edit_pipeline.py`)
Luồng này không cắt ghép video, chỉ viết kịch bản dựa trên độ dài video gốc và ốp âm thanh lên.

**Flow Bắt Buộc:**
1. **Viết Kịch Bản Khớp Thời Gian:** GPT nhận `SRT gốc` và `thời lượng video gốc`, viết kịch bản sao cho khi đọc với tốc độ bình thường sẽ chiếm đúng bằng độ dài video.
2. **Tạo Voice & Sub:** Tạo file audio và srt tổng.
3. **Overlay & Mix:** Lấy **NGUYÊN BẢN video gốc**, giảm âm lượng gốc xuống (`volume=0.1`), chèn âm thanh voiceover lên (`volume=1.0`), dùng mix `amix=inputs=2:duration=longest` và burn file Sub tổng.

---

## 4. Biên Tập Video & Lồng Tiếng AI (Editor & AI Dubbing Pipeline - `routes/video_edit.py`)
Luồng này cho phép chỉnh sửa video, dịch phụ đề, lồng tiếng AI đa luồng và làm mờ phụ đề gốc theo chuẩn Single-Pass.

**Flow Bắt Buộc:**
1. **Cơ Chế 2-Track Phụ Đề & Làm Mờ (2-Track Subtitle Engine):**
   - **Track 1 (Dynamic Blur):** Luôn ưu tiên lấy **Chữ gốc ban đầu** (`original_text` hoặc `text` - tiếng Trung, Hàn, Anh...) để đo đạc và làm mờ khít 100% dòng chữ thực tế trên khung hình video.
   - **Track 2 (Burn-in Subtitles):** Sử dụng **Chữ dịch mới** (`translation` - tiếng Việt) để ghi ra file phụ đề tạm `temp_subs.srt` và chèn đè lên trên vùng đã làm mờ.
   - **Tùy chọn Quét Tọa Độ Pixel AI (RapidOCR Bounding Box):** Nếu người dùng tick chọn `blur_use_ai_scan`, hệ thống sẽ kích hoạt RapidOCR AI (`scan_subtitles_pixel_boxes_generator`) để quét và lấy tọa độ pixel thực tế `[box_x_ratio, box_w_ratio]` của chữ gốc trên video. Quá trình này được yield generator log liên tục ra frontend và sẽ tự động fallback về đo đạc qua thuật toán trọng số ký tự CJK nếu có lỗi, đảm bảo luồng Dynamic Blur chạy trơn tru mà không cần cắt video ra file phụ.
2. **Tạo Giọng Lồng Tiếng AI Đa Luồng (TTS Multi-Threading):**
   - Khởi tạo `ThreadPoolExecutor` với số luồng tùy biến `max_workers` (`4 - 32` luồng, mặc định `16 - 20` luồng).
   - Kiểm tra bộ nhớ đệm âm thanh (**Audio Disk Cache MD5** tại `.cache/tts_cache/`) trước khi gọi API để tiết kiệm thời gian (0ms) và quota API.
   - Áp dụng cơ chế **Auto-Retry tối đa 3 lần** nếu gặp sự cố nghẽn mạng tạm thời.
   - Ghép nối các đoạn âm thanh thành track lồng tiếng tổng thể (`dubbed_timeline.wav`) bằng Pure Python PCM Timeline Mixer.
3. **Động Cơ Single-Pass Video Engine (FFmpeg):**
   - Tích hợp trực tiếp: `Dynamic Blur Filters` + `Video Effects (Speed, Flip, Aspect Scale, Zoom Crop)` + `Burn-in Subtitles` + `Audio Ducking/Mixing (Sidechain Compress)` vào **1 lệnh FFmpeg DUY NHẤT**.
   - Tự động kiểm tra và ưu tiên bộ mã hóa phần cứng GPU (`h264_nvenc`, `h264_qsv`) trước khi fallback về CPU (`libx264`).

---

## 5. Quy Chuẩn An Toàn Cho FFmpeg Dynamic Blur (Expression Overflow Prevention)
Bộ lọc làm mờ động theo thời gian (`enable='between(t,...)'`) có thể gây tràn bộ nhớ stack của FFmpeg (`eval.c`) khi số lượng phụ đề lớn (hàng trăm câu).

**Quy Tắc Bắt Buộc:**
1. **Giới Hạn Batch An Toàn (Chunking):** Tuyệt đối không nối chuỗi vô hạn. Giới hạn tối đa **25 điều kiện `between()`** trên mỗi tầng filter `overlay`. Tự động phân tách thành các chunk tuần tự an toàn.
2. **Gộp Khoảng Cách Ngắt (Gap Merging):** Tự động hợp nhất các câu phụ đề có khoảng cách nghỉ ngắn (`<= pad_sec + 0.15s`) thành một khối làm mờ liền mạch để chống giật nháy hình và giảm tải biểu thức.
3. **Lead & Padding Sync:** Luôn áp dụng bù thời gian sớm (`lead_sec`) và đệm giữ mờ (`pad_sec`) để khớp chuẩn từng khung hình chữ xuất hiện.

---

## 6. Quy Chuẩn Tương Tác Khung Phụ Đề & Vùng Quét (8-Way Resize System)
Hệ thống cho phép người dùng vi chỉnh kích thước và vị trí vùng phụ đề/vùng quét sau khi vẽ.

**Quy Tắc Bắt Buộc:**
1. **8 Điểm Neo Co Giãn (8-Way Handles):** Trên khung viền `.sub-preview-box` và `.ocr-draw-box` phải luôn gắn 8 điểm neo co giãn (`nw`, `n`, `ne`, `e`, `se`, `s`, `sw`, `w`) hỗ trợ con trỏ chuột tương ứng (`↔`, `↕`, `↗`, `↖`).
2. **Đồng Bộ Hai Chiều Real-Time (Two-Way Sync):**
   - Kéo chuột trên khung video -> Tự động cập nhật tức thì vào các thanh trượt (`subBoxWidth`, `subBoxHeight`, `subBoxX`, `subBoxY`).
   - Kéo thanh trượt hoặc bấm nút "Căn giữa" -> Tự động co giãn và định vị lại khung hiển thị trên video.
   - Khi cập nhật nội dung văn bản xem trước, phải bảo toàn các element `.box-resize-handle` (dùng `.sub-text-inner` thay vì ghi đè toàn bộ `innerHTML`).

---

> **LƯU Ý QUAN TRỌNG CHO AGENT:**
> - Nếu một Issue được báo cáo ở tính năng A, **hãy đối chiếu logic code hiện tại với file flow này**. 
> - Bất kỳ sự khác biệt nào giữa code và flow này đều là lỗi do tác động của agent trước (ví dụ tự ý cắt vụn audio thay vì overlay tổng, hoặc render video 2 lần thay vì Single-Pass).
> - Phải áp dụng Flow ở đây làm "Kim chỉ nam" để debug.
