# UI/UX Rule
- All notification boxes, alerts, and system prompts must follow the tone/theme of the app (dark mode, modern UI) rather than native browser alerts. Always use custom modal/toast notification systems in the UI to ensure visual consistency.

# GPU / CUDA Compatibility Rule
- Whenever a user encounters a `CUDA error: no kernel image is available for execution on the device` or a similar PyTorch CUDA version mismatch error, DO NOT immediately default to a CPU fallback in the code without asking.
- Instead, first check their GPU model (e.g. via `nvidia-smi`) and determine if the currently installed PyTorch version matches the GPU's compute capability (e.g., RTX 50-series requires newer PyTorch with cu124+).

# License & Feature Permission Enforcement Rule
- Tất cả các chức năng cốt lõi của ứng dụng (Xuất video Biên tập phim, Review Phim, Tạo giọng đọc TTS, Trích xuất OCR/ASR, Dịch phụ đề AI, Đồng bộ CapCut, Clone Voice Studio) PHẢI ĐƯỢC BẢO VỆ CHẶT CHẼ ở cả 2 tầng:
  1. Tầng Giao diện (Frontend): Bắt buộc gọi `checkFeaturePermission(featureName, featureTitle)` trước khi người dùng thực hiện bất kỳ tác vụ nào. Nếu bản quyền hết hạn (`EXPIRED`), chưa kích hoạt (`UNLICENSED`), lỗi đồng hồ (`CLOCK_TAMPERED`) hoặc gói cước không có quyền (`features[featureName] == False`), hiển thị ngay thông báo Dark Mode (`showAlertModal`) và tự động mở bảng Nâng Cấp Bản Quyền (`licenseModal`).
  2. Tầng Máy chủ (Backend): Bắt buộc kiểm tra quyền bằng `license_manager.check_permission(feature_name)` tại các Flask API route. Tuyệt đối không cho phép bypass qua API trực tiếp; nếu không đủ quyền, trả về mã lỗi `403 Forbidden` hoặc dừng luồng Stream ngay lập tức.

# Release & Patch Publishing Rule
- CHỈ phát hành bản cập nhật mới (chạy `publish_patch.py` hoặc tạo GitHub Release) KHI VÀ CHỈ KHI người dùng yêu cầu rõ ràng (ví dụ: "hãy phát hành bản mới", "đẩy lên bản cập nhật mới").
- TUYỆT ĐỐI KHÔNG tự ý đóng gói patch.zip hay tạo Release mới khi chưa có chỉ thị từ người dùng.

# GitHub Release & Developer Secrets Rule
- GitHub Personal Access Token (PAT) dùng để đẩy code và phát hành bản cập nhật được lưu trữ bảo mật tại tệp cục bộ `.github_token` trên máy Dev (được bảo vệ bởi `.gitignore`). Các agent khi thực hiện phát hành sẽ tự động đọc token từ tệp này qua `scripts/publish_patch.py` hoặc `os.path.join(ROOT_DIR, '.github_token')`.
- TUYỆT ĐỐI KHÔNG BAO GIỜ đưa `.github_token` hay bất kỳ token/key quản trị nào vào bản cập nhật máy khách (`patch.zip`). Tệp `scripts/publish_patch.py` bắt buộc duy trì `.github_token` trong danh sách loại trừ `PATCH_EXCLUDES`.

# Bug Fix & Feature Tracking Rule (Changelog Staging)
- Mỗi khi người dùng báo lỗi hoặc yêu cầu chỉnh sửa/thêm tính năng mới: Sau khi hoàn thành việc sửa mã nguồn, PHẢI ghi nhận và lưu lại chi tiết các thay đổi vào file `TODO.md` (mục "CÁC THAY ĐỔI ĐANG CHỜ PHÁT HÀNH").
- Khi người dùng ra lệnh phát hành bản mới ("hãy cập nhật", "phát hành bản mới"), hãy đọc danh sách các mục đã ghi nhận này để tổng hợp changelog đầy đủ, chính xác nhất cho phiên bản tiếp theo.

# No Codex Rule (Gỡ Bỏ Hoàn Toàn Codex)
- Tuyệt đối KHÔNG sử dụng, không gọi và không kích hoạt OpenAI Codex (hoặc bất kỳ quy trình nào liên quan đến Codex CLI, codex-runner, codex-debug-loop, codex-plan-review, codex-implementation-review) trong toàn bộ quá trình làm việc. Toàn bộ các tác vụ phân tích nguyên nhân, lập kế hoạch, viết mã nguồn, sửa lỗi và đối soát mã nguồn đều được thực hiện trực tiếp, độc lập và nhanh chóng.

# Autonomous Claude AI Collaboration Rule (Tự Động Phối Hợp Cùng Claude)
- Bất cứ khi nào người dùng gõ lệnh `/claude <nội dung>`, hỏi "hỏi Claude", "nhờ Claude viết", "Claude review", hoặc yêu cầu tối ưu hóa kịch bản review phim:
  1. Tự động kích hoạt Claude Runner (`node "C:\Users\hoang\.gemini\config\plugins\claude\scripts\claude-runner.mjs" task "<nội dung>"`) để Claude xử lý trực tiếp.
  2. Báo cáo nguyên văn (verbatim) phản hồi từ Claude cho người dùng.
