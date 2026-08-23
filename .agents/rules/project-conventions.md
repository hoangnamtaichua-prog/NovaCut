# Project Conventions & Workflow Rules

## 1. Kiến trúc tổng thể & Luồng dữ liệu (Architecture & Data Flow)
- **Backend Framework:** Flask (Python). Sử dụng **Flask Blueprints** để chia nhỏ các route thành nhiều file riêng biệt (vd: `routes/video_edit.py`, `routes/tts.py`), tuyệt đối không nhồi nhét tất cả vào `web_app.py`.
- **Frontend:** ES6 Modules (Vanilla JS) + HTML/CSS. Code JS phải được module hóa (vd: `api.js`, `ui.js`, `editor.js`). Giao tiếp API qua fetch (JSON) và Server-Sent Events (SSE) cho các tác vụ xử lý video/audio dài.
- **State Management:** Backend quản lý luồng bằng SSE để push trạng thái liên tục. Frontend quản lý state cục bộ và hiển thị qua UI Terminal. 

## 2. Quy ước tổ chức thư mục & file
Mọi feature mới phải tuân theo cấu trúc sau, KHÔNG vứt file lẻ tẻ ra thư mục gốc:
- `routes/`: Chứa các Flask Blueprint endpoints.
- `services/`: Chứa logic xử lý chính (vd: `auto_edit_pipeline.py`, `ai_dubbing.py`).
- `utils/`: Các file hỗ trợ chung (ffmpeg, file system).
- `scripts/`: Chứa các script chạy một lần, patch, fix lỗi. Tuyệt đối không để file rác ở thư mục root.
- `web/`: Chứa Frontend (CSS, JS, HTML). Không viết JS/CSS inline vào HTML. Phải chia JS thành nhiều file module.

## 3. Quy ước Coding Style & Đặt tên
- **Python:** Tên file/module (`snake_case.py`), Tên biến/hàm (`snake_case`), Tên class (`PascalCase`). Ưu tiên có Type hints.
- **JavaScript:** Tên biến/hàm (`camelCase`), Constants (`UPPER_SNAKE_CASE`).
- **CSS:** Class name theo chuẩn `kebab-case`.

## 4. Quy ước Xử lý lỗi & Logging
- **Backend API:** Trả về chuẩn HTTP Status Code. Nếu lỗi, trả về JSON `{ "error": "Mô tả lỗi chi tiết" }`.
- **Backend SSE (Task dài):** Báo lỗi qua format chuẩn của hệ thống log: `yield f"data: 🛑 Lỗi chi tiết\n\n"`, sau đó dọn dẹp file temp và thoát an toàn.
- **Frontend:** Hiển thị qua modal/toast notification. Ghi log ra thẻ `#terminal` trên UI. Tuyệt đối không dùng `alert()` mặc định của trình duyệt.

## 5. Những việc TUYỆT ĐỐI KHÔNG được tự ý làm
- **KHÔNG** thay đổi cấu trúc thư mục gốc hiện tại (nếu chưa xin phép).
- **KHÔNG** đổi framework cốt lõi (ví dụ tự ý cài React hoặc đổi Flask sang FastAPI).
- **KHÔNG** chỉnh sửa trực tiếp các file config môi trường (`requirements.txt`, v.v.) trừ khi thật sự cần thiết và ĐÃ BÁO CÁO.
- **KHÔNG** để lại code debug như `print()` rác hoặc các file `.py` test ở thư mục root.

## 6. QUY TẮC XÁC NHẬN THAY ĐỔI (BẮT BUỘC ĐỐI VỚI MỌI AGENT)
> **[MỨC ĐỘ ƯU TIÊN CAO NHẤT]**
> Nếu trong quá trình làm việc, agent nhận thấy cần thay đổi/đi lệch khỏi flow hoặc quy ước đã định nghĩa trong file Rules này (ví dụ: đổi cấu trúc thư mục, đổi cách gọi API, thêm thư viện mới, đổi kiến trúc một phần), agent **PHẢI** dừng lại và trình bày rõ:
> - Đang định thay đổi gì
> - Lý do tại sao cần thay đổi (rule hiện tại không phù hợp ở đâu)
> - Ảnh hưởng nếu thay đổi
> 
> Sau đó agent **PHẢI** chờ tôi xác nhận bằng một câu trả lời rõ ràng qua chat (ví dụ: 'đồng ý', 'ok làm đi', 'không, giữ nguyên'). 
> Agent **TUYỆT ĐỐI KHÔNG** được tự cho là 'đã xác nhận' chỉ vì tôi bấm nút Accept/Submit trên UI, không phản hồi, hoặc im lặng — **im lặng KHÔNG PHẢI là đồng ý**.
> Nếu chưa có xác nhận bằng chat, agent không được tiến hành thay đổi đó, kể cả khi đây là bước nhỏ trong một task lớn hơn đã được giao.

## 7. Quy tắc Tái sử dụng Code (DRY - Don't Repeat Yourself)
- **Ưu tiên kế thừa:** Khi cần xây dựng một tính năng mới, agent BẮT BUỘC phải kiểm tra xem trong app đã có sẵn logic/hàm/module nào làm việc tương tự chưa (vd: hàm cắt video, hàm xử lý chuỗi, hàm gọi API TTS).
- **Tuyệt đối không viết lại từ đầu:** Nếu đã có sẵn, phải ưu tiên gọi lại (import) hàm đó hoặc kế thừa luồng cũ sang tính năng mới. Việc code đi code lại cùng một chức năng sẽ làm rác codebase và khó bảo trì.
