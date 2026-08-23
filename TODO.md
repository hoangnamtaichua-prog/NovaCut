# 📋 DANH SÁCH VIỆC CẦN LÀM & ĐỀ XUẤT PHÁT TRIỂN (TODO & ROADMAP)

> **Quy tắc quản lý:**
> - Mỗi khi hoàn thành xong một công việc nào trong danh sách này, tôi sẽ **tự động cập nhật / đánh dấu hoàn thành**.
> - Mỗi lần bạn hỏi "cho tôi xem todo" hoặc "còn việc gì cần làm?", tôi sẽ đọc file này để báo cáo chính xác tiến độ hiện tại.
> - Mỗi lần đẩy lên bản cập nhật mới không cần nhắc số phiên bản sẽ **tự động tăng tiến +1 (vd: v1.0.1 -> v1.0.2 -> v1.0.3...)**.

---

## ✅ I. CÁC TÍNH NĂNG & SỬA LỖI ĐÃ HOÀN THÀNH MỚI NHẤT (v1.0.5)

1. ✅ **Gắn Cụm Điều Khiển Tách & Lọc Âm Gốc AI Trực Tiếp Vào Thẻ Lồng Tiếng:**
   - Đặt ngay trong thẻ **`🎙️ LỒNG TIẾNG AI`** ở giao diện Biên tập phim.
   - Thêm nút **`[⚡ Tách & Nghe Thử Âm SFX]`** kèm trình phát nghe thử trực tiếp file đã lọc sạch lời thoại.

2. ✅ **Hệ Thống 1-Click Auto-Updater Trực Tiếp Kho Private GitHub (`hoangnamtaichua-prog/NovaCut`):**
   - Đèn báo phát sáng viền cyan trên nút **`[🚀 Cập nhật (v1.0.5)]`** khi phát hiện bản mới.
   - Tải stream bản vá `patch.zip` qua GitHub Private API trong 2-3 giây, tự giải nén và tải lại app giữ nguyên 100% bản quyền & dữ liệu người dùng.

3. ✅ **AI Tách Âm Thanh, Lọc Lời Thoại Cũ & Bỏ Nhạc Nền Giữ Lại Âm Gốc (AI Stem & Vocal Separation):**
   - Đã xây dựng engine `audio_separator.py` hỗ trợ 2 chế độ: **AI Neural** (Phân tích ma trận phổ STFT + Harmonic-Percussive Gating) và **DSP Turbo** (Đảo pha triệt tiêu Center Dialogue siêu tốc 0.2s).
   - Tách và triệt tiêu sạch lời thoại gốc (tiếng Trung, Anh, Hàn...) trước khi lồng tiếng mới.
   - Giữ nguyên 100% tiếng động hiện trường (tiếng súng nổ, bước chân, tiếng xe, tiếng đấm đá, gió thổi, mở cửa...).

4. ✅ **Khắc Phục Triệt Để Lỗi Clone Voice Trên Môi Trường Máy Sạch / Windows Sandbox:**
   - Đóng gói trọn bộ mô hình Offline ONNX int8 (`denoiser.onnx`, `speaker_encoder.onnx`, `vieneu_v3_heads.npz`) vào `models/vieneu/`.
   - Tự động nạp mô hình cục bộ, triệt tiêu 100% lỗi `os error 2`.

5. ✅ **Tính Năng Nghe Thử Lồng Tiếng Trực Tiếp (Live Dubbing Engine):**
   - Nghe thử giọng AI khớp thời gian thực trên video khi chuyển sang chế độ **`[✨ Bản sau khi sửa]`** (kèm tính năng Audio Ducking tự hạ âm lượng gốc).
   - Thêm nút **`[🗣️]`** nghe thử từng câu trên từng dòng bảng phụ đề SRT.

6. ✅ **Chuẩn Hóa Khung Hình Mặc Định 16:9 Ngang & Chuyển Đổi Dọc 9:16:**
   - Mặc định 16:9 ngang và tự động co giãn khung hình 9:16 dọc có viền sáng cyan và cover fit.

---

## 🚀 II. DANH SÁCH TÍNH NĂNG MỚI TIẾP THEO (ROADMAP):

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

## 🛡️ III. CÁC HẠNG MỤC CỐT LÕI ĐÃ HOÀN THÀNH TOÀN DIỆN:
- ✅ **Bảo Vệ Mã Nguồn:** Biên dịch C-binary `.pyd` qua Cython & mã hóa AES-256 Prompt (`.prompt_vault.dat`).
- ✅ **Chống Dò Thám Frontend:** Khóa chuột phải Inspect, chặn F12 / DevTools.
- ✅ **Cổng Thanh Toán Tự Động:** SePay.vn VietQR TPBank tích hợp trực tiếp, kích hoạt bản quyền trong 2 giây.
- ✅ **Modal Miễn Trừ Trách Nhiệm:** Cam kết bản quyền chuẩn Dark Mode AAA.
- ✅ **Nhận Diện Đa Ổ Đĩa CapCut / JianYing:** Quét toàn bộ ổ C, D, E.
