# 📋 TỔNG HỢP TOÀN BỘ WORKFLOW ĐÃ THỰC HIỆN HÔM NAY
*Cập nhật: 21/08/2026*

---

## 🚀 1. Quét Tọa Độ Phụ Đề AI Khớp Khung Hình Thực Tế (Visual Frame Alignment)
- **Vấn đề**: Hardsub gốc của phim xuất hiện sớm hơn từ `0.5s – 1.5s` trước khi nhân vật cất tiếng thoại (lệch so với SRT âm thanh), gây hiện tượng hở chữ và nhấp nháy.
- **Giải pháp**:
  - Tích hợp cơ chế **Dò lùi (Seek Backward)** và **Dò tiến (Forward Seek)** trong `ocr_module.py` (`find_visual_boundaries`), tự động dò tìm thời điểm chữ thực tế bắt đầu xuất hiện (`visual_start`) và kết thúc (`visual_end`).
  - Lưu trữ `visual_start` & `visual_end` vào AI Bounding Box.
  - Tích hợp **Smart Gap Bridging**: Tự động nhận diện các khoảng trống nhỏ giữa 2 câu thoại ($\le 0.75\text{s}$) để giữ dải mờ liên tục, triệt tiêu hoàn toàn hiện tượng chớp tắt (flicker).

---

## 🎯 2. Tích Hợp Toàn Diện Dynamic Blur & Quét AI Sang Tab Review Phim
- **Giao diện & Điều khiển (`web/index.html`)**:
  - Bổ sung cụm điều khiển **✨ Tự động làm mờ phụ đề gốc (Dynamic Blur)** và **🎯 Quét tọa độ chữ AI (RapidOCR Bounding Box)** vào mục Cấu hình Review Phim.
  - Hỗ trợ nút **Quét Toàn Bộ Sub** (`btnReviewTabScanAiAllSubs`) & **Quét Frame Này** (`btnReviewTabScanAiCurrentFrame`) trực tiếp bằng GPU.
  - Bổ sung 4 thanh trượt tinh chỉnh:
    - 💧 **Độ mờ (Blur Intensity)**
    - ⚡ **Bù thời gian xuất hiện (Sync Offset)**: Mở rộng dải bù từ `-1500ms` đến `+300ms`.
    - 🛡️ **Đệm giữ mờ liên tục (Gap Padding)**: Mở rộng dải đệm từ `50ms` đến `1000ms`.
    - ↕️ **Vị trí độ cao phụ đề (Y Position)**
- **Backend & Pipeline (`auto_edit_pipeline.py`)**:
  - Sử dụng trực tiếp dữ liệu `ai_boxes` đã quét từ giao diện để xuất video FFmpeg, **không cần quét lại**, tiết kiệm 100% thời gian render.

---

## 🖼️ 3. Hệ Thống Chèn Logo / Watermark Bản Quyền (Khung Điều Hướng 8 Điểm)
- **Tương tác trực tiếp trên màn hình xem trước (`web/app.js` & `web/style.css`)**:
  - Hỗ trợ **kéo thả di chuyển (Drag to move)** toàn bộ vị trí logo.
  - Hỗ trợ **co giãn 8 hướng (8-Point Resize)** qua các nút neo `NW`, `N`, `NE`, `E`, `SE`, `S`, `SW`, `W`.
  - Tự động chuẩn hóa và lưu trữ tọa độ theo `%` (`x_pct`, `y_pct`, `w_pct`, `h_pct`) để luôn khớp trên mọi độ phân giải và tỉ lệ (9:16 dọc / 16:9 ngang).
- **Tính năng bổ trợ**:
  - Hỗ trợ chọn ảnh / tải ảnh trực tiếp / kéo thả file ảnh logo (`.png`, `.jpg`, `.jpeg`, `.webp`) vào khung player.
  - Thanh trượt **Độ mờ đục (Opacity)** từ `10%` đến `100%`.
  - 5 nút vị trí nhanh (Quick Snap): Góc trên-trái, trên-phải, dưới-trái, dưới-phải, chính giữa.

---

## 📺 4. Đưa Trình Phát Video Player & Preview Sang Tab Review Phim
- **Player trực quan đa năng**:
  - Thêm thẻ `#reviewVideoPlayerCard` tự động phát phim ngay khi chọn file.
  - Đầy đủ nút Play / Pause, thanh trượt tua Timeline, hiển thị thời lượng video (`MM:SS / MM:SS`), điều chỉnh âm lượng.
  - **Bộ chuyển đổi Preview kép**:
    - `[Bản gốc]`: Xem video gốc.
    - `[✨ Bản sau khi sửa]`: Xem trực tiếp lớp mờ Dynamic Blur và Logo Watermark.
- **Kéo thả tệp tin trực tiếp (Drag & Drop)**:
  - Thả file video (`.mp4`, `.mov`, `.mkv`, `.avi`, `.webm`) hoặc file phụ đề (`.srt`, `.vtt`, `.ass`) trực tiếp vào màn hình player để tự động nạp.
- **Tự động tạm dừng thông minh**: Tự động pause video khi người dùng chuyển sang tab khác để tránh phát âm thanh ngầm.

---

## 🔍 5. Xem Trước Trực Tiếp Vùng Mờ Phụ Đề & Nút Điều Hướng Từng Câu
- **Hiển thị trực quan khung làm mờ trên Preview**:
  - Khi bật `✨ Bản sau khi sửa`, xuất hiện khung kính mờ (Frosted-Glass) kèm viền nét đứt Cyan (`border: 1.5px dashed #38bdf8`) ôm khít chữ theo đúng toạ độ AI đã quét.
- **Nút nhảy nhanh từng câu phụ đề (`⏮️` / `⏭️`)**:
  - Nhảy chính xác tới từng câu thoại để kiểm tra độ khớp thời gian và độ che phủ.
- **Cập nhật Live tức thì khi kéo thanh trượt (Zero-Delay Live Sync)**:
  - Kéo thanh trượt Sync Offset, Gap Padding, Blur Intensity, Y Position sẽ cập nhật kích thước/vị trí khung mờ trên màn hình ngay lập tức ngay cả khi video đang tạm dừng.

---

## 🖥️ 6. Tính Năng Toàn Màn Hình (Fullscreen Video Player)
- Bổ sung nút **`⛶` / `🗗`** trên thanh điều khiển của cả **Studio Review Phim** và **Biên tập phim**.
- Hỗ trợ **nháy đúp chuột (`Double-Click`)** trực tiếp vào màn hình video để bật/tắt toàn màn hình.
- Tự động co giãn 100vw x 100vh giữ nguyên tỉ lệ khung hình (Aspect Ratio) với nền đen điện ảnh và giữ chuẩn vị trí khung mờ/logo.

---

## 🛑 7. Nút Dừng Khẩn Cấp Khi Dịch Phụ Đề & Làm Sạch SRT Bằng AI
- **Nút Dừng Dịch Phụ Đề (`#btnStopTranslate`)**:
  - Tự động xuất hiện nút đỏ `⏹️ Dừng dịch` khi đang chạy dịch hàng loạt câu (hỗ trợ cả **Google Dịch** và **AI GPT**).
  - Tích hợp `AbortController` ngắt ngay lập tức kết nối API mạng đang chờ.
  - **Bảo toàn dữ liệu 100%**: Lưu giữ toàn bộ các câu phụ đề đã dịch thành công trước đó vào bảng Editor mà không bị mất dữ liệu.
- **Nút Dừng Làm Sạch SRT AI (`#btnStopCleanSrtAI`)**:
  - Tự động xuất hiện nút đỏ `⏹️ Dừng AI` khi GPT đang gộp và làm sạch các đoạn phụ đề vụn.
  - Tự động ghép nối các đoạn đã gộp với các câu gốc chưa xử lý còn lại, đánh lại ID chuẩn xác và hiển thị ngay lên bảng Editor.

---

## 👑 8. Hệ Thống Bản Quyền, HWID & Thanh Toán SePay VietQR Tự Động
- **Xác thực Mã máy phần cứng duy nhất (HWID)**:
  - Tự động sinh mã máy định dạng `AMS-XXXX-XXXX-XXXX` từ thông số bo mạch chủ và CPU, đảm bảo 1 bản quyền gắn liền 1 máy tính duy nhất.
- **Bảo mật mã hóa HMAC-SHA256**:
  - Chứng chỉ bản quyền offline được mã hóa chống can thiệp trong file `.license.dat`.
- **Phân quyền 4 Gói cước (Trial / Pro / VIP / 1 Năm)**:
  - Tự động kích hoạt 24h dùng thử cho máy mới; mở khóa quyền lợi tùy theo từng gói.
- **Tự động kích hoạt VietQR SePay**:
  - Hiển thị QR thanh toán chuẩn Napas 247; hệ thống tự động nhận Webhook từ SePay và mở gói VIP sau 3-5 giây.
- **Google Sheets Cloud Backend**:
  - Cung cấp sẵn mã nguồn `google_apps_script_template.js` sẵn sàng triển khai quản lý toàn bộ khách hàng trên Google Sheets.

---

## 🛠️ 9. Các Lỗi Quan Trọng Đã Được Khắc Phục (Bug Fixes)

| # | Hiện tượng lỗi | Nguyên nhân | Giải pháp |
|---|---|---|---|
| 1 | **Ảnh logo preview bị hỏng (icon lỗi ảnh)** | Đường dẫn file local không được trình duyệt cấp phép truy cập trực tiếp | Tích hợp Data URL FileReader + Endpoint `/api/upload_image` & `/api/image` |
| 2 | **Lỗi khi quét tọa độ chữ bên Review Phim** | Hàm `_parse_srt_tolerant` trong `routes/subtitles.py` bị thiếu và lỗi mã hóa encoding | Khôi phục bộ phân tích tolerant hỗ trợ đa bảng mã (`utf-8`, `utf-8-sig`, `gbk`, `gb18030`, `utf-16`) |
| 3 | **Toàn bộ nút bấm bị khóa cứng (Click Lock)** | Biến module TDZ (`ReferenceError`) và biến `let` trùng lặp ở module scope | Đưa `<script type="module">` về cuối body, đóng gói biến `startX, startY` bên trong hàm |
| 4 | **Video Player không nhận thời gian (`00:00 / 00:00`)** | Thiếu hàm `formatVideoTime(seconds)` trong app.js | Bổ sung hàm định dạng chuẩn và bắt toàn bộ sự kiện `loadedmetadata`, `durationchange`, `canplay`, `timeupdate` |
| 5 | **`🛑 Không thể đo thời lượng video.` khi xuất video kể chuyện** | Hệ thống gọi lệnh `ffprobe.exe` trong khi thư mục `bin/` chỉ có `ffmpeg.exe` | Nâng cấp cơ chế đo thời lượng 3 lớp dự phòng (`ffprobe` $\rightarrow$ `ffmpeg.exe -i` $\rightarrow$ OpenCV `cv2.VideoCapture`) |
| 6 | **`[AVFilterGraph] Error initializing filters: Invalid argument` khi render video** | Cú pháp `scale=w='main_w*...':h='main_h*...'` bị FFmpeg từ chối vì `main_w` chỉ thuộc `scale2ref`/`overlay`, cùng với việc lặp `-i audio` | Chuẩn hóa toàn bộ filter logo sang `[logo_alpha][v_ref]scale2ref=...`, xóa input audio trùng và kiểm tra kênh audio video gốc |

---

## 🧪 10. Kiểm Thử Hệ Thống (Verification Results)
- ✅ `scripts/test_license_manager.py` $\rightarrow$ **PASS 100% (HWID, VietQR, Master Key, Tamper Resistance, Flask Endpoints)**
- ✅ `scripts/test_visual_frame_alignment.py` $\rightarrow$ **PASS 100%**
- ✅ `scripts/test_logo_overlay_export.py` $\rightarrow$ **PASS 100%**
- ✅ `node -c web/app.js` $\rightarrow$ **PASS (Cú pháp JS chuẩn)**
- ✅ `python -m py_compile license_manager.py routes/license.py web_app.py` $\rightarrow$ **PASS 100%**
- ✅ `python -m py_compile routes/core.py routes/subtitles.py routes/video_edit.py auto_edit_pipeline.py` $\rightarrow$ **PASS 100%**
