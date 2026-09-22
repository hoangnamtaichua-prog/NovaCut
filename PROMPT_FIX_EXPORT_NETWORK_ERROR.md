# Prompt gửi cho AI sửa lỗi

Hãy kiểm tra và sửa lỗi xuất video NovaCut theo `REPORT_EXPORT_NETWORK_ERROR.md` đính kèm và ảnh log tôi cung cấp. Đây là nhiệm vụ sửa mã và kiểm thử, không chỉ trả kế hoạch.

Triệu chứng: 21:52:52 tạo xong 1213/1213 câu TTS; 21:52:55 ghép track xong; 21:52:56 báo chuẩn bị FFmpeg, phụ đề tắt, xử lý 1 lớp phủ; đến 23:11:27 báo “Lỗi kết nối tới Server: network error”, không có kết quả rõ ràng.

Không kết luận do Internet/GPU/blur chỉ từ ảnh. Báo cáo phân biệt lỗi source đã thấy với giả thuyết chưa xác minh. Đọc `.agents/AGENTS.md`, git diff và mã đang được chạy thực tế; giữ nguyên thay đổi sẵn có. Không xóa temp, TTS cache hoặc video cũ để thử lại.

Ưu tiên kiểm tra:

- `web/app.js`: catch quá chung trong luồng xuất, parser SSE không giữ partial chunk/streaming UTF-8, kết quả cuối chưa đối soát backend.
- `routes/video_edit.py`: log FFmpeg xuất hiện trước Popen; sau custom layers có separate_audio_stems đồng bộ không truyền progress/logger/cancel callbacks; render nằm trong response generator; GeneratorExit có thể terminate process; export_status chỉ có active boolean.
- `audio_separator.py`/`mdx_separator.py`: khả năng tiến độ/hủy đã có, thực tế stage đang chạy, log và tài nguyên.
- Nhánh stream-copy proc_sc so với process cleanup; batch_editor caller; chế độ dev/patch overlay.

Hãy thu thập log và thêm stage/job ID trước khi khẳng định nguyên nhân. Nếu không có log phiên cũ, nói rõ chưa thể xác nhận nguyên nhân gốc, vẫn sửa các lỗi kiến trúc có bằng chứng và tái hiện có kiểm soát.

Triển khai job worker tách khỏi subscriber SSE, status bền vững, heartbeat độc lập với công việc blocking, reconnect/status reconciliation không tạo job mới; hủy rõ ràng theo job và quản lý đầy đủ child process. Không chỉ tăng timeout hoặc thêm yield trước lời gọi blocking. Sửa parser SSE đúng UTF-8, chunk boundary, event framing và trạng thái failed/cancelled. Giữ tương thích các caller và kiểm tra license/security. Không âm thầm tắt blur/stem hoặc chuyển CPU để né lỗi.

Bảo toàn và tái dùng track TTS hợp lệ bằng manifest/fingerprint; không bắt tạo lại 1.213 câu khi chỉ retry encode. Phân biệt kết nối mất với render thất bại. Giao diện dark mode hiện có phải hiển thị stage thật, tiến độ stage, reconnect, kết quả/path hoặc lỗi có log; không dùng alert native.

Kiểm thử theo ma trận báo cáo: stem bật/tắt, split SSE từng byte, disconnect/reload ở mọi stage, cancel, server crash, cache invalidation, stream-copy, encoder/filter/disk errors, batch editor và output cũ. Dùng clip ngắn/test tạm trước, không render lại video dài của tôi khi chưa cần. Khi test UI trực tiếp phải dùng trình duyệt hiện rõ theo repo.

Cuối cùng bàn giao: nguyên nhân nào đã có bằng chứng, phần nào còn chưa xác minh; danh sách file sửa; test đã chạy/kết quả thật/ca chưa chạy; ảnh UI thực; cách khởi động lại và thử tính năng. Cập nhật TODO mục chờ phát hành sau khi hoàn tất. Không tự publish release, không tạo patch.zip. Không triển khai toàn bộ tính năng lịch sử video ngoài phạm vi chỉ vì báo cáo này nhắc điểm tích hợp.
