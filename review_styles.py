"""
Module Quản Lý Phong Cách Kịch Bản Review Phim (Review Styles & Tone Directives)
NovaCut - AI Video & Review Editor
"""

REVIEW_STYLES = [
    {
        "id": "dramatic",
        "name": "Kịch Tính & Hồi Hộp",
        "icon": "🎭",
        "badge": "Mặc định",
        "description": "Căng thẳng, nghẹt thở, nhấn mạnh plot twists và những cú lừa kinh điển",
        "directive": (
            "PHONG CÁCH VĂN PHONG BẮT BUỘC: KỊCH TÍNH & HỒI HỘP (DRAMATIC & SUSPENSEFUL)\n"
            "- Giọng văn căng thẳng, hồi hộp, tạo cảm giác nghẹt thở và tò mò cao độ cho người xem.\n"
            "- Sử dụng các câu cảm thán, câu hỏi tu từ, nhấn mạnh vào những bước ngoặt bất ngờ, hiểm nguy và cái giá phải trả của nhân vật.\n"
            "- Nhịp văn dồn dập ở cảnh hành động/cao trào, chậm rãi gieo rắc nghi vấn ở các khoảnh khắc bí ẩn."
        )
    },
    {
        "id": "humorous",
        "name": "Hài Hước & Cà Khịa",
        "icon": "😂",
        "badge": "Trend",
        "description": "Dí dỏm, châm biếm, ví von lầy lội các pha xử lý ngớ ngẩn của nhân vật",
        "directive": (
            "PHONG CÁCH VĂN PHONG BẮT BUỘC: HÀI HƯỚC, CHÂM BIẾM & CÀ KHỊA (HUMOROUS & SARCASTIC)\n"
            "- Giọng văn dí dỏm, lầy lội, có tính giải trí cao, tạo tiếng cười sảng khoái cho khán giả.\n"
            "- Cà khịa một cách duyên dáng các tình huống trớ trêu, quyết định ngớ ngẩn của nhân vật bằng các phép so sánh ví von hài hước, ngôn từ trẻ trung hot trend.\n"
            "- Vẫn đảm bảo tóm tắt đúng mạch truyện và không xuyên tạc nội dung chính."
        )
    },
    {
        "id": "deep_analysis",
        "name": "Phân Tích & Triết Lý",
        "icon": "🧠",
        "badge": "Chuyên sâu",
        "description": "Đi sâu vào tâm lý, ẩn dụ nghệ thuật, thông điệp nhân văn và bài học cuộc sống",
        "directive": (
            "PHONG CÁCH VĂN PHONG BẮT BUỘC: PHÂN TÍCH CHUYÊN SÂU & TRIẾT LÝ (DEEP ANALYSIS & PSYCHOLOGICAL)\n"
            "- Giọng văn điềm đạm, có chiều sâu, mang tính học thuật và chiêm nghiệm sâu sắc.\n"
            "- Đào sâu phân tích tâm lý nhân vật, động cơ ngầm, những mâu thuẫn nội tâm, ẩn dụ nghệ thuật và bức tranh đạo đức của bộ phim.\n"
            "- Đưa ra những góc nhìn đa chiều, câu hỏi suy ngẫm cho người xem sau mỗi biến cố."
        )
    },
    {
        "id": "fast_paced",
        "name": "Tóm Tắt Nhanh (Mì Ăn Liền)",
        "icon": "⚡",
        "badge": "Shorts/TikTok",
        "description": "Tiết tấu siêu tốc, câu ngắn gọn, dồn dập, đi thẳng vào các cảnh then chốt",
        "directive": (
            "PHONG CÁCH VĂN PHONG BẮT BUỘC: TÓM TẮT NHANH, DỒN DẬP & MÌ ĂN LIỀN (FAST-PACED RECAP)\n"
            "- Câu ngắn gọn, súc tích, nhịp độ dồn dập liên tục, không lan man dài dòng.\n"
            "- Bỏ qua các chi tiết phụ, tập trung 100% vào chuỗi hành động và kết quả then chốt của từng phân đoạn.\n"
            "- Tiết tấu như một chuyến tàu lượn siêu tốc giữ chân người xem từ giây đầu đến giây cuối."
        )
    },
    {
        "id": "horror",
        "name": "Kinh Dị & Rùng Rợn",
        "icon": "👻",
        "badge": "Rùng rợn",
        "description": "Không khí u ám, lạnh lẽo, cảm giác rình rập và đe dọa vô hình",
        "directive": (
            "PHONG CÁCH VĂN PHONG BẮT BUỘC: KINH DỊ, U ÁM & RÙNG RỢN (HORROR & DARK THRILLER)\n"
            "- Không khí kể chuyện lạnh gáy, u tối, gợi mở cảm giác sợ hãi và đe dọa vô hình.\n"
            "- Dùng các từ ngữ miêu tả xúc giác, thị giác rùng rợn, cảm giác bất an tột cùng trước cái chết và thực thể tà ác.\n"
            "- Giọng văn thì thầm, bí hiểm, đẩy cao sự căng thẳng trước các phân cảnh jumpscare hoặc cái chết kinh hoàng."
        )
    },
    {
        "id": "emotional",
        "name": "Tình Cảm & Lắng Đọng",
        "icon": "💖",
        "badge": "Xúc động",
        "description": "Giàu cảm xúc, chạm đến trái tim, đồng cảm sâu sắc với số phận nhân vật",
        "directive": (
            "PHONG CÁCH VĂN PHONG BẮT BUỘC: TÌNH CẢM, XÚC ĐỘNG & LẮNG ĐỌNG (EMOTIONAL & TOUCHING)\n"
            "- Giọng văn tha thiết, giàu cảm xúc, chạm đến trái tim người nghe.\n"
            "- Khắc họa sâu sắc nỗi đau, tình yêu thương, sự hy sinh và những giọt nước mắt của nhân vật trước số phận nghiệt ngã.\n"
            "- Dành những khoảng lặng lắng đọng, câu từ giàu chất thơ và sự đồng cảm chân thành."
        )
    },
    {
        "id": "custom",
        "name": "Tùy Chỉnh Riêng",
        "icon": "✍️",
        "badge": "Custom",
        "description": "Người dùng tự định nghĩa văn phong và chỉ thị kịch bản riêng theo ý muốn",
        "directive": ""
    }
]

def get_style_by_id(style_id):
    """Tìm thông tin cấu hình style theo id."""
    if not style_id:
        return REVIEW_STYLES[0]
    for s in REVIEW_STYLES:
        if s["id"] == str(style_id).strip().lower():
            return s
    return REVIEW_STYLES[0]

def get_style_directive(style_id="dramatic", custom_directive=None):
    """
    Trả về khối văn bản chỉ thị phong cách (Directive) để chèn vào prompt AI.
    """
    style_id = str(style_id or "dramatic").strip().lower()
    if style_id == "custom":
        if custom_directive and custom_directive.strip():
            return f"PHONG CÁCH VĂN PHONG TÙY CHỈNH TỪ NGƯỜI DÙNG:\n{custom_directive.strip()}"
        return REVIEW_STYLES[0]["directive"]
    
    style_obj = get_style_by_id(style_id)
    return style_obj["directive"]
