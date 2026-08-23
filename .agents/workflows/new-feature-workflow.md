# Quy Trình Phát Triển Tính Năng Mới (New Feature Workflow)

Để đảm bảo tính nhất quán và tránh phá vỡ các chức năng cũ, MỌI tính năng mới đều phải được thực hiện theo đúng 4 bước sau. Agent **KHÔNG ĐƯỢC** tự ý bỏ qua bất kỳ bước nào.

## BƯỚC 1: Phân tích & Viết Kế Hoạch (Implementation Plan)
Trước khi viết bất kỳ dòng code nào, agent phải:
- Khảo sát các file liên quan (tìm kiếm xem codebase hiện tại đã có logic tương tự chưa).
- Lên cấu trúc dữ liệu, các hàm/endpoint cần tạo. Đảm bảo tuân thủ cấu trúc thư mục quy định (Flask Blueprint cho Backend, ES6 Module cho Frontend).
- Xuất một file `implementation_plan.md` để user duyệt.

## BƯỚC 2: User Duyệt (Approval)
- Agent bắt buộc phải dừng lại và chờ user xác nhận "ok" hoặc "đồng ý" qua chat. (Tuyệt đối tuân thủ Quy Tắc Xác Nhận ở phần 6 của `project-conventions.md`).
- Nếu user yêu cầu sửa đổi kế hoạch, agent phải sửa lại bản kế hoạch và chờ duyệt lại.

## BƯỚC 3: Viết Code Logic (Backend / Script ẩn)
- Chuyển logic chính vào một file `.py` riêng trong thư mục `services/`.
- Nếu có API Endpoint, tạo một Blueprint mới trong `routes/` và đăng ký vào `web_app.py`.
- Thiết lập cơ chế chạy nền (nếu mất thời gian) và báo cáo tiến trình (progress) về Frontend qua cơ chế SSE. Lỗi phải được bắt bằng `try...except` và trả về JSON/SSE có kiểm soát.

## BƯỚC 4: Tích Hợp Giao Diện (Frontend)
- Chỉ sau khi logic Backend đã được kiểm thử ổn định, mới bắt đầu sửa file HTML và CSS.
- Mọi logic JS liên quan đến feature này phải được viết trong một file ES6 module riêng rẽ (vd: `feature_abc.js`) nằm trong thư mục `web/`, sau đó import vào file chính. Không nhồi nhét code vào file `app.js` hiện tại.
- Hook các event listener và test thông báo UI (Toast, Terminal logs).
