import os
import sys
import json
import re
import time
import subprocess
import requests
import numpy as np
import cv2
import ffmpeg_installer

# Load RapidOCR an toàn nếu có
_ocr_engine = None
def get_ocr_instance():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _ocr_engine = RapidOCR()
        except Exception:
            _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None

STYLE_PROMPTS = {
    "badass": "Phong cách Review Truyện Tranh Bá Đạo, Giật Gân: Văn phong lôi cuốn, xưng hô 'anh main', 'thằng cha này', ngôn từ dí dỏm, châm biếm sâu cay và cực kỳ kịch tính theo chuẩn các kênh Review Truyện triệu view trên TikTok/YouTube.",
    "dramatic": "Phong cách Kịch Tính & Hồi Hộp: Tập trung vào căng thẳng, mâu thuẫn đối đầu, bí ẩn và những cú twist bất ngờ.",
    "humorous": "Phong cách Hài Hước & Cà Khịa: Sử dụng ngôn từ bắt trend giới trẻ, ví von lầy lội, tạo tiếng cười sảng khoái.",
    "summary": "Phong cách Tóm Tắt Chi Tiết: Rõ ràng, mạch lạc, thuật lại trọn vẹn diễn biến của chương truyện một cách khách quan."
}

AD_SPONSOR_KEYWORDS = [
    'shopee', 'lazada', 'tiki', 'zakad', 'cocoon', 'neutrogena', 'my pham', 'mỹ phẩm',
    'kem duong', 'kem dưỡng', 'cap nuoc', 'cấp nước', 'beauty', 'freeship', 'giam gia', 'giảm giá',
    'khuyen mai', 'khuyến mãi', 'dat hang', 'đặt hàng', 'mua ngay', 'san pham', 'sản phẩm',
    'quang cao', 'quảng cáo', 'nhan vao', 'nhấn vào', 'ung ho web', 'ủng hộ web',
    'kinh phi', 'kinh phí', 'baotangtruyen', 'sang web', 'nhom dich', 'nhóm dịch',
    'dich boi', 'dịch bởi', 'truyen duoc dich', 'truyện được dịch', 'donate', 'momo', 'stk',
    'ngan hang', 'ngân hàng', 'chuyen khoan', 'chuyển khoản', 'zalo', 'telegram',
    'ra chap som hon', 'ra chap sớm hơn', 'theo doi page', 'fanpage'
]

def is_ad_or_credit_text(text):
    if not text:
        return False
    t_lower = text.lower()
    return any(kw in t_lower for kw in AD_SPONSOR_KEYWORDS)

def inpaint_text_from_image(img_bgr, ocr_boxes):
    """
    Xóa sạch chữ thoại trong bong bóng thoại bằng thuật toán Telea inpainting.
    """
    if not ocr_boxes or img_bgr is None:
        return img_bgr

    mask = np.zeros(img_bgr.shape[:2], dtype=np.uint8)
    for box in ocr_boxes:
        pts = np.array(box, dtype=np.int32)
        cv2.fillPoly(mask, [pts], 255)

    # Nở nhẹ viền 4px để xóa sạch viền nét chữ
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)

    return cv2.inpaint(img_bgr, mask, inpaintRadius=4, flags=cv2.INPAINT_TELEA)

def inpaint_single_panel(panel_path):
    """
    Xóa chữ khung thoại cho một ô tranh cụ thể.
    """
    try:
        ocr = get_ocr_instance()
        img_bytes = np.fromfile(panel_path, dtype=np.uint8)
        img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
        if img is None:
            return panel_path

        ocr_res, _ = ocr(img) if ocr else ([], None)
        if not ocr_res:
            return panel_path

        boxes = [item[0] for item in ocr_res if item and len(item) > 1 and item[1].strip()]
        if not boxes:
            return panel_path

        clean_img = inpaint_text_from_image(img, boxes)
        dir_name = os.path.dirname(panel_path)
        base_name = os.path.basename(panel_path)
        clean_name = base_name.replace('.jpg', '_clean.jpg')
        if clean_name == base_name:
            clean_name = 'clean_' + base_name
        clean_path = os.path.join(dir_name, clean_name)

        _, encoded = cv2.imencode('.jpg', clean_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
        with open(clean_path, 'wb') as f:
            f.write(encoded)

        return clean_path
    except Exception as e:
        logger.error(f"Error inpainting single panel {panel_path}: {e}")
        return panel_path

def extract_ocr_generator(panels_info, max_panels=60, inpaint_bubbles=False, check_stop=None):
    """
    Generator trích xuất chữ thoại trên các ô tranh bằng RapidOCR,
    yield ('progress', (pct, message)) từng ô tranh và yield ('done', panel_texts) khi hoàn tất.
    """
    ocr = get_ocr_instance()
    panel_texts = []
    total_panels = min(len(panels_info), max_panels)

    for idx, p in enumerate(panels_info[:max_panels], start=1):
        if check_stop and check_stop():
            break

        pct = int((idx / max(1, total_panels)) * 100)
        p_name = p.get('filename', f"panel_{idx}")
        inpaint_suffix = " • Đang xóa chữ thoại (Inpaint)" if inpaint_bubbles else ""
        yield ('progress', (pct, f"🔍 [AI OCR & Phân Tích] Đang quét ô tranh {idx}/{total_panels} ({pct}%) • {p_name}{inpaint_suffix}"))

        text_content = ""
        is_text_heavy = False
        clean_path = ""
        clean_filename = ""
        ocr_boxes = []

        if ocr:
            try:
                # Đọc ảnh an toàn UTF-8
                img_bytes = np.fromfile(p['path'], dtype=np.uint8)
                img = cv2.imdecode(img_bytes, cv2.IMREAD_COLOR)
                if img is not None:
                    ocr_res, _ = ocr(img)
                    if ocr_res:
                        lines = []
                        total_box_area = 0
                        ih, iw = img.shape[:2]
                        for item in ocr_res:
                            if item and len(item) > 1 and item[1].strip():
                                lines.append(item[1].strip())
                                box = item[0]
                                ocr_boxes.append(box)
                                try:
                                    xs = [pt[0] for pt in box]
                                    ys = [pt[1] for pt in box]
                                    bw = max(xs) - min(xs)
                                    bh = max(ys) - min(ys)
                                    total_box_area += (bw * bh)
                                except Exception:
                                    pass

                        text_content = " | ".join(lines)
                        area_ratio = total_box_area / max(1, (iw * ih))
                        if area_ratio >= 0.22 or len(lines) >= 6:
                            is_text_heavy = True

                        if inpaint_bubbles and ocr_boxes:
                            try:
                                clean_img = inpaint_text_from_image(img, ocr_boxes)
                                p_dir = os.path.dirname(p['path'])
                                clean_filename = p['filename'].replace('.jpg', '_clean.jpg')
                                clean_path = os.path.join(p_dir, clean_filename)
                                _, encoded = cv2.imencode('.jpg', clean_img, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
                                with open(clean_path, 'wb') as cf:
                                    cf.write(encoded)
                            except Exception:
                                pass
            except Exception as e:
                pass

        is_ad = is_ad_or_credit_text(text_content)
        panel_texts.append({
            "panel_id": p['id'],
            "filename": clean_filename if (inpaint_bubbles and clean_filename) else p['filename'],
            "path": clean_path if (inpaint_bubbles and clean_path) else p['path'],
            "raw_filename": p['filename'],
            "raw_path": p['path'],
            "text": "" if is_ad else text_content,
            "is_ad": is_ad,
            "is_text_heavy": is_text_heavy,
            "clean_path": clean_path,
            "clean_filename": clean_filename
        })

    yield ('done', panel_texts)

def extract_ocr_from_panels(panels_info, max_panels=60, inpaint_bubbles=False, check_stop=None):
    """
    Trích xuất chữ thoại trên các ô tranh bằng RapidOCR (đồng bộ).
    """
    panel_texts = []
    for event_type, payload in extract_ocr_generator(panels_info, max_panels=max_panels, inpaint_bubbles=inpaint_bubbles, check_stop=check_stop):
        if event_type == 'done':
            panel_texts = payload
    return panel_texts

def generate_comic_review_script(panel_texts, api_config, style="badass", target_minutes=3, chapter_scope="5", chapter_count=5, is_all=False, filter_text_heavy=True, pacing="balanced", check_stop=None):
    """
    Gọi AI LLM để tạo kịch bản review phân đoạn theo từng ô tranh dựa trên số chap hoặc toàn bộ truyện,
    hỗ trợ tự động lọc bỏ bớt các ô tranh chứa nhiều khung thoại rườm rà.
    """
    openai_key = api_config.get('openaiKey', '').strip()
    openai_base = api_config.get('openaiBaseUrl', 'https://api.openai.com/v1').strip().rstrip('/')
    openai_model = api_config.get('openaiModel', 'gpt-5.6-luna-pro-batch').strip()

    # Tự động chuẩn hóa Base URL & Model thông minh
    if openai_key.startswith('sk-proj-') and 'openrouter.ai' in openai_base:
        openai_base = 'https://api.openai.com/v1'
        if not openai_model or openai_model in ['gpt-4o-mini', 'gpt-4o']:
            openai_model = 'gpt-5.6-luna-pro-batch'
    elif openai_key.startswith('sk-or-'):
        openai_base = 'https://openrouter.ai/api/v1'
        if not openai_model or openai_model in ['gpt-4o-mini', 'gpt-4o', 'openrouter/free']:
            openai_model = 'gpt-5.6-luna-pro-batch'
    if not openai_model or openai_model in ['gpt-4o-mini', 'gpt-4o']:
        openai_model = 'gpt-5.6-luna-pro-batch'
    elif openai_model == 'gpt-5.6-luna':
        openai_model = 'gpt-5.6-luna-pro-batch'

    style_directive = STYLE_PROMPTS.get(style, STYLE_PROMPTS['badass'])

    # Tính toán thời lượng mục tiêu và chỉ thị phạm vi theo số chap
    if is_all or chapter_scope == 'all':
        calc_minutes = 10
        scope_directive = """📌 PHẠM VI REVIEW: TOÀN BỘ TRUYỆN (FULL SERIES RECAP TỪ ĐẦU ĐẾN ĐẠI KẾT CỤC).
Kịch bản cần bao quát trọn vẹn mạch truyện:
- Phần 1: Khởi đầu câu chuyện, thân phận & nghịch cảnh bi đát ban đầu của nhân vật chính.
- Phần 2: Cơ duyên bước ngoặt, thức tỉnh năng lực bí truyền & hành trình cày cấp đột phá.
- Phần 3: Đại chiến nghẹt thở với trùm cuối & Đại kết cục của toàn bộ tác phẩm."""
    elif chapter_scope == '1':
        calc_minutes = 3
        scope_directive = """📌 PHẠM VI REVIEW: 1 CHƯƠNG TRUYỆN DUY NHẤT.
Kịch bản cần tập trung phân tích sâu các tình tiết kịch tính, câu thoại đắt giá, pha hành động gay cấn và kết thúc bằng cú Hook hóng chap sau cực mạnh."""
    elif chapter_scope == '3':
        calc_minutes = 5
        scope_directive = """📌 PHẠM VI REVIEW: COMBO 3 CHƯƠNG LIÊN TIẾP.
Kịch bản liên kết mượt mà diễn biến giữa các chap, giữ nhịp độ nhanh và cuốn hút từ mở màn đến cao trào."""
    elif chapter_scope == '5':
        calc_minutes = 7
        scope_directive = """📌 PHẠM VI REVIEW: COMBO 5 CHƯƠNG LIÊN TIẾP.
Kịch bản kể lại trọn vẹn một nhánh cốt truyện quan trọng xuyên suốt 5 chương, làm nổi bật diễn biến thăng tiến của nhân vật."""
    elif chapter_scope == '10':
        calc_minutes = 10
        scope_directive = """📌 PHẠM VI REVIEW: COMBO 10 CHƯƠNG LIÊN TIẾP.
Kịch bản trường thiên bao quát một đại sự kiện lớn hoặc một giải đấu / phụ bản quan trọng của câu chuyện."""
    else:
        calc_minutes = max(3, min(15, round(int(chapter_count) * 1.5)))
        scope_directive = f"""📌 PHẠM VI REVIEW: {chapter_count} CHƯƠNG TRUYỆN.
Kịch bản tổng hợp mạch truyện của {chapter_count} chương thành một video review liền mạch, hấp dẫn."""

    target_words = max(180, calc_minutes * 120)

    # Chuẩn bị dữ liệu text từ các panel (LOẠI BỎ TRIỆT ĐỂ Ô TRANH QUẢNG CÁO)
    transcripts = []
    for item in panel_texts:
        if item.get('is_ad'):
            continue
        if item['text']:
            transcripts.append(f"[Ô tranh #{item['panel_id']}]: {item['text']}")
        else:
            transcripts.append(f"[Ô tranh #{item['panel_id']}]: (Diễn biến hành động / cảnh quay)")

    all_dialogue = "\n".join(transcripts[:120])

    pacing_guide = ""
    if filter_text_heavy:
        pacing_guide = """- QUY TẮC TINH GỌN: BỎ QUA các bong bóng thoại nhỏ, đối thoại rườm rà. TẬP TRUNG TỐI ĐA vào việc kể câu chuyện lôi cuốn, làm nổi bật các phân cảnh hành động, biểu cảm căng thẳng và bước ngoặt nhân vật. Không đọc lại nguyên văn từng câu thoại nhỏ."""

    prompt = f"""Bạn là một Biên kịch Review Truyện Tranh (Manga, Manhwa, Webtoon) triệu view chuyên nghiệp hàng đầu.
Nhiệm vụ của bạn là viết một kịch bản Video Review Truyện Tranh cực kỳ lôi cuốn, giữ chân người xem từ giây đầu tiên đến giây cuối cùng.

{style_directive}

{scope_directive}

MỤC TIÊU KỊCH BẢN:
- Độ dài kịch bản: Khoảng {target_words} từ (~{calc_minutes} phút xem).
- Chia thành từng câu phân cảnh (Scene Beats). Mỗi câu thoại review PHẢI gắn liền với một ô tranh (panel_id) tương ứng nhất trong truyện để tạo nhịp phim chuẩn xác.
- Câu mở đầu (Hook) phải gây tò mò tột độ.
- Văn phong tự nhiên như người đang kể chuyện cuốn hút, không dùng từ ngữ dịch máy thô ráp.
{pacing_guide}

NỘI DUNG DIỄN BIẾN VÀ LỜI THOẠI TRÍCH XUẤT TỪ CÁC Ô TRANH:
{all_dialogue}

BẮT BUỘC TRẢ VỀ DUY NHẤT 1 MẢNG JSON HỢP LỆ (Không thêm bất kỳ chữ dẫn dắt, markdown ngoài block JSON):
[
  {{
    "panel_id": 1,
    "script_text": "Mở đầu câu chuyện, chúng ta thấy anh chàng Lâm Phong đang trong tình cảnh vô cùng trớ trêu."
  }},
  {{
    "panel_id": 2,
    "script_text": "Ai mà ngờ được, chỉ sau một giấc ngủ, hắn đã xuyên không vào đúng cơ thể của một tên phế vật."
  }}
]
"""

    beats = None
    if openai_key:
        try:
            headers = {
                "Authorization": f"Bearer {openai_key}",
                "Content-Type": "application/json"
            }
            if 'openrouter.ai' in openai_base:
                headers["HTTP-Referer"] = "https://novacut.app"
                headers["X-Title"] = "NovaCut Comic Review"

            payload = {
                "model": openai_model,
                "messages": [
                    {"role": "system", "content": "You are a professional comic review scriptwriter. Always reply with valid JSON array."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.75
            }

            url = f"{openai_base}/chat/completions"
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                raw_content = data['choices'][0]['message']['content'].strip()
                cleaned = re.sub(r'^```json\s*', '', raw_content, flags=re.IGNORECASE)
                cleaned = re.sub(r'^```\s*', '', cleaned)
                cleaned = re.sub(r'\s*```$', '', cleaned)
                match = re.search(r'(\[.*\])', cleaned, re.DOTALL)
                if match:
                    cleaned = match.group(1)
                parsed = json.loads(cleaned)
                if isinstance(parsed, list) and len(parsed) > 0:
                    beats = parsed
            else:
                print(f"[ComicReviewAI] API call status {resp.status_code}: {resp.text[:120]}")
        except Exception as api_err:
            print(f"[ComicReviewAI] Lỗi kết nối AI: {api_err}")

    if not beats:
        beats = _generate_fallback_beats(panel_texts, style, target_words, filter_text_heavy=filter_text_heavy, pacing=pacing)

    return beats

def _generate_fallback_beats(panel_texts, style="badass", target_words=300, filter_text_heavy=True, pacing="balanced"):
    valid_panels = [p for p in panel_texts if p.get('panel_id') and not p.get('is_ad')]
    if not valid_panels:
        valid_panels = [p for p in panel_texts if p.get('panel_id')]
    if not valid_panels:
        valid_panels = [{"panel_id": i+1, "text": ""} for i in range(12)]

    # Bỏ bớt ô tranh chỉ toàn khung thoại nếu có đủ ô tranh nghệ thuật
    if filter_text_heavy and len(valid_panels) > 12:
        art_panels = [p for p in valid_panels if not p.get('is_text_heavy')]
        if len(art_panels) >= 8:
            valid_panels = art_panels

    # Xác định số lượng phân cảnh mục tiêu theo pacing
    if pacing == 'compact':
        max_beats = 16
    elif pacing == 'detailed':
        max_beats = 40
    else:
        max_beats = 26

    total = len(valid_panels)
    step = max(1, total // max_beats)
    selected = valid_panels[::step][:max_beats]

    beats = []
    hooks = [
        "Mở đầu câu chuyện, chúng ta lập tức bước vào một thế giới tràn ngập những bí ẩn và biến cố khó lường.",
        "Ngay từ những khung hình đầu tiên, không khí căng thẳng đã bao trùm toàn bộ câu chuyện.",
        "Ai có thể ngờ được rằng, một biến cố kinh hoàng sắp sửa ập đến thay đổi hoàn toàn vận mệnh của nhân vật chính."
    ]

    for idx, p in enumerate(selected):
        p_id = p.get('panel_id', idx + 1)
        dialogue = str(p.get('text') or '').strip()

        if idx == 0:
            text = hooks[0]
            if dialogue:
                text += f" Tại đây, nhân vật chính chạm mặt biến cố: '{dialogue[:60]}'."
        elif idx == len(selected) - 1:
            text = "Diễn biến tiếp theo sẽ ra sao? Những bí mật nào còn đang ẩn giấu? Các bạn hãy bấm theo dõi để đón chờ chương mới nhất nhé!"
        else:
            if dialogue and len(dialogue) > 4:
                text = f"Tình thế ngày càng trở nên gay cấn hơn khi những lời đe dọa vang lên: '{dialogue[:80]}'."
            else:
                transitions = [
                    "Ngay sau đó, nhịp độ câu chuyện được đẩy lên cao trào với một loạt tình tiết bất ngờ.",
                    "Trước tình thế hiểm nghèo, nhân vật chính lập tức có hành động táo bạo khiến đối thủ phải bất ngờ.",
                    "Mọi ánh mắt đều đổ dồn vào khung cảnh này khi bí mật dần được hé lộ.",
                    "Những đòn tấn công dồn dập khiến cho cục diện trận đấu hoàn toàn đảo chiều."
                ]
                text = transitions[idx % len(transitions)]

        beats.append({
            "panel_id": p_id,
            "script_text": text
        })

    return beats

def generate_voice_for_text(text, voice_id, output_path, speed=1.0):
    """
    Sinh file âm thanh từ văn bản qua ai_dubbing (hỗ trợ Edge-TTS, Kokoro, Local Voice, v.v.).
    Đảm bảo tốc độ đọc (speed) được áp dụng chuẩn xác 100%.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    text = text.strip()
    if not text:
        text = "..."

    # 1. Thử qua ai_dubbing (hỗ trợ toàn bộ giọng Kokoro, Local Voice, Edge-TTS, RVC của NovaCut)
    try:
        import ai_dubbing
        res = ai_dubbing.synthesize_sentence(text, voice_id=voice_id, speed=speed, output_path=output_path)
        if res and os.path.exists(output_path) and os.path.getsize(output_path) > 100:
            return True
    except Exception as e:
        print(f"[ComicTTS] ai_dubbing error ({e}), falling back to Edge-TTS...")

    # 2. Fallback trực tiếp Edge-TTS (kèm tham số rate chuẩn xác)
    try:
        import edge_tts
        import asyncio
        edge_voice = voice_id.replace('edge_', '') if (voice_id.startswith('edge_') or 'neural' in voice_id.lower() or voice_id.startswith('vi-') or voice_id.startswith('en-')) else "vi-VN-NamMinhNeural"
        rate_val = int(round((speed - 1.0) * 100))
        rate_str = f"{rate_val:+d}%"
        communicate = edge_tts.Communicate(text, edge_voice, rate=rate_str)
        asyncio.run(communicate.save(output_path))
        return os.path.exists(output_path) and os.path.getsize(output_path) > 100
    except Exception as e:
        raise RuntimeError(f"Không thể tạo âm thanh TTS: {e}")

def get_audio_duration(audio_path):
    """
    Lấy thời lượng file audio chính xác qua ffprobe.
    """
    try:
        bin_dir = os.path.join(ffmpeg_installer.ROOT_DIR, 'bin')
        ffprobe = os.path.join(bin_dir, 'ffprobe.exe') if os.name == 'nt' else 'ffprobe'
        cmd = [
            ffprobe, '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            audio_path
        ]
        out = subprocess.check_output(cmd, **ffmpeg_installer.get_stealth_subprocess_kwargs()).decode('utf-8').strip()
        dur = float(out)
        return max(0.5, round(dur, 2))
    except Exception:
        # Fallback ước tính theo dung lượng file mp3 (128kbps ~ 16KB/s)
        try:
            sz = os.path.getsize(audio_path)
            return max(1.0, round(sz / 16000.0, 2))
        except Exception:
            return 3.0
