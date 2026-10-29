# -*- coding: utf-8 -*-
import os
import sys

# Ensure utf-8 output
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

changelog = """✨ Bản Cập Nhật NovaCut v1.3.7 (Hoàn Toàn Miễn Phí Vĩnh Viễn & Nâng Cấp Toàn Diện Biên Tập Phim, Dynamic Blur, TTS Studio):

1. 💎 Mở Khóa Miễn Phí Vĩnh Viễn 100% (100% Free Lifetime All Features):
- Gỡ bỏ hoàn toàn mọi rào cản bản quyền, hệ thống kiểm tra và thanh toán VietQR / SePay MBBank.
- Kích hoạt toàn bộ tính năng cao cấp không giới hạn: Biên tập phim, Review Phim AI, Dubbing TTS, Clone Voice Studio, Hồng Quả Video Downloader, Tách âm AI...

2. 🎬 Khắc Phục Triệt Để Lỗi Dynamic Blur & Căn Tâm Phụ Đề Mới (Biên Tập Hàng Loạt):
- Tự động nạp tọa độ bounding box pixel RapidOCR (ai_blur_boxes.json) khi xuất hàng loạt.
- Tích hợp cơ chế AI Auto-Pin tự động tính toán tâm dọc và ghim dải làm mờ cùng phụ đề mới trùng khít 100% với phụ đề gốc ở đáy video.
- Gỡ bỏ giới hạn chiều cao 7.5%, bổ sung vùng đệm an toàn padding (12px) che phủ trọn vẹn nét chữ và viền stroke.
- Bổ sung 2 thanh trượt trực quan Vị trí dọc (Y) và Chiều cao mờ (H) ngay trong tab Biên tập hàng loạt.

3. ⚡ Tăng Cường Khả Năng Chịu Lỗi Gói Tin Âm Thanh FFmpeg (Audio Packet Corruption Resilience):
- Bổ sung cơ chế dung sai lỗi nén AAC (-err_detect ignore_err -max_error_rate 1.0), giúp FFmpeg render mượt mà các video phim dài tải về từ web mà không bị crash hay drop tiến trình.
- Triệt tiêu hoàn toàn hàng trăm nghìn dòng log rác decoder, chống phình dung lượng log và giật lag giao diện web.

4. 🎙️ Tối Ưu Hóa & Đột Phá Tốc Độ TTS Studio:
- Tăng tốc 7x - 15x với GPU Batch Engine RTX 5060 và bộ nhớ đệm Sentence Cache 2 tầng (Instant Hit 0.01s).
- Hỗ trợ nhập hàng loạt tệp kịch bản (.txt, .docx, .pdf, .srt, .vtt, .md, .json, .csv) hoặc cả thư mục kịch bản, tự động đọc lần lượt theo thứ tự tự nhiên (Natural Sort).
- Hỗ trợ tạo audio truyện dài (30p - 1h) với bộ tách nhịp thông minh chống nuốt âm, lặp từ hoặc timeout.

5. 🌐 Nâng Cấp Cào Kênh & Bộ Sưu Tập Douyin Không Bị Chặn:
- Nâng cấp cơ chế cuộn trang phần cứng (Native Hardware Wheel/Key) kết hợp Patchright Stealth bypass chống phát hiện bot.
- Sửa lỗi cào kênh bị dừng ở trang đầu (21 video) -> quét trọn vẹn 100% danh sách video kênh và video ghim.
- Hỗ trợ giải mã bộ sưu tập Douyin từ URL chứa tham số showSubTab=compilation, vid=.

6. 🛠️ Khắc Phục Lỗi Hệ Thống & Nâng Cao Tính Ổn Định:
- Phân tách tên tệp phụ đề rời (_subtitles.srt) chống lỗi hiển thị 2 lớp sub đè nhau (Hardsub + Softsub).
- Tự động phát hiện và tải môi trường Python Portable (~17MB) từ Microsoft NuGet khi máy khách chưa có Python (mã lỗi 9009 PyTorch).
- Thêm khóa luồng nguyên tử (RLock) và retry backoff triệt tiêu hoàn toàn lỗi WinError 5 Access is Denied.
- Sửa lỗi DOM sập thanh công cụ VideoStudioSuite."""

# Import and run publish_patch
import subprocess

cmd = [
    sys.executable,
    os.path.join(os.path.dirname(__file__), "publish_patch.py"),
    "--version", "1.3.7",
    "--changelog", changelog.strip()
]

print("Executing publish_patch.py for v1.3.7...")
res = subprocess.run(cmd, check=True)
sys.exit(res.returncode)
