# -*- coding: utf-8 -*-
"""
Glossary Manager - Quản lý Từ Điển Tu Tiên, Danh Xưng Cổ Trang & Thuật Ngữ Phim Trung Quốc.
Hỗ trợ:
1. Nạp từ điển mặc định (Tu tiên, Cảnh giới, Danh xưng cổ trang, Cung đấu).
2. Tùy biến từ điển theo người dùng (lưu tại data/glossary_custom.json).
3. Đính kèm glossary vào Prompt AI khi dịch phụ đề.
4. Hậu kiểm (Post-Translation Regex Matcher): Tự động đối chiếu câu gốc và bản dịch để ép ghép chuẩn theo từ điển mà tốn 0 token.
"""

import os
import json
import re
from typing import Dict, List, Tuple

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
GLOSSARY_DIR = os.path.join(ROOT_DIR, 'data')
GLOSSARY_FILE = os.path.join(GLOSSARY_DIR, 'glossary_custom.json')

# Bộ từ điển tu tiên, cảnh giới và danh xưng hoàng thất / cổ trang chuẩn mực
DEFAULT_GLOSSARY: Dict[str, str] = {
    # --- DANH XƯNG HOÀNG THẤT & CUNG ĐẤU ---
    "朕": "Trẫm",
    "本王": "Bổn vương",
    "本座": "Bổn tọa",
    "本宫": "Bổn cung",
    "陛下": "Bệ hạ",
    "父皇": "Phụ hoàng",
    "母后": "Mẫu hậu",
    "老祖": "Lão tổ",
    "老夫": "Lão phu",
    "臣妾": "Thần thiếp",
    "微臣": "Vi thần",
    "爱卿": "Ái khanh",
    "九皇子": "Cửu hoàng tử",
    "大皇子": "Đại hoàng tử",
    "二皇子": "Nhị hoàng tử",
    "太子": "Thái tử",
    "禁军": "Cấm quân",
    "老东西": "Lão già kia",
    "奴才": "Nô tài",
    "奴婢": "Nô tỳ",
    "启奏陛下": "Khởi tấu bệ hạ",
    "吾皇万岁": "Ngô hoàng vạn tuế",

    # --- CẢNH GIỚI TU TIÊN TIÊU CHUẨN ---
    "练气": "Luyện Khí",
    "炼气": "Luyện Khí",
    "筑基": "Trúc Cơ",
    "金丹": "Kim Đan",
    "元婴": "Nguyên Anh",
    "化神": "Hóa Thần",
    "炼虚": "Luyện Hư",
    "合体": "Hợp Thể",
    "大乘": "Đại Thừa",
    "渡劫": "Độ Kiếp",
    "真仙": "Chân Tiên",
    "金仙": "Kim Tiên",
    "玄仙": "Huyền Tiên",
    "仙帝": "Tiên Đế",
    "魔尊": "Ma Tôn",
    "妖皇": "Yêu Hoàng",

    # --- THUẬT NGỮ TU TIÊN & MÔN PHÁI ---
    "道友": "Đạo hữu",
    "道侣": "Đạo lữ",
    "师尊": "Sư tôn",
    "师尊上": "Sư tôn",
    "师伯": "Sư bá",
    "师叔": "Sư thúc",
    "师兄": "Sư huynh",
    "师姐": "Sư tỷ",
    "师弟": "Sư đệ",
    "师妹": "Sư muội",
    "徒儿": "Đồ nhi",
    "掌门": "Chưởng môn",
    "宗主": "Tông chủ",
    "长老": "Trưởng lão",
    "圣女": "Thánh nữ",
    "圣子": "Thánh tử",
    "神识": "Thần thức",
    "灵根": "Linh căn",
    "丹田": "Đan điền",
    "经脉": "Kinh mạch",
    "法宝": "Pháp bảo",
    "灵宝": "Linh bảo",
    "灵石": "Linh thạch",
    "丹药": "Đan dược",
    "洞府": "Động phủ",
    "秘境": "Bí cảnh",
    "天劫": "Thiên kiếp",
    "雷劫": "Lôi kiếp",
    "走火入魔": "Tẩu hỏa nhập ma",
    "神魂": "Thần hồn",
    "元神": "Nguyên thần",
    "储物袋": "Túi trữ vật",
    "储物戒": "Nhẫn trữ vật",
    "阵法": "Trận pháp",
    "禁制": "Cấm chế",
    "符箓": "Phù lục",
    "傀儡": "Khôi lỗi",
    "鼎炉": "Đỉnh lô"
}


def load_glossary() -> Dict[str, str]:
    """Tải toàn bộ từ điển (mặc định gộp tùy biến người dùng)."""
    os.makedirs(GLOSSARY_DIR, exist_ok=True)
    glossary = dict(DEFAULT_GLOSSARY)
    if os.path.exists(GLOSSARY_FILE):
        try:
            with open(GLOSSARY_FILE, 'r', encoding='utf-8') as f:
                custom = json.load(f)
                if isinstance(custom, dict):
                    glossary.update(custom)
        except Exception as e:
            print(f"[Glossary] Lỗi đọc file {GLOSSARY_FILE}: {e}")
    return glossary


def save_glossary(custom_dict: Dict[str, str]) -> bool:
    """Lưu từ điển tùy biến của người dùng."""
    os.makedirs(GLOSSARY_DIR, exist_ok=True)
    try:
        with open(GLOSSARY_FILE, 'w', encoding='utf-8') as f:
            json.dump(custom_dict, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Glossary] Lỗi lưu glossary: {e}")
        return False


def filter_relevant_glossary(text_list: List[str], max_terms: int = 50) -> Dict[str, str]:
    """
    Trích xuất các từ trong từ điển thực sự xuất hiện trong danh sách câu thoại để đính kèm vào prompt,
    giúp tiết kiệm token tối đa và tập trung ngữ cảnh cho AI.
    """
    glossary = load_glossary()
    combined_text = " ".join(text_list)
    matched = {}
    
    # Sắp xếp các từ tiếng Trung có độ dài lớn trước để ưu tiên cụm từ dài (vd: 九皇子 trước 皇子)
    sorted_keys = sorted(glossary.keys(), key=lambda k: len(k), reverse=True)
    for k in sorted_keys:
        if k in combined_text:
            matched[k] = glossary[k]
            if len(matched) >= max_terms:
                break
    return matched


def post_process_with_glossary(src_text: str, trans_text: str, glossary: Dict[str, str] = None) -> str:
    """
    Hậu kiểm tự động (0 Token):
    Nếu câu gốc tiếng Trung chứa từ khóa quan trọng (như 朕, 金丹, 父皇, 本座...),
    đối chiếu xem bản dịch có đang dùng sai từ không và tự động hiệu chỉnh lại cho chuẩn xác.
    """
    if not trans_text or not src_text:
        return trans_text
        
    if glossary is None:
        glossary = load_glossary()
        
    res = trans_text
    
    # Một số quy tắc đối chiếu danh xưng cốt lõi
    rules = [
        # (Chữ Hán trong câu gốc, Danh xưng chuẩn tiếng Việt, Các từ dịch lỗi thường gặp của AI)
        ("朕", "Trẫm", [r"\btôi\b", r"\bta\b", r"\bông\b", r"\bmình\b"]),
        ("陛下", "Bệ hạ", [r"\bnhà vua\b", r"\bquốc vương\b", r"\bhoàng thượng\b"]),
        ("父皇", "Phụ hoàng", [r"\bcha\b", r"\bbố\b", r"\bba\b"]),
        ("母后", "Mẫu hậu", [r"\bmẹ\b", r"\bmá\b"]),
        ("本座", "Bổn tọa", [r"\bghế này\b", r"\bchỗ này\b", r"\btôi\b"]),
        ("本王", "Bổn vương", [r"\btôi\b", r"\bta đây\b"]),
        ("金丹", "Kim Đan", [r"\bviên thuốc vàng\b", r"\bthuốc vàng\b", r"\bđan vàng\b"]),
        ("元婴", "Nguyên Anh", [r"\btrẻ sơ sinh\b", r"\bđứa trẻ nguyên bản\b"]),
        ("筑基", "Trúc Cơ", [r"\bxây móng\b", r"\bxây nền\b"]),
        ("老祖", "Lão tổ", [r"\bông tổ già\b", r"\btổ tiên già\b"]),
        ("九皇子", "Cửu hoàng tử", [r"\bhoàng tử thứ chín\b", r"\bhoàng tử số 9\b"]),
        ("老东西", "Lão già kia", [r"\bđồ vật cũ\b", r"\bthứ cũ kỹ\b"])
    ]
    
    for cn_term, correct_term, wrong_patterns in rules:
        if cn_term in src_text:
            for pat in wrong_patterns:
                res = re.sub(pat, correct_term, res, flags=re.IGNORECASE)
                
    return res
