import os
import cv2
import numpy as np
from PIL import Image

def is_row_blank(row, threshold=245, black_threshold=15):
    """Kiểm tra dòng ảnh có phải màu trắng (hoặc đen) đồng nhất không"""
    mean_val = np.mean(row)
    std_val = np.std(row)
    # Trắng đồng nhất hoặc đen đồng nhất
    if (mean_val >= threshold and std_val < 10) or (mean_val <= black_threshold and std_val < 10):
        return True
    return False

def slice_webtoon_image(img_bgr, min_panel_height=180, max_panel_height=2000, gap_threshold=20):
    """
    Cắt ảnh webtoon dải dài thành các ô tranh riêng biệt theo dải phân cách trắng/đen ngang.
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Nếu ảnh có chiều cao bình thường (< 800px) thì coi như 1 panel luôn
    if h <= 800:
        return [img_bgr]

    blank_mask = np.zeros(h, dtype=bool)
    for y in range(h):
        row = gray[y, :]
        blank_mask[y] = is_row_blank(row)

    # Tìm các khoảng hở (gaps)
    cuts = [0]
    in_gap = False
    gap_start = 0

    for y in range(h):
        if blank_mask[y]:
            if not in_gap:
                in_gap = True
                gap_start = y
        else:
            if in_gap:
                in_gap = False
                gap_len = y - gap_start
                if gap_len >= gap_threshold:
                    cut_pos = gap_start + gap_len // 2
                    # Chỉ cắt nếu khoảng cách tới nhát cắt trước đó đủ lớn
                    if cut_pos - cuts[-1] >= min_panel_height:
                        cuts.append(cut_pos)

    cuts.append(h)

    # Trích xuất các lát cắt
    panels = []
    for i in range(len(cuts) - 1):
        y1 = cuts[i]
        y2 = cuts[i + 1]
        panel_h = y2 - y1

        # Nếu panel quá dài (vẫn chưa có gap), chia đều thành các đoạn hợp lý
        if panel_h > max_panel_height:
            num_sub = int(np.ceil(panel_h / 1200))
            sub_h = panel_h // num_sub
            for sub_i in range(num_sub):
                sy1 = y1 + sub_i * sub_h
                sy2 = min(y1 + (sub_i + 1) * sub_h, y2)
                if sy2 - sy1 >= min_panel_height:
                    panels.append(img_bgr[sy1:sy2, :])
        elif panel_h >= min_panel_height:
            panels.append(img_bgr[y1:y2, :])

    return panels if panels else [img_bgr]

def detect_manga_panel_boxes(img_bgr, min_area_ratio=0.06):
    """
    Nhận diện các ô tranh (khung chữ nhật) trong trang Manga bằng OpenCV Contours.
    """
    h, w = img_bgr.shape[:2]
    total_area = w * h
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

    # Cân bằng sáng và nhị phân hóa
    _, thresh = cv2.threshold(gray, 230, 255, cv2.THRESH_BINARY_INV)

    # Tìm contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area / total_area >= min_area_ratio:
            x, y, bw, bh = cv2.boundingRect(cnt)
            # Tránh các khung viền bao trọn toàn bộ trang
            if bw < w * 0.98 or bh < h * 0.98:
                boxes.append((y, x, bw, bh))

    if not boxes:
        return []

    # Sắp xếp theo thứ tự từ trên xuống dưới, từ phải sang trái (chuẩn Manga đọc)
    boxes.sort(key=lambda b: (b[0] // 100, -b[1]))

    panels = []
    for y, x, bw, bh in boxes:
        # Thêm padding nhẹ nếu có thể
        px1 = max(0, x - 4)
        py1 = max(0, y - 4)
        px2 = min(w, x + bw + 4)
        py2 = min(h, y + bh + 4)
        panels.append(img_bgr[py1:py2, px1:px2])

    return panels

def extract_panels_stream(raw_image_paths, output_panel_dir, check_stop=None):
    """
    Generator xử lý danh sách các trang ảnh truyện và trích xuất thành danh sách panel ô tranh,
    yield ('progress', (pct, message)) từng trang và yield ('done', extracted_panels) khi kết thúc.
    """
    os.makedirs(output_panel_dir, exist_ok=True)
    extracted_panels = []
    panel_counter = 1
    total_pages = len(raw_image_paths)

    for page_idx, img_path in enumerate(raw_image_paths, start=1):
        if check_stop and check_stop():
            break

        pct = int((page_idx / max(1, total_pages)) * 100)
        page_name = os.path.basename(img_path)
        yield ('progress', (pct, f"✂️ [Cắt Ô Tranh] Đang xử lý trang {page_idx}/{total_pages} ({pct}%) • {page_name} • Đã tạo {panel_counter - 1} ô tranh"))

        try:
            # Đọc ảnh UTF-8 an toàn trên Windows
            img_bytes = np.fromfile(img_path, dtype=np.uint8)
            img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
            if img is None:
                continue

            h, w = img.shape[:2]
            aspect = h / max(1, w)

            # Bỏ qua nếu là banner quảng cáo vuông (1024x1024) hoặc icon/banner ngang hẹp
            if w < 320 or h < 250:
                continue
            if 0.93 <= (w / h) <= 1.07 and min(w, h) >= 300:
                continue
            if w >= 2.8 * h and h < 300:
                continue

            # Nếu là ảnh dải dọc Webtoon (tỉ lệ chiều cao > 2.0)
            if aspect > 2.0 or h > 1600:
                sub_panels = slice_webtoon_image(img)
            else:
                # Thử tìm ô tranh Manga
                sub_panels = detect_manga_panel_boxes(img)
                # Nếu không tìm thấy ô tranh rõ ràng, giữ nguyên trang hoặc chia 2 nửa
                if not sub_panels:
                    if aspect > 1.3:
                        sub_panels = [img]
                    else:
                        sub_panels = [img]

            # Lưu các panel đã cắt
            for p_img in sub_panels:
                ph, pw = p_img.shape[:2]
                if ph < 80 or pw < 80:
                    continue

                panel_filename = f"panel_{panel_counter:04d}.jpg"
                panel_save_path = os.path.join(output_panel_dir, panel_filename)

                # Lưu ảnh chất lượng cao
                _, encoded_img = cv2.imencode('.jpg', p_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                with open(panel_save_path, 'wb') as f:
                    f.write(encoded_img)

                extracted_panels.append({
                    "id": panel_counter,
                    "filename": panel_filename,
                    "path": panel_save_path,
                    "source_page": os.path.basename(img_path),
                    "width": pw,
                    "height": ph
                })
                panel_counter += 1

        except Exception as e:
            print(f"[PanelDetector] Lỗi xử lý ảnh {img_path}: {e}")

    yield ('done', extracted_panels)

def process_and_extract_panels(raw_image_paths, output_panel_dir, check_stop=None):
    """
    Xử lý danh sách các trang ảnh truyện và trích xuất thành danh sách panel ô tranh (đồng bộ).
    """
    panels = []
    for event_type, payload in extract_panels_stream(raw_image_paths, output_panel_dir, check_stop=check_stop):
        if event_type == 'done':
            panels = payload
    return panels
