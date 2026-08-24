# 📋 DANH SÁCH VIỆC CẦN LÀM & ĐỀ XUẤT PHÁT TRIỂN (TODO & ROADMAP)

> **Quy tắc quản lý:**
> - Mỗi khi hoàn thành xong một công việc nào trong danh sách này, tôi sẽ **tự động cập nhật / đánh dấu hoàn thành**.
> - Mỗi lần bạn hỏi "cho tôi xem todo" hoặc "còn việc gì cần làm?", tôi sẽ đọc file này để báo cáo chính xác tiến độ hiện tại.
> - **Quy tắc phát hành bản vá:** CHỈ phát hành bản cập nhật mới (tạo GitHub Release / patch.zip) khi bạn yêu cầu. Tuyệt đối không tự động phát hành. Khi phát hành theo lệnh của bạn, phiên bản sẽ tự động tăng tiến +1 (vd: v1.0.7 -> v1.0.8...).

---

## 📦 CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH (CHO BẢN TIẾP THEO v1.0.9)
*(Mỗi khi bạn báo lỗi hoặc yêu cầu tính năng mới và tôi sửa xong, tôi sẽ tự động ghi chi tiết vào đây để chuẩn bị cho lần phát hành tiếp theo).*

---

## 🚀 LỊCH SỬ CÁC PHIÊN BẢN ĐÃ PHÁT HÀNH

### ✅ Phiên bản v1.0.8 (Đã phát hành ngày 24/08/2026):
1. **Kiến trúc Map-Reduce Bước 1 (Lên kịch bản):** Xử lý file SRT dài không giới hạn, chống timeout 120s bằng cách chia chunk an toàn.
2. **Kiến trúc Map-Reduce Bước 3 (Phân tích cảnh):** Chia mẻ 35 câu/lần, xử lý bất đồng bộ, Batch Caching độc lập chống mất dữ liệu và khắc phục triệt để lỗi timeline rỗng.
3. **Đa luồng TTS (TTS Multi-threading):** Tùy chỉnh 1 - 10 luồng trong Card 3, tăng tốc tạo giọng đọc x3 - x5 lần.
4. **Phóng to Video (Video Zoom & Crop):** Tùy chỉnh 100% - 150% kèm preset chống bản quyền và bộ lọc Center-Crop FFmpeg.
5. **Hiển thị % tiến trình từng bước:** Sửa log console hiển thị chính xác % thực tế của từng tác vụ.
6. **Tự động cài đặt dependencies:** Tự động chạy `pip install -r requirements.txt` khi updater nâng cấp app trên máy khách.

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
