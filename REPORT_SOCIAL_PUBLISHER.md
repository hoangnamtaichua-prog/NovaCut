# Báo cáo yêu cầu: Chức năng đăng video lên mạng xã hội bằng Chrome

## 1. Mục tiêu

Xây dựng chức năng trong NovaCut để mở Google Chrome bằng profile đã đăng nhập, truy cập YouTube, Facebook, TikTok và các mạng xã hội khác, chuẩn bị nội dung đăng bài và hỗ trợ người dùng đăng video.

Chức năng cần hỗ trợ:

- Mở Chrome mới hoặc mở thêm tab trên Chrome đang dùng.
- Chọn profile Chrome đã đăng nhập.
- Sử dụng session/cookie sẵn có trong profile Chrome.
- Chọn video đã xuất từ NovaCut.
- Nhập tiêu đề, mô tả, caption, hashtag và quyền riêng tư.
- Mở trang upload tương ứng của từng nền tảng.
- Cho phép xem lại trước khi bấm nút đăng cuối cùng.
- Ghi lịch sử thao tác và trạng thái đăng.

## 2. Tình trạng dự án hiện tại

Dự án hiện đang sử dụng:

- Python Flask làm backend.
- pywebview làm giao diện desktop.
- Giao diện chính tại `web/index.html` và `web/app.js`.
- Nhiều route backend nằm trong thư mục `routes/`.
- Có sẵn chức năng xử lý và xuất video cho YouTube, TikTok, Facebook và các nền tảng khác.
- Chưa có module chuyên biệt để đăng bài lên mạng xã hội.

## 3. Kiến trúc đề xuất

Tạo các thành phần sau:

```text
social_publisher.py
routes/social_publish.py
web/js/features/social_publisher.js
```

Đăng ký blueprint mới trong `web_app.py` và thêm một tab giao diện có tên `Đăng mạng xã hội`.

## 4. Xử lý đăng nhập và cookie

Ưu tiên sử dụng Chrome profile thay vì yêu cầu người dùng nhập cookie thủ công.

Thư mục profile mặc định trên Windows:

```text
%LOCALAPPDATA%\\Google\\Chrome\\User Data
```

Các profile thường gặp:

```text
Default
Profile 1
Profile 2
```

Ví dụ lệnh mở Chrome:

```text
chrome.exe --profile-directory="Default" https://studio.youtube.com/
```

Ứng dụng cần:

- Liệt kê các profile Chrome có sẵn.
- Cho người dùng chọn profile.
- Mở Chrome bằng profile được chọn.
- Giữ cookie bên trong Chrome.
- Không đọc, xuất, hiển thị hoặc lưu cookie dạng text.
- Nếu profile chưa đăng nhập, mở trang đăng nhập để người dùng đăng nhập thủ công.

Không nên yêu cầu người dùng dán cookie Facebook, TikTok hoặc YouTube vào ứng dụng vì có thể làm lộ phiên đăng nhập.

## 5. Nền tảng cần hỗ trợ

### Giai đoạn đầu

- YouTube Studio.
- TikTok Upload.
- Facebook.
- Instagram.

### Giai đoạn mở rộng

- X/Twitter.
- LinkedIn.
- Threads.
- Các nền tảng khác có giao diện web.

Mỗi nền tảng cần có cấu hình URL và luồng upload riêng vì giao diện, giới hạn dung lượng, định dạng và trường metadata khác nhau.

## 6. Luồng sử dụng

1. Người dùng mở tab `Đăng mạng xã hội`.
2. Chọn Chrome profile.
3. Chọn một hoặc nhiều nền tảng.
4. Chọn video từ thư mục xuất của NovaCut.
5. Nhập tiêu đề, mô tả, caption, hashtag và quyền riêng tư.
6. Bấm `Mở trình đăng bài`.
7. Ứng dụng mở Chrome tới trang upload.
8. Tự động chuẩn bị nội dung và chọn file nếu nền tảng cho phép.
9. Hiển thị trạng thái để người dùng kiểm tra.
10. Người dùng xác nhận nút `Đăng` cuối cùng.

Nên giữ bước xác nhận cuối vì nền tảng có thể yêu cầu CAPTCHA, xác minh hai bước, kiểm tra bản quyền hoặc xác nhận thông tin tài khoản.

## 7. API backend đề xuất

```text
GET  /api/social/platforms
GET  /api/social/profiles
POST /api/social/open
POST /api/social/prepare
GET  /api/social/status
GET  /api/social/history
```

Ví dụ mở nền tảng:

```json
{
  "platform": "youtube",
  "profile": "Default",
  "compose": true
}
```

Ví dụ dữ liệu bài đăng:

```json
{
  "platforms": ["youtube", "tiktok", "facebook"],
  "video_path": "D:/Videos/output.mp4",
  "title": "Tên video",
  "caption": "Nội dung bài đăng",
  "hashtags": ["#reviewphim", "#shorts"],
  "privacy": "private"
}
```

## 8. Lưu lịch sử

Có thể lưu lịch sử tại:

```text
user_data/social_publish_history.json
```

Chỉ lưu:

- Nền tảng.
- Tên file video.
- Thời gian thao tác.
- Profile được chọn, không lưu cookie.
- Trạng thái mở trang, chuẩn bị, thành công hoặc lỗi.
- Nội dung caption nếu người dùng cho phép lưu.

## 9. Vấn đề kỹ thuật cần xử lý

- Chrome có thể đang chạy và khóa profile.
- Chrome có thể yêu cầu đăng nhập lại.
- Giao diện các nền tảng thường xuyên thay đổi.
- TikTok, Facebook hoặc Instagram có thể hiển thị CAPTCHA.
- YouTube có giới hạn dung lượng, định dạng và thời lượng.
- Instagram có yêu cầu riêng về tỷ lệ video.
- Đường dẫn video phải được kiểm tra trước khi upload.
- Không ghi cookie, mật khẩu hoặc token vào log.
- Không tự động vượt CAPTCHA hoặc cơ chế xác minh bảo mật.
- Cần xử lý trường hợp Chrome chưa được cài ở đường dẫn mặc định.

## 10. Kiểm thử bắt buộc

- Chrome chưa chạy.
- Chrome đang chạy.
- Profile `Default`.
- Profile khác.
- Profile chưa đăng nhập.
- File video không tồn tại.
- File video sai định dạng.
- Mở từng nền tảng.
- Mở nhiều nền tảng.
- Người dùng hủy trước khi đăng.
- Nền tảng yêu cầu CAPTCHA.
- Chrome không nằm trong đường dẫn cài đặt mặc định.

## 11. Tiêu chí hoàn thành

- Có tab giao diện đăng mạng xã hội.
- Liệt kê và chọn được Chrome profile.
- Mở đúng nền tảng bằng profile đã chọn.
- Không lưu hoặc hiển thị cookie thô.
- Chọn được video từ NovaCut.
- Nhập và kiểm tra được metadata bài đăng.
- Có trạng thái lỗi dễ hiểu bằng tiếng Việt.
- Có bước xem lại trước khi đăng.
- Có lịch sử thao tác.
- Có kiểm thử backend cho các endpoint chính.

## 12. Prompt gửi cho AI khác

```text
Bạn hãy triển khai chức năng đăng video lên mạng xã hội cho dự án NovaCut hiện tại.

Bối cảnh dự án:
- Python Flask backend.
- pywebview desktop app.
- Giao diện chính ở web/index.html và web/app.js.
- Backend route nằm trong routes/.
- Dự án chạy trên Windows.

Mục tiêu:
- Thêm tab “Đăng mạng xã hội”.
- Mở Google Chrome bằng Chrome profile người dùng chọn.
- Tận dụng phiên đăng nhập/cookie có sẵn trong profile Chrome.
- Không đọc, xuất, hiển thị hoặc lưu cookie dạng text.
- Hỗ trợ YouTube Studio, TikTok, Facebook và Instagram trước.
- Có thể mở rộng cho X/Twitter và LinkedIn.
- Cho phép chọn video, nhập tiêu đề, mô tả, caption, hashtag và quyền riêng tư.
- Mở đúng trang upload của từng nền tảng.
- Có bước xem lại trước khi người dùng bấm nút đăng cuối cùng.
- Có lịch sử thao tác trong user_data/social_publish_history.json.

Yêu cầu triển khai:
1. Tạo social_publisher.py để tìm Chrome, liệt kê Chrome profile và mở URL bằng profile được chọn.
2. Tạo routes/social_publish.py với các endpoint:
   GET /api/social/platforms
   GET /api/social/profiles
   POST /api/social/open
   POST /api/social/prepare
   GET /api/social/status
   GET /api/social/history
3. Đăng ký blueprint trong web_app.py.
4. Tạo web/js/features/social_publisher.js.
5. Thêm giao diện vào web/index.html theo phong cách hiện có.
6. Kiểm tra và giới hạn đường dẫn file để tránh truy cập ngoài phạm vi cho phép.
7. Không lưu mật khẩu, cookie, token hoặc dữ liệu nhạy cảm vào log.
8. Không tự động vượt CAPTCHA, xác minh hai bước hoặc cơ chế bảo mật của nền tảng.
9. Nếu giao diện nền tảng không thể tự động hóa ổn định, hãy mở đúng trang upload và để người dùng hoàn tất thủ công.
10. Viết kiểm thử cho endpoint chính và các trường hợp Chrome/profile/file không hợp lệ.
11. Chạy kiểm tra cú pháp, kiểm thử backend và kiểm tra giao diện trước khi hoàn thành.
12. Báo cáo rõ các file đã sửa, cách chạy, giới hạn kỹ thuật và các bước kiểm thử.

Ưu tiên tính an toàn, khả năng bảo trì và khả năng phục hồi khi giao diện mạng xã hội thay đổi.
```
