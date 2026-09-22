# Báo cáo yêu cầu: Thông báo Telegram cho NovaCut

## Mục tiêu

Bổ sung thông báo Telegram vào chức năng biên tập hàng loạt của NovaCut. Người dùng cần nhận được thông báo khi từng video hoàn tất xử lý và khi toàn bộ danh sách video đã xử lý xong.

## Thông tin Telegram

- Chat ID hiện tại: `5011367599`
- Bot Token: không ghi trong tài liệu, mã nguồn, log, ảnh chụp màn hình hoặc prompt. Token đã từng được gửi trong cuộc trò chuyện nên phải thu hồi bằng BotFather và tạo Token mới trước khi cấu hình.
- Token mới phải được nhập qua biến môi trường, tệp cấu hình cục bộ được loại khỏi Git, hoặc giao diện cài đặt bảo mật của NovaCut.

## Phạm vi chức năng

### Cấu hình

Thêm khu vực cấu hình Telegram trong phần Cài đặt của NovaCut với các mục:

- Bật/tắt thông báo Telegram.
- Bot Token, hiển thị dạng mật khẩu.
- Chat ID.
- Nút gửi tin nhắn kiểm tra.
- Lựa chọn thông báo sau mỗi video, khi hoàn tất toàn bộ batch, hoặc cả hai.

Không hiển thị toàn bộ Token sau khi lưu. Không ghi Token vào log, lịch sử thao tác, báo cáo lỗi, Git hoặc dữ liệu xuất ra.

### Thông báo sau mỗi video

Sau khi một video xử lý thành công, gửi thông báo gồm:

- Tên video nguồn.
- Trạng thái thành công.
- Vị trí hoặc tên file kết quả nếu có.
- Thời gian xử lý nếu hệ thống đã có thông tin này.
- Tiến độ batch, ví dụ: video thứ 3 trên tổng số 10.

Nếu xử lý thất bại, gửi thông báo lỗi ngắn gọn gồm tên video, trạng thái thất bại và nguyên nhân có thể đọc được. Không gửi nội dung nhạy cảm hoặc toàn bộ traceback vào Telegram.

### Thông báo khi hoàn tất batch

Khi toàn bộ batch kết thúc, gửi một thông báo tổng hợp gồm:

- Tổng số video.
- Số video thành công.
- Số video thất bại.
- Số video bị bỏ qua hoặc hủy nếu có.
- Thời gian bắt đầu và kết thúc nếu hệ thống hỗ trợ.
- Thư mục kết quả hoặc liên kết nội bộ nếu có.

Nếu batch bị người dùng hủy, gửi trạng thái đã hủy và thống kê các video đã hoàn thành.

## Yêu cầu kỹ thuật

- Việc gửi Telegram không được làm treo giao diện hoặc dừng pipeline biên tập.
- Nếu Telegram không khả dụng, NovaCut vẫn phải tiếp tục xử lý video và ghi nhận lỗi gửi thông báo riêng.
- Có cơ chế timeout và thử lại giới hạn cho lỗi mạng tạm thời.
- Không gửi trùng thông báo khi một sự kiện hoàn tất bị phát lại.
- Hỗ trợ tên file Unicode và ký tự đặc biệt an toàn.
- Khi người dùng bấm gửi tin nhắn kiểm tra, hiển thị rõ thành công hoặc lý do thất bại.
- Giữ tương thích với các phương thức biên tập đơn lẻ và biên tập hàng loạt hiện có.

## Tiêu chí nghiệm thu

1. Người dùng nhập Token mới và Chat ID, bật thông báo rồi gửi tin nhắn kiểm tra thành công.
2. Khi một video trong batch hoàn tất, Telegram nhận đúng một thông báo cho video đó.
3. Khi toàn bộ batch kết thúc, Telegram nhận một thông báo tổng hợp chính xác.
4. Video lỗi tạo thông báo lỗi nhưng không làm dừng các video còn lại.
5. Mất mạng Telegram không làm hỏng quá trình biên tập.
6. Token không xuất hiện trong log, giao diện sau khi lưu, file xuất bản hoặc Git.
7. Tắt thông báo thì pipeline không thực hiện yêu cầu gửi Telegram.
8. Kiểm thử được cả batch rỗng, một video, nhiều video, video thành công, video thất bại và thao tác hủy.

## Hướng dẫn bảo mật bắt buộc

Token cũ đã bị lộ trong cuộc trò chuyện. Trước khi chạy tính năng:

1. Mở `@BotFather` trên Telegram.
2. Dùng `/revoke` để thu hồi Token cũ.
3. Dùng `/token` để tạo Token mới cho bot.
4. Gửi `/start` cho bot.
5. Nhập Token mới trực tiếp vào NovaCut hoặc cấu hình cục bộ; không gửi Token mới vào chat và không commit vào repository.

## Prompt giao cho AI khác

Bạn là kỹ sư phần mềm phụ trách NovaCut. Hãy kiểm tra kiến trúc hiện tại của ứng dụng, xác định luồng biên tập hàng loạt và triển khai chức năng thông báo Telegram theo báo cáo này.

Yêu cầu thực hiện:

- Tích hợp Telegram vào luồng biên tập hàng loạt.
- Hỗ trợ thông báo sau từng video, sau toàn bộ batch, thông báo lỗi và trạng thái hủy.
- Thêm cấu hình bật/tắt, Bot Token, Chat ID và nút gửi thử nếu phù hợp với giao diện hiện tại.
- Dùng Chat ID `5011367599` làm giá trị cấu hình mặc định có thể chỉnh sửa.
- Không đưa Bot Token vào mã nguồn, tài liệu, log, test, commit hoặc câu trả lời cuối cùng. Token đã lộ và phải được thay bằng Token mới do BotFather cấp.
- Lưu Token bằng cơ chế bảo mật phù hợp với kiến trúc NovaCut; ưu tiên biến môi trường hoặc kho cấu hình cục bộ bị loại khỏi Git.
- Tách lỗi gửi Telegram khỏi lỗi biên tập để mạng Telegram lỗi không làm dừng pipeline.
- Thêm timeout, thử lại giới hạn và chống gửi trùng.
- Giữ nguyên hành vi hiện có của biên tập đơn lẻ và biên tập hàng loạt khi người dùng tắt thông báo.
- Kiểm tra các trường hợp thành công, thất bại, hủy, batch rỗng, nhiều video và mất mạng.
- Sau khi triển khai, báo cáo các file đã thay đổi, cách cấu hình Token mới và kết quả kiểm thử. Không in hoặc trích lại Token.

Trước khi sửa, hãy đọc cấu trúc repository và các quy ước hiện có của NovaCut. Sau khi sửa, kiểm tra giao diện, luồng xử lý nền, log và khả năng đóng gói ứng dụng. Chỉ hoàn tất khi các tiêu chí nghiệm thu trong báo cáo này đều được đáp ứng.

