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
