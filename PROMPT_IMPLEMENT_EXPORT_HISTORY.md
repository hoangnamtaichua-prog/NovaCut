# Prompt giao cho AI triển khai

Bạn đang làm việc trong repository NovaCut / AI-Movie-Shorts. Hãy triển khai hoàn chỉnh tính năng **Lịch sử xuất video** theo tài liệu `REPORT_EXPORT_HISTORY.md` đính kèm. Đọc toàn bộ báo cáo và chỉ dẫn repository trước khi sửa. Báo cáo là đặc tả thiết kế, không phải xác nhận tính năng đã tồn tại; số dòng chỉ là mốc khảo sát.

Mục tiêu: tôi có nhiều video ở nhiều folder. Sau mỗi lần xuất, tôi cần xem tên file, ngày giờ hoàn thành, dung lượng, công cụ xuất và đường dẫn, tìm kiếm lại, mở video, mở đúng folder và copy đường dẫn. Lịch sử phải còn sau khi đóng/mở app. Cần chức năng nhập video cũ từ thư mục do tôi chọn, preview trước khi nhập và không bịa ngày xuất.

Yêu cầu thực hiện:

1. Đọc `.agents/AGENTS.md`, kiểm tra git status/diff. Bảo toàn mọi thay đổi có sẵn. Khảo sát lại luồng thực trước khi sửa, nêu ngắn các khác biệt với báo cáo nếu có.
2. Dùng SQLite trong `USER_DATA_DIR`, service độc lập Flask, migration và transaction. Không dùng localStorage làm nguồn lưu lịch sử. Backend ghi khi xuất thành công, trước thông báo hoàn thành; dùng run ID và UNIQUE event key chống trùng. Lỗi lưu lịch sử không được biến video đã xuất thành thất bại.
3. Bao phủ cả stream copy và encode của editor, batch editor, review, narration, từng preset batch queue và comic review. Chỉ định một nơi chịu trách nhiệm ghi cho mỗi output; tránh trùng giữa pipeline và queue manager. Không ghi file tạm/bản copy nội bộ, không nhận file cũ còn tồn tại là bằng chứng lần chạy lỗi đã thành công.
4. Tạo tab Lịch sử xuất video theo wireframe và token màu trong báo cáo. Dùng theme dark hiện có, Inter, cyan, bảng tên file/đường dẫn/metadata, tìm kiếm và bộ lọc, phân trang, empty/loading/error/missing states. Modal/toast đồng bộ app, không dùng alert/confirm native. Render đường dẫn bằng textContent, không innerHTML.
5. Mở video/mở thư mục theo ID tra từ DB và kiểm tra lại file; không nhận lệnh hay đường dẫn tùy ý từ client. Giữ các kiểm tra quyền bản quyền và đường dẫn hiện có, xử lý restart mà không mở rộng quyền toàn filesystem. Xóa record không xóa file thật.
6. Làm import video cũ theo scan/preview/commit: thư mục do người dùng chọn, quét con tùy chọn, hủy/tiến độ, chống trùng và kiểm tra candidate lại khi commit. Mục imported có ngày xuất không xác định, tách ngày nhập và mtime. Không tự quét ổ đĩa.
7. Kiểm thử theo ma trận báo cáo: persistence, concurrency/idempotency, failure/cancel, Unicode/path injection, import trùng, file mất/ổ offline, pagination/search, quyền và các luồng xuất. Test dùng DB/file tạm, mock mở ứng dụng; integration dùng clip ngắn. Demo/test UI trực tiếp phải có trình duyệt hiện rõ theo quy định repo.
8. Cập nhật `TODO.md` mục CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH sau khi code hoàn thành. Kiểm tra dev/patch overlay, chỉ rõ cần restart/reload. Không tự publish, release hoặc tạo patch.zip.

Hãy thực hiện code và kiểm thử, không chỉ trả kế hoạch. Tự quyết các chi tiết nhỏ theo kiến trúc sẵn có; chỉ hỏi khi thiếu thông tin thực sự chặn công việc. Không thêm framework hay dependency nặng nếu không cần. Tránh refactor ngoài phạm vi.

Cuối cùng bàn giao: danh sách thay đổi, ảnh giao diện thực, kết quả test thật và các ca chưa chạy, hướng dẫn sử dụng ngắn, giới hạn còn lại. Không khẳng định đã test hoặc đã hoàn thành phần chưa thực hiện. Tiêu chí quan trọng nhất là sau khi xuất và khởi động lại app, tôi vẫn tìm thấy và mở được đúng video trong bất kỳ folder đã chọn hợp lệ nào.
