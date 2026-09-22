# Đặc tả triển khai: Lịch sử xuất video NovaCut

Ngày khảo sát: 21/09/2026. Tài liệu thiết kế dựa trên mã nguồn hiện tại; chưa triển khai tính năng. Số dòng dưới đây là mốc tham khảo, AI thực hiện phải tìm lại theo tên hàm và sự kiện trước khi sửa.

## 1. Mục tiêu và phạm vi

Người dùng có video nằm ở nhiều thư mục, cần trả lời nhanh: “Tôi vừa xuất video nào, lúc nào, lưu ở đâu, mở lại bằng cách nào?”. Thêm một trang **Lịch sử xuất video** dùng chung cho toàn ứng dụng, lưu bền vững sau khi đóng app, khởi động máy hoặc cập nhật ứng dụng.

Yêu cầu bắt buộc:

- Tự ghi mỗi lần xuất thành công: tên file, đường dẫn tuyệt đối, thời điểm hoàn thành, dung lượng và công cụ xuất.
- Tìm theo tên hoặc đường dẫn; lọc công cụ, ngày xuất; mới nhất trước; phân trang.
- Mở video bằng trình phát mặc định; mở thư mục và chọn đúng file; sao chép đường dẫn.
- Hiển thị file còn tồn tại, không tìm thấy hoặc chưa kiểm tra. Không xóa lịch sử khi video bị chuyển/xóa ngoài app.
- Xóa một bản ghi bằng xác nhận riêng, tuyệt đối không xóa video thật.
- Nhập video cũ từ các thư mục người dùng chủ động chọn, có tùy chọn quét thư mục con và bước xem trước.

Không tự quét toàn bộ ổ đĩa. Không tự di chuyển/đổi tên video. Không thêm cloud, tài khoản hay dịch vụ trả phí. Thumbnail, phát trong app, xuất CSV và tự dò vị trí file bị di chuyển có thể làm sau; không cần cho bản đầu.

## 2. Bản đồ mã nguồn đã khảo sát

| Vị trí | Hiện trạng và hướng tích hợp |
|---|---|
| `routes/video_edit.py`, khoảng 861–865 và 1525–1529 | Có hai nhánh thành công: sao chép luồng và encode thường; đều phát `[EVENT:SUCCESS]`. Ghi backend trước khi phát sự kiện ở cả hai nhánh. |
| `web/js/features/batch_editor.js`, khoảng 1373 | Biên tập hàng loạt đọc sự kiện thành công của editor. Không tạo bản ghi từ JavaScript, chỉ thông báo làm mới danh sách. |
| `auto_edit_pipeline.py`, `run_auto_edit_workflow` và `run_narration_workflow` | Kết thúc tại `final_output`, gần dòng 2325 và 2821. Cần xác thực đầu ra và ghi thành công tại đây, phân biệt chạy riêng và được gọi từ hàng đợi. |
| `batch_queue_manager.py`, khoảng 545–563 | Sau pipeline, gán `task.output_path` rồi `task.status = 'completed'`. Đây là điểm quản lý thành công của hàng đợi, phải tránh ghi trùng với pipeline bên dưới. |
| `routes/comic_review.py`, khoảng 855–863 | Có bước copy vào project rồi phát `[RENDER_FINISHED]`; ghi đường dẫn đầu ra người dùng nhận, không ghi bản copy nội bộ như một lần xuất mới. |
| `routes/state.py` | Có `USER_DATA_DIR = user_data_dir('NovaCut', 'NovaCut', roaming=True)`. Dùng nơi này cho cơ sở dữ liệu, không dùng thư mục cài đặt. |
| `routes/security.py` | `is_path_allowed`, `register_user_path`, `safe_join`; quyền đường dẫn được chọn hiện nằm trong bộ nhớ, nên phải tính tình huống khởi động lại app. |
| `routes/core.py`, `api_general_open_folder` | Đã có `/api/open_folder` và Explorer `/select,`; có kiểm tra quyền và đường dẫn. Có thể tách helper để dùng lại, không mở rộng API thành mở đường dẫn tùy ý. |
| `web/index.html`, `web/app.js` | Điều hướng `.header-tabs .nav-tab`, `data-target`, chuyển view ở đầu app.js. Thêm view theo cấu trúc hiện có và kiểm tra chế độ display. |
| `web/style.css` | Đã có token dark mode, Inter, bo góc 12px; tái sử dụng thay vì xây theme khác. |
| `web_app.py` | Đăng ký Flask Blueprint; có cơ chế ưu tiên mã gốc ở dev và `patches/active` ở release. |

Kho mã đang có nhiều thay đổi chưa commit. Không reset, ghi đè toàn bộ file hoặc hoàn tác phần việc sẵn có. Đọc `.agents/AGENTS.md`. Chỉ ghi TODO ở mục chờ phát hành khi thực sự hoàn thành code, không ghi thiết kế này là tính năng đã xong.

## 3. Thiết kế giao diện

### Vị trí và bố cục

Thêm mục điều hướng **Lịch sử xuất video**, icon SVG đồng hồ có mũi tên, cùng kích cỡ icon hiện tại. Đặt gần nhóm quản lý/tải video, không chen vào cụm điều khiển render. View ID đề xuất `viewExportHistory`.

```text
LỊCH SỬ XUẤT VIDEO                 [Nhập video cũ] [Làm mới]
Tìm lại video đã xuất và thư mục lưu trên máy của bạn.

[Tìm theo tên hoặc đường dẫn...............................]
[Tất cả công cụ ▾] [Từ ngày] [Đến ngày]       128 kết quả

Tên video / Thư mục             Xuất lúc       Công cụ   Dung lượng   Thao tác
review_tap_01.mp4               21/09 14:32     Review    235 MB       [Mở video]
D:\Video\Kenh_A\Thang_09        ● Có sẵn                             [Thư mục] [⋯]

clip_02.mp4                    20/09 19:08     Biên tập  84 MB        [Mở video]
E:\Da_xuat\Kenh_B               ! Không tìm thấy                     [Thư mục] [⋯]

                            [Trước] Trang 1 / 6 [Sau]
```

Mỗi hàng cao tối thiểu 80px, tên file nổi bật, đường dẫn nằm dòng riêng có thể chọn/copy. Tên dài và đường dẫn dài dùng ellipsis, tooltip chứa đủ giá trị; modal chi tiết phải cho xem/copy toàn bộ. Header bảng sticky; chỉ vùng danh sách cuộn. Không để bảng dài đẩy phân trang ra ngoài màn hình.

Menu `⋯`: Sao chép đường dẫn, Xem chi tiết, Xóa khỏi lịch sử. Nút Mở video là secondary để tránh cả bảng đầy màu nhấn; nút Nhập video cũ là hành động nhấn chính. Không cần 3–4 thẻ thống kê lớn chiếm không gian.

Ở cửa sổ hẹp hơn khoảng 1000px, chuyển hàng thành card hoặc gộp metadata xuống dòng. Kiểm tra với kích thước 1366×768, 1920×1080 và Windows scaling 125%/150%. Không có thanh cuộn ngang toàn trang.

### Màu sắc và typography

| Vai trò | Giá trị / cách dùng |
|---|---|
| Nền trang | `var(--bg-dark)` = `#070a13` |
| Nền bảng/card/modal | `var(--card-bg)` = `#111827` |
| Viền | `var(--card-border)` = `#1f2937` |
| Nút chính / trạng thái chọn | `var(--primary)` = `#0ea5e9`; hover `#0284c7` |
| Nút phụ / hover hàng | `#1e293b` / `#334155`, dùng vừa phải |
| Tên file, tiêu đề | `var(--text-main)` = `#f8fafc` |
| Đường dẫn, metadata | `var(--text-muted)` = `#94a3b8` |
| Có sẵn | Chữ/icon `#4ade80`, nền xanh trong suốt nhẹ |
| Không tìm thấy | Chữ/icon `#fbbf24`, nền vàng trong suốt nhẹ |
| Xóa bản ghi | Chữ `#f87171`, chỉ dùng trong menu/modal xác nhận |

Font Inter theo ứng dụng. Tiêu đề 22px/700, tên file 14px/600, metadata 12–13px. Padding trang 24px, khoảng cách nhóm 16px, input/nút cao tối thiểu 36px, bo góc 8–12px. Focus ring nhìn rõ; icon luôn kèm nhãn hoặc accessible name. Không chỉ dùng màu để phân biệt tình trạng.

### Trạng thái UI và thông báo

- Chưa có dữ liệu: “Chưa có lịch sử xuất video. Video xuất thành công từ bây giờ sẽ xuất hiện ở đây.” Kèm nút “Nhập video cũ”.
- Lọc không ra kết quả: “Không tìm thấy video phù hợp” và “Xóa bộ lọc”.
- Đang tải: skeleton hoặc dòng loading; lỗi API: thông báo tại trang và nút thử lại.
- File mất: vẫn giữ hàng, ghi “Không tìm thấy tại đường dẫn đã lưu”, vô hiệu hóa Mở video; cho mở thư mục nếu thư mục còn tồn tại.
- Ổ ngoài/ổ mạng không truy cập được: ghi “Chưa thể kiểm tra”, không khẳng định đã bị xóa; vẫn giữ lịch sử.
- Xuất xong: bổ sung “Xem lịch sử” vào thông báo thành công hiện có. Không tự chuyển tab khi người dùng đang làm việc.
- Xóa: modal dark mode “Xóa mục này khỏi lịch sử? File video trên máy vẫn được giữ nguyên.” Nút Hủy/Xóa khỏi lịch sử, mặc định focus Hủy.
- Dùng hệ thống modal/toast hiện có; không dùng `alert`, `confirm`, `prompt` của trình duyệt. Escape đóng modal; trả focus về nút gọi.

## 4. Lựa chọn lưu trữ

| Phương án | Ưu / nhược | Quyết định |
|---|---|---|
| localStorage | Nhanh nhưng phụ thuộc browser/origin, dễ mất, không chắc ghi được khi đóng UI | Không dùng làm nguồn lịch sử |
| JSON trong USER_DATA_DIR | Dễ làm, cần khóa và ghi atomic; lọc/phân trang phải đọc lại dữ liệu | Chỉ phù hợp prototype nhỏ |
| SQLite qua thư viện chuẩn Python | Bền vững, transaction, chống trùng, phân trang, không cần server DB | Chọn cho bản thực tế |

Đường dẫn: `os.path.join(USER_DATA_DIR, 'export_history.sqlite3')`. Không lưu API key, token, nội dung phụ đề hoặc toàn bộ cấu hình request. Module lưu trữ độc lập Flask để worker và test có thể dùng; truyền đường dẫn DB vào constructor, tránh import `routes.state` kéo theo ASR/GPU chỉ để chạy test.

Schema đề xuất `exports`:

```sql
CREATE TABLE IF NOT EXISTS exports (
  id TEXT PRIMARY KEY,
  event_key TEXT NOT NULL UNIQUE,
  output_path TEXT NOT NULL,
  normalized_path TEXT NOT NULL,
  filename TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  origin TEXT NOT NULL CHECK(origin IN ('export', 'import')),
  completed_at TEXT,
  recorded_at TEXT NOT NULL,
  file_mtime_ns INTEGER,
  file_size_bytes INTEGER NOT NULL,
  job_id TEXT,
  project_name TEXT
);
CREATE INDEX IF NOT EXISTS exports_time ON exports(recorded_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS exports_source ON exports(source_kind, recorded_at DESC);
CREATE INDEX IF NOT EXISTS exports_path ON exports(normalized_path);
```

UUID cho `id`; thời gian UTC ISO 8601, hiển thị theo timezone máy. `source_kind`: editor, batch_editor, review, narration, batch_queue, comic_review, imported. `origin=import` phải có `completed_at=NULL`; mtime chỉ là thời gian sửa file, không phải ngày xuất.

Mỗi connection riêng theo operation/thread, timeout hữu hạn; transaction ngắn; `busy_timeout`, migration bằng `PRAGMA user_version`. Có thể bật WAL sau khi kiểm tra môi trường lưu trữ; không giả định thư mục roaming luôn nằm trên đĩa local. Không chia sẻ connection SQLite giữa các thread một cách tùy tiện. Không giữ transaction trong lúc render, stat ổ mạng, ffprobe hoặc mở Explorer.

Không giới hạn âm thầm 20/50 bản ghi như lịch sử tải hiện tại. API trả tối đa 100 hàng/trang, mặc định 50. Tìm kiếm tên/đường dẫn bằng parameterized SQL, xử lý `%`/`_` như ký tự tìm kiếm thông thường nếu UI không công bố wildcard. Test tiếng Việt và không phân biệt hoa thường; SQLite NOCASE mặc định không xử lý đầy đủ Unicode, cần trường search chuẩn hóa bằng Python hoặc giải pháp tương đương có test.

## 5. Luồng ghi lịch sử và chống trùng

1. Khi bắt đầu một lần xuất, backend tạo `export_run_id`. Lần người dùng xuất lại tạo ID mới, kể cả ghi đè cùng tên file.
2. Truyền context gồm ID, nguồn công cụ và chủ thể chịu trách nhiệm ghi vào pipeline. Không dùng biến global cho ID.
3. Chỉ ghi khi tiến trình của lần chạy hiện tại thành công, không bị hủy và file đầu ra hợp lệ. File cũ còn tồn tại sau lần chạy lỗi không đủ chứng minh thành công.
4. Chuẩn hóa đường dẫn bằng hàm tương thích Windows; giữ path hiển thị và path chuẩn hóa phục vụ so sánh. Lấy kích thước và mtime sau khi đóng file đầu ra.
5. Ghi trước sự kiện thành công cuối cùng; `event_key = export_run_id + ':' + normalized_path`. UNIQUE chống callback trùng. Một lần chạy có nhiều output được ghi từng file.
6. Trả `history_id` trong payload thành công nếu có, không đổi format sự kiện cũ. UI chỉ cập nhật/làm mới, không POST tạo lịch sử dựa trên log text.
7. Nếu DB lỗi: vẫn báo video xuất thành công, kèm cảnh báo riêng “Video đã lưu nhưng chưa ghi được lịch sử” và đường dẫn copy được; ghi log chẩn đoán. Không đổi job thành thất bại hoặc chạy render lại vì lỗi lịch sử. Nếu bổ sung retry, giữ nguyên event_key và giới hạn retry.

Quyền sở hữu ghi:

- Editor và batch editor: backend route editor ghi; batch editor truyền loại nguồn được kiểm tra theo danh sách hợp lệ. Nguồn chỉ là metadata, không được dùng thay kiểm tra quyền xuất.
- Review/narration chạy độc lập: pipeline ghi ở cuối thành công. Hàng đợi gọi pipeline với cờ/context bỏ ghi bên dưới, rồi manager ghi khi xác nhận task thành công. Chọn một chủ thể cho mỗi output.
- Nhánh anti_copyright của hàng đợi phải được bao phủ dù không dùng cùng pipeline review.
- Comic review: ghi một bản output chính; không nhân đôi do copy dự phòng vào project.

Đọc đầy đủ cơ chế lỗi/return code của mỗi pipeline trước khi sửa. Đặc biệt kiểm tra các nhánh hiện chỉ xét `exists(final_output)`: cần bảo đảm file thực sự do lần chạy hiện tại tạo thành công. Không refactor toàn bộ engine chỉ để thêm lịch sử.

Nếu người dùng ghi đè một đường dẫn qua nhiều lần xuất, giữ nhiều sự kiện lịch sử. UI nói rõ đây là lịch sử thao tác, không phải hệ thống lưu các phiên bản video; nút Mở luôn mở file hiện tại ở đường dẫn đó. Không cam kết có thể phục hồi bản cũ.

## 6. Backend API và quyền đường dẫn

Tạo `export_history.py` cho persistence/service; `routes/export_history.py` cho Blueprint. Đăng ký trong `web_app.py`.

| API đề xuất | Hợp đồng |
|---|---|
| `GET /api/export-history?q=&source=&from=&to=&page=1&page_size=50` | `{items, total, page, page_size}`; sort ổn định mới nhất trước; ngày lọc được chuyển đúng timezone; ngày cuối bao gồm cả ngày |
| `POST /api/export-history/<id>/open` | Mở video theo path lấy từ DB; không nhận path tùy ý từ client |
| `POST /api/export-history/<id>/reveal` | Chọn file trong Explorer hoặc mở thư mục cha còn tồn tại |
| `DELETE /api/export-history/<id>` | Chỉ xóa bản ghi trong transaction |
| `POST /api/export-history/import/scan` | Quét thư mục đã chọn hợp lệ, trả scan ID; job nền có tiến độ/hủy nếu quét lớn |
| `GET /api/export-history/import/scan/<id>` | Lấy tiến độ và kết quả preview có phân trang |
| `POST /api/export-history/import/commit` | Nhập các candidate ID đã xác nhận từ scan phía server |

Mã lỗi rõ ràng: 400 tham số không hợp lệ, 403 không đủ quyền, 404 ID hoặc file không còn, 409 scan hết hạn, 500 lỗi nội bộ. Không trả traceback ra UI.

Không nới `is_path_allowed` cho toàn bộ filesystem. Đường dẫn trong bản ghi do backend tạo hoặc nhập có kiểm soát là căn cứ để mở chính file đó sau restart; không vì một bản ghi mà cấp quyền đọc/ghi mọi file trong thư mục. Kiểm tra extension video được phép, file thường, path canonical, không nhận URI hoặc command. Dùng `os.startfile` cho video trên Windows hoặc danh sách đối số subprocess phù hợp; không nối path vào PowerShell/cmd, không `shell=True`. Explorer reveal tái sử dụng cách triển khai đã có sau kiểm chứng.

Giữ nguyên mọi kiểm tra bản quyền của tác vụ xuất. Route mới cần theo chính sách quyền media hiện tại và đồng bộ frontend/backend; xem kỹ quyền editor/review/batch/comic để không vô tình chặn người dùng có gói hợp lệ chỉ cho một công cụ. Không tự thêm một feature trả phí mới chỉ cho trang lịch sử. Nếu dùng lại `_require_any_media_permission`, phải kiểm tra phạm vi vì hiện helper thiên về editor/review.

Không chạy stat hàng nghìn file trên mỗi GET. Chỉ kiểm tra trang hiện tại bằng worker giới hạn số lượng, cache ngắn, không để ổ mạng bị ngắt chặn toàn trang. Có trạng thái `unknown/checking/available/missing/unreachable`; thao tác Mở phải kiểm tra lại tại thời điểm bấm. Nếu hết ngân sách thời gian, trả unknown và cập nhật sau, không báo mất file sai.

## 7. Nhập video đã có từ trước

Modal gồm: danh sách thư mục đã chọn, nút Thêm thư mục, checkbox “Bao gồm thư mục con” mặc định tắt, nút Quét. Dùng native folder picker và cơ chế đăng ký đường dẫn hiện có. Sau quét hiển thị số file, tổng dung lượng và preview; người dùng xác nhận mới ghi DB.

Chỉ nhận định dạng video được ứng dụng hỗ trợ, chẳng hạn mp4/mov/mkv/webm/avi sau khi đối chiếu code. Không đi theo symlink/junction ra khỏi vùng đã chọn; tránh loop, thư mục không có quyền phải được bỏ qua có báo số lượng. Không đọc nội dung video, không gọi ffprobe cho mọi file chỉ để nhập lịch sử. Có Hủy, tiến độ và giới hạn scan hợp lý được giải thích trên UI.

Nhập lặp không nhân đôi file không đổi. Khóa import có thể dựa vào path chuẩn hóa + kích thước + mtime_ns; đây không phải checksum nội dung. Nếu cùng phiên bản file đã có trong lịch sử xuất thì báo “Đã có”, không tạo thêm imported row. Trước commit kiểm tra lại candidate, path, size, mtime và quyền; file đã thay đổi cần báo bỏ qua/scan lại. Không tin danh sách đường dẫn do client tự gửi.

Mục nhập cũ có nhãn “Video đã có”, “Ngày xuất: Không xác định”, “Ngày thêm vào lịch sử: …”, “Sửa đổi file: …”. Không gán mtime thành ngày xuất. Khi lọc ngày xuất, các mục không biết ngày xuất không được gán ngày giả; UI giải thích hoặc có bộ lọc riêng ngày thêm.

## 8. Frontend và thứ tự triển khai

1. Đọc chỉ dẫn repo, git diff, kiểm tra tất cả nơi tạo output cuối và cách app chọn mã gốc/overlay.
2. Tạo service SQLite với dependency injection, migration, transaction, chuẩn hóa path, query/pagination và test service.
3. Gắn hooks vào mọi luồng trong mục 2; xác lập ownership, context và idempotency trước khi làm UI.
4. Tạo Blueprint, kiểm tra quyền, mở/reveal theo ID; test API bằng Flask test client và mock mở ứng dụng.
5. Thêm HTML view, CSS có scope `.export-history-*`, JS `web/js/features/export_history.js`; tải script sau DOM theo pattern hiện có. Không thêm framework mới.
6. Gắn điều hướng app.js; search debounce khoảng 300ms; AbortController/request sequence để response cũ không ghi đè kết quả mới; reset page khi đổi filter; sửa page khi xóa hàng cuối.
7. Làm mới khi mở tab, nhấn Làm mới và nhận sự kiện thành công. Nếu polling thì chỉ khi view đang mở, dừng lúc ẩn và không tạo timer trùng.
8. Làm import scan/preview/commit và trạng thái file. Clipboard có fallback chọn văn bản thủ công và toast nếu copy thất bại.
9. Kiểm thử hồi quy, kiểm tra giao diện thực, cập nhật TODO mục chờ phát hành với đúng phần đã làm.

Không chèn filename/path vào `innerHTML`; dùng `textContent` và listener gắn theo ID. Kiểm tra cả trường hợp đường dẫn chứa dấu nháy, dấu `&`, chuỗi giống HTML và tiếng Việt.

Dev mặc định ưu tiên source gốc; release có thể ưu tiên `patches/active`. Không tự copy hàng loạt file sang overlay. Xác định đúng chế độ đang chạy, báo rõ cần restart backend/hard reload frontend. Khi được yêu cầu phát hành sau này, kiểm tra manifest/đóng gói bao gồm module và JS mới. Không tự tạo patch.zip, publish hoặc release cho yêu cầu triển khai tính năng.

## 9. Ma trận kiểm thử và tiêu chí đạt

| Nhóm | Ca kiểm thử bắt buộc | Kết quả mong đợi |
|---|---|---|
| Lưu bền vững | Xuất, đóng app, mở lại; đổi browser/origin | Lịch sử còn nguyên từ DB |
| Nhánh editor | Stream copy, encode, fallback encoder thành công | Mỗi lần xuất đúng một bản ghi |
| Nguồn xuất | Batch editor nhiều item; review; narration; batch queue từng preset; comic | Đủ file, đúng loại, không trùng pipeline/manager |
| Lỗi/hủy | FFmpeg lỗi, người dùng hủy, file rỗng; có file cũ cùng tên trước khi chạy lỗi | Không thêm lịch sử thành công giả |
| Đồng thời | Nhiều worker ghi cùng lúc, callback lặp event_key | Không mất record; một event chỉ một record |
| Xuất lại | Cùng tên/path nhưng run ID mới | Có hai sự kiện; mở file hiện tại, không hứa có bản cũ |
| Lỗi DB | Permission denied, DB lock, disk full/corrupt mô phỏng | Video vẫn thành công; cảnh báo không lưu lịch sử; không tự xóa DB hỏng |
| Đường dẫn | Dấu cách, tiếng Việt, dấu nháy, ký tự HTML, ổ khác | Hiển thị an toàn, mở đúng file, không thực thi lệnh |
| Path API | ID giả, path từ client, extension executable, symlink/junction ra ngoài | Từ chối phù hợp, không mở tùy ý |
| File biến mất | Xóa, đổi tên, tháo USB, ổ mạng offline, khôi phục ổ | Lịch sử giữ nguyên; trạng thái cập nhật; UI không treo |
| Xóa record | Xóa rồi kiểm tra file trên đĩa | File video còn nguyên |
| Tìm/lọc | Chữ hoa/thường, Unicode, `%`, `_`, không kết quả, ranh giới ngày local | Kết quả đúng và không SQL injection |
| Phân trang | 0/1/50/51/10.000 record; đổi filter khi ở trang cuối | Tổng và thứ tự ổn định, không trang trắng sai |
| Import | Thư mục con bật/tắt, folder lồng nhau, import lặp, file biến đổi trước commit, hủy scan | Không trùng, không ngày xuất giả, commit đúng candidate |
| Quyền | Gói hợp lệ từng công cụ, hết hạn, gọi API trực tiếp | Không bypass license; không chặn nhầm gói hợp lệ |
| UI | Loading/error/empty/missing; bàn phím; modal Escape; nhiều DPI | Dễ đọc, không che nút, không alert native |
| Hồi quy | Xuất video trước/sau, dừng xuất, chuyển tab, mở project, download history | Các tính năng cũ vẫn hoạt động |

Unit test dùng thư mục/DB tạm; mock subprocess/os.startfile. Integration test dùng video ngắn do test tạo và ffmpeg sẵn có, không render lại kho video của người dùng. Xác thực MP4 thực bằng ffprobe cho mẫu integration nếu công cụ sẵn có, không tăng chi phí mỗi lần mở lịch sử.

Đo thời gian truy vấn với 10.000 record trên máy test, tách thời gian DB khỏi kiểm tra file mạng; mục tiêu phản hồi truy vấn metadata trang 50 hàng dưới 500ms trên đĩa local, ghi rõ máy và kết quả thật thay vì khẳng định trước. File check không được làm mất khả năng tìm/lọc trong lúc chờ.

Chạy kiểm tra cú pháp Python/JS cho file thay đổi và test phù hợp; không coi compile-only là xác nhận tính năng hoạt động. Khi demo hoặc test giao diện trực tiếp, dùng trình duyệt có giao diện nhìn thấy theo chỉ dẫn repo. Nếu thiếu môi trường/giấy phép/tool, báo rõ ca chưa chạy và lý do; không ghi “đã pass” khi chỉ kiểm tra tĩnh.

## 10. Đầu ra AI thực hiện phải bàn giao

- Mã triển khai và danh sách file thay đổi, giải thích ngắn điểm tích hợp từng luồng.
- Ảnh UI thực sau triển khai: có dữ liệu, empty, file mất và modal import.
- Test report ghi lệnh chạy, kết quả thực tế, ca chưa chạy và giới hạn.
- Hướng dẫn người dùng: mở Lịch sử xuất video, tìm kiếm, mở thư mục, nhập file cũ; lịch sử tự động chỉ bắt đầu từ sau khi cài tính năng.
- TODO cập nhật đúng trạng thái chờ phát hành. Không tự phát hành.

Hoàn thành khi người dùng xuất thành công từ các luồng đã liệt kê, khởi động lại app vẫn tìm thấy đúng tên/đường dẫn, mở đúng file/thư mục, và nhập được video cũ mà không tạo thông tin ngày xuất sai.
