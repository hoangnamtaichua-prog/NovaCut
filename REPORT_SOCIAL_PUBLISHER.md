# 📊 BÁO CÁO TRIỂN KHAI TÍNH NĂNG ĐĂNG VIDEO LÊN MẠNG XÃ HỘI (SOCIAL MEDIA VIDEO PUBLISHER)

**Dự án:** NovaCut - AI Video & Review Editor  
**Hệ điều hành:** Windows 10/11  
**Thời gian hoàn thành:** 22/09/2026  
**Trạng thái:** ✅ Đã hoàn thành, kiểm thử 100% đạt chuẩn (17/17 Unit/Integration Tests Passed).

---

## 1. Mục Tiêu & Kiến Trúc Thiết Kế

Tính năng **"Đăng video lên mạng xã hội"** được xây dựng nhằm giải quyết bài toán đưa video thành phẩm từ NovaCut lên các kênh truyền thông xã hội một cách nhanh chóng, mượt mà và **tuyệt đối an toàn**.

### Nguyên Tắc An Toàn & Bảo Mật Cốt Lõi:
1. **Khởi chạy Google Chrome với Profile Người Dùng (`--profile-directory="..."`):**
   - Tự động dò tìm đường dẫn cài đặt `chrome.exe` trên máy tính Windows (kiểm tra PATH, `Program Files`, `Program Files (x86)`, `%LOCALAPPDATA%`, Windows Registry `App Paths`).
   - Quét danh sách các Profile thực tế trong `%LOCALAPPDATA%\Google\Chrome\User Data\Local State` (`profile.info_cache`), lấy đúng tên profile, tên tài khoản Google và email.
   - Khi người dùng chọn profile và bấm mở, Chrome sẽ kích hoạt cửa sổ với đúng tài khoản đã đăng nhập sẵn.
2. **Bảo Mật Cookie & Phiên Đăng Nhập:**
   - **Tuyệt đối KHÔNG đọc, trích xuất, giải mã, hiển thị hoặc lưu cookie/mật khẩu dưới dạng văn bản.**
   - NovaCut không đóng vai trò bot tự động xâm nhập phiên đăng nhập của người dùng. Chrome tự quản lý cookie an toàn trong vùng sandbox của trình duyệt.
3. **Không Cố Vượt CAPTCHA / 2FA:**
   - Ứng dụng không can thiệp vào cơ chế phòng vệ chống bot của nền tảng (không dùng cờ tự động hóa như `--remote-debugging-port` hay `AutomationControlled` gây gắn cờ bot).
   - Mở đúng trang upload tương ứng, người dùng toàn quyền kiểm soát bước bấm nút tải/đăng cuối cùng trên giao diện chính thức của nền tảng.
4. **Kiểm Soát Đường Dẫn An Toàn:**
   - Chỉ cho phép các định dạng tệp video hợp lệ (`.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`, `.m4v`).
   - Tích hợp hàm kiểm tra bảo mật `routes.security.is_path_allowed` để chống tấn công Path Traversal.

---

## 2. Danh Sách Các Tệp Đã Tạo & Chỉnh Sửa

| Tệp tin | Trạng thái | Mô tả chi tiết |
| :--- | :--- | :--- |
| [`social_publisher.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/social_publisher.py) | **Mới** | Core engine: Dò tìm Chrome, quét Profile người dùng, định dạng kịch bản bài đăng, chuẩn hóa hashtag, khởi chạy Chrome và quản lý lịch sử thao tác nguyên tử (`social_publish_history.json`). |
| [`patches/active/social_publisher.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/social_publisher.py) | **Mới** | Bản đồng bộ cho hệ thống OTA Patch Overlay của NovaCut. |
| [`routes/social_publish.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/routes/social_publish.py) | **Mới** | Cung cấp đầy đủ 6 Flask API RESTful: `platforms`, `profiles`, `prepare`, `open`, `status`, `history` (kèm `history/clear`). |
| [`patches/active/routes/social_publish.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/routes/social_publish.py) | **Mới** | Bản đồng bộ OTA cho route. |
| [`web/js/features/social_publisher.js`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/web/js/features/social_publisher.js) | **Mới** | Frontend controller: Quản lý chọn nền tảng, chọn Chrome profile, nạp video nhanh từ dự án vừa xuất, tạo bản xem trước trực quan (Live Social Preview), đếm ký tự bài đăng, tiện ích sao chép 1 chạm và gọi API. |
| [`patches/active/web/js/features/social_publisher.js`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/web/js/features/social_publisher.js) | **Mới** | Bản đồng bộ OTA cho frontend module. |
| [`web_app.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/web_app.py) | **Sửa** | Đăng ký Blueprint `social_publish_bp`. |
| [`patches/active/web_app.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/web_app.py) | **Sửa** | Đồng bộ đăng ký Blueprint trong OTA runtime. |
| [`license_manager.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/license_manager.py) | **Sửa** | Bổ sung phân quyền `can_access_social_publish` cho các gói bản quyền (Trial, Pro, VIP, Yearly, Admin = True; Unlicensed = False). |
| [`patches/active/license_manager.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/license_manager.py) | **Sửa** | Đồng bộ phân quyền bản quyền vào OTA overlay. |
| [`web/index.html`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/web/index.html) | **Sửa** | Thêm tab "Đăng mạng xã hội" vào nhóm MỞ RỘNG & TỰ ĐỘNG và bố cục giao diện hoàn chỉnh của view `viewSocialPublish`. |
| [`patches/active/web/index.html`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/web/index.html) | **Sửa** | Đồng bộ giao diện HTML cho OTA. |
| [`web/style.css`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/web/style.css) | **Sửa** | Thêm hệ thống CSS Dark Mode chuyên nghiệp cho thẻ nền tảng, khung xem trước (Live Preview Card) và bảng lịch sử. |
| [`patches/active/web/style.css`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/web/style.css) | **Sửa** | Đồng bộ CSS cho OTA overlay. |
| [`web/app.js`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/web/app.js) | **Sửa** | Nạp module `social_publisher.js`, gắn bộ lắng nghe chuyển tab và phân quyền kiểm tra bản quyền 2 tầng trước khi mở view. |
| [`patches/active/web/app.js`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/patches/active/web/app.js) | **Sửa** | Đồng bộ logic chuyển tab vào OTA overlay. |
| [`scripts/test_social_publisher.py`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/scripts/test_social_publisher.py) | **Mới** | Bộ kiểm thử tự động toàn diện (17 test cases). |
| [`TODO.md`](file:///d:/Tool/AI-Movie-Shorts/AI-Movie-Shorts/TODO.md) | **Sửa** | Ghi nhận chi tiết thay đổi vào mục "CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH" theo đúng quy tắc Bug Fix & Feature Tracking. |

---

## 3. Chi Tiết Các API Endpoint

### 1. `GET /api/social/platforms`
- **Mục đích:** Cung cấp danh sách 6 mạng xã hội kèm cấu hình chuyên biệt:
  - **YouTube Studio:** Giới hạn tiêu đề 100 ký tự, mô tả 5000 ký tự, URL upload: `https://studio.youtube.com/channel/UC/videos/upload?d=ud`.
  - **TikTok Studio:** Caption 2200 ký tự, URL upload: `https://www.tiktok.com/creator-center/upload?from=webapp`.
  - **Facebook (Meta Business):** Tiêu đề 255 ký tự, mô tả 2000 ký tự, URL upload: `https://business.facebook.com/latest/composer/`.
  - **Instagram:** Caption 2200 ký tự, URL: `https://www.instagram.com/`.
  - **X (Twitter):** Caption 280 ký tự, URL: `https://x.com/compose/post`.
  - **LinkedIn:** Caption 3000 ký tự, URL: `https://www.linkedin.com/feed/?shareActive=true`.

### 2. `GET /api/social/profiles`
- **Mục đích:** Quét tìm trình duyệt Google Chrome và trích xuất tất cả Chrome Profile có sẵn trên máy tính.
- **Phản hồi:** Trả về `chrome_installed` (bool), `chrome_path` (đường dẫn), `profiles` (danh sách `{ id, name, display_name, email, avatar_icon, is_default }`).

### 3. `POST /api/social/prepare`
- **Mục đích:** Tiếp nhận thông tin bài đăng từ người dùng, kiểm tra tệp video (định dạng, kích thước, kiểm tra tồn tại và phân quyền truy cập an toàn), làm sạch và chuẩn hóa hashtag (`#`), tính toán độ dài ký tự và đưa ra cảnh báo nếu vượt quá giới hạn từng nền tảng.
- **Payload:** `{ platform_id, video_path, title, description, caption, hashtags, privacy }`.
- **Mã lỗi:** Trả về `400 Bad Request` nếu sai nền tảng hoặc sai định dạng video; `404 Not Found` nếu video không tồn tại; `403 Forbidden` nếu tệp nằm ngoài thư mục cho phép.

### 4. `POST /api/social/open`
- **Mục đích:** 
  1. Kiểm tra bản quyền phía Backend (`license_manager.check_permission('can_access_social_publish')`), trả về `403 Forbidden` kèm thông báo bản quyền nếu chưa kích hoạt.
  2. Khởi chạy Google Chrome độc lập với cờ `--profile-directory="<profile_id>"` mở đúng URL upload của nền tảng.
  3. Tự động sao chép đường dẫn tuyệt đối của video vào Clipboard của Windows.
  4. Ghi nhận nhật ký thao tác vào `user_data/social_publish_history.json`.

### 5. `GET /api/social/status`
- **Mục đích:** Trả về tổng quan trạng thái (tình trạng cài đặt Chrome, số lượng Profile phát hiện, số nền tảng hỗ trợ, số lượt thao tác trong lịch sử, quyền bản quyền hiện tại).

### 6. `GET /api/social/history` & `POST /api/social/history/clear`
- **Mục đích:** Đọc danh sách lịch sử thao tác theo thứ tự mới nhất lên đầu và cho phép dọn dẹp lịch sử khi cần.

---

## 4. Trải Nghiệm Giao Diện Người Dùng (UI/UX)

- **Vị trí Tab:** Nằm trên thanh điều hướng chính tại nhóm **MỞ RỘNG & TỰ ĐỘNG** với tiêu đề **"Đăng mạng xã hội"** và icon chia sẻ hiện đại.
- **Bố cục 2 Cột (Desktop Layout):**
  - **Cột Trái (4 Bước Trực Quan):**
    1. *Bước 1:* Thẻ chọn nền tảng trực quan (YouTube, TikTok, Facebook, Instagram, X, LinkedIn) với logo chính thức, hiệu ứng viền phát sáng khi chọn.
    2. *Bước 2:* Menu chọn Chrome Profile với thông tin tài khoản Google / Email rõ ràng.
    3. *Bước 3:* Chọn Video: Hỗ trợ nút **"⚡ Dùng Video Vừa Xuất"** (tự động nạp video thành phẩm vừa xuất từ Biên tập phim hoặc Review Phim) hoặc bấm **"📁 Chọn Từ Máy Tính"**. Có thẻ hiển thị tên tệp và dung lượng video.
    4. *Bước 4:* Nhập Tiêu đề, Mô tả/Caption, Hashtag (kèm các nút gắn hashtag nhanh 1 chạm như `#reviewphim`, `#phimhay`, `#shorts`, `#reels`...) và tùy chọn Quyền riêng tư.
  - **Cột Phải (Live Preview & Thao Tác):**
    - *Live Social Preview Card:* Hiển thị bản mô phỏng bài đăng thực tế theo đúng phong cách của mạng xã hội đang chọn.
    - *Nút Hành Động Lớn:* **"🚀 Xem Lại & Mở Chrome Đăng Video"** với hiệu ứng gradient tím - xanh nổi bật.
    - *Bộ Tiện Ích Sao Chép Nhanh:* Nút copy tiêu đề, copy mô tả, copy đường dẫn file.
    - *Tính Năng Tự Động Copy Clipboard:* Khi bấm mở, đường dẫn tệp video tự động được nạp vào Clipboard của Windows. Khi hộp thoại chọn tệp của trình duyệt hiện ra, người dùng chỉ cần nhấn **Ctrl+V** là file được chọn ngay lập tức.
- **Bảng Lịch Sử Dưới Cùng:** Hiển thị thời gian, nền tảng, tiêu đề, tên video, profile và huy hiệu trạng thái thành công/thất bại rõ ràng.

---

## 5. Kết Quả Kiểm Thử (Verification & Testing)

Đã khởi tạo và thực thi thành công bộ test tự động tại `scripts/test_social_publisher.py`:

```
test_chrome_executable_and_profiles ... ok
test_clean_hashtags ... ok
test_prepare_publish_content_invalid_platform ... ok
test_prepare_publish_content_tiktok ... ok
test_prepare_publish_content_warnings_length ... ok
test_prepare_publish_content_youtube ... ok
test_publish_history_io ... ok
test_api_history_and_clear ... ok
test_api_open_success_mocked ... ok
test_api_open_unlicensed_permission_denied ... ok
test_api_platforms ... ok
test_api_prepare_invalid_extension ... ok
test_api_prepare_invalid_platform ... ok
test_api_prepare_nonexistent_file ... ok
test_api_prepare_valid ... ok
test_api_profiles ... ok
test_api_status ... ok

----------------------------------------------------------------------
Ran 17 tests in 0.305s

OK
```

### Kết Quả Kiểm Thử Thực Tế Trên Môi Trường App:
- Google Chrome được nhận diện chuẩn xác tại: `C:\Program Files\Google\Chrome\Application\chrome.exe`.
- Phát hiện đầy đủ **7 Google Chrome Profile** đang hoạt động trên máy tính của người dùng.
- Cú pháp toàn bộ các tệp Python biên dịch thành công 100% (`py_compile`).
- Toàn bộ cơ chế phân quyền bản quyền 2 tầng bảo vệ tuyệt đối tính năng: Chặn ở Frontend với Custom Dark Mode Alert và chặn ở Backend với HTTP 403.

---

## 6. Hướng Dẫn Sử Dụng Nhanh

1. Khởi động ứng dụng NovaCut: `python web_app.py` hoặc chạy `run_nova.bat`.
2. Trên thanh menu bên trái, nhấp chọn tab **"Đăng mạng xã hội"**.
3. Chọn mạng xã hội bạn muốn đăng (ví dụ: YouTube Studio, TikTok hoặc Facebook).
4. Chọn đúng Chrome Profile tương ứng với kênh/tài khoản của bạn.
5. Bấm **"⚡ Dùng Video Vừa Xuất"** để lấy ngay video bạn vừa biên tập xong (hoặc chọn từ máy tính).
6. Nhập nội dung tiêu đề, mô tả và nhấp chọn các hashtag xu hướng.
7. Nhìn sang khung xem trước bên phải để kiểm tra bố cục bài đăng.
8. Bấm **"🚀 Xem Lại & Mở Chrome Đăng Video"**.
9. Trình duyệt Chrome sẽ lập tức bật lên đúng tài khoản của bạn và mở sẵn trang đăng video. Tại hộp thoại chọn tệp, chỉ cần nhấn **Ctrl+V** và Enter để hoàn tất tải video!
