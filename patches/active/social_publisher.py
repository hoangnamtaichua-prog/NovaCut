# -*- coding: utf-8 -*-
"""
NovaCut Social Media Video Publisher Engine
Hỗ trợ đăng tải video lên các mạng xã hội (YouTube Studio, TikTok, Facebook, Instagram, X, LinkedIn)
bằng cách mở Google Chrome trực tiếp với Profile người dùng chọn.

Nguyên tắc an toàn & bảo mật:
1. Tận dụng 100% phiên đăng nhập / cookie sẵn có trong Chrome của người dùng.
2. Tuyệt đối KHÔNG đọc, trích xuất, hiển thị hoặc lưu cookie/mật khẩu dạng văn bản.
3. Không cố gắng can thiệp hay vượt CAPTCHA/2FA của nền tảng.
4. Kiểm tra và giới hạn định dạng/đường dẫn tệp video an toàn.
"""

import os
import sys
import json
import shutil
import re
import time
import subprocess
import threading
from typing import Dict, List, Optional, Tuple, Any

# Đường dẫn thư mục gốc và thư mục dữ liệu người dùng
ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
USER_DATA_DIR = os.path.join(ROOT_DIR, "user_data")
HISTORY_FILE = os.path.join(USER_DATA_DIR, "social_publish_history.json")

_history_lock = threading.RLock()

# Danh sách các nền tảng mạng xã hội được hỗ trợ
SUPPORTED_PLATFORMS = {
    "youtube": {
        "id": "youtube",
        "name": "YouTube Studio",
        "category": "Video Dài & Shorts",
        "upload_url": "https://studio.youtube.com/channel/UC/videos/upload?d=ud",
        "direct_url": "https://studio.youtube.com",
        "supports_direct_upload": True,
        "max_title_len": 100,
        "max_desc_len": 5000,
        "has_separate_title": True,
        "privacy_options": [
            {"id": "public", "label": "Công khai (Public)", "desc": "Mọi người đều có thể tìm kiếm và xem video này"},
            {"id": "unlisted", "label": "Không công khai (Unlisted)", "desc": "Chỉ những ai có đường liên kết mới có thể xem"},
            {"id": "private", "label": "Riêng tư (Private)", "desc": "Chỉ bạn và những người bạn chọn mới có thể xem"}
        ],
        "default_privacy": "public",
        "icon": "youtube",
        "tips": "Mở YouTube Studio -> Kéo thả video hoặc nhấn 'TẢI VIDEO LÊN', sau đó dán tiêu đề & mô tả đã sao chép."
    },
    "tiktok": {
        "id": "tiktok",
        "name": "TikTok Studio",
        "category": "Shorts & Video Ngắn",
        "upload_url": "https://www.tiktok.com/creator-center/upload?from=webapp",
        "direct_url": "https://www.tiktok.com/creator-center/upload",
        "supports_direct_upload": True,
        "max_title_len": 0,  # TikTok dùng trường Caption gộp
        "max_desc_len": 2200,
        "has_separate_title": False,
        "privacy_options": [
            {"id": "public", "label": "Công khai (Mọi người)", "desc": "Tất cả mọi người đều có thể xem video"},
            {"id": "friends", "label": "Bạn bè", "desc": "Những người theo dõi bạn mà bạn cũng theo dõi lại"},
            {"id": "private", "label": "Chỉ mình tôi", "desc": "Chỉ một mình bạn có quyền xem video này"}
        ],
        "default_privacy": "public",
        "icon": "tiktok",
        "tips": "Kéo thả video vào khung đăng tải TikTok, dán Caption và Hashtags vào ô mô tả."
    },
    "facebook": {
        "id": "facebook",
        "name": "Facebook (Reels / Meta Suite)",
        "category": "Mạng Xã Hội",
        "upload_url": "https://business.facebook.com/latest/composer/",
        "direct_url": "https://www.facebook.com/",
        "supports_direct_upload": True,
        "max_title_len": 255,
        "max_desc_len": 2000,
        "has_separate_title": True,
        "privacy_options": [
            {"id": "public", "label": "Công khai (Public)", "desc": "Mọi người trên hoặc ngoài Facebook"},
            {"id": "friends", "label": "Bạn bè (Friends)", "desc": "Bạn bè của bạn trên Facebook"},
            {"id": "only_me", "label": "Chỉ mình tôi (Only Me)", "desc": "Chỉ hiển thị với bạn"}
        ],
        "default_privacy": "public",
        "icon": "facebook",
        "tips": "Mở Meta Business Suite Composer để đăng video Reel/Bài đăng trang chất lượng cao."
    },
    "instagram": {
        "id": "instagram",
        "name": "Instagram",
        "category": "Reels & Hình Ảnh",
        "upload_url": "https://www.instagram.com/",
        "direct_url": "https://www.instagram.com/",
        "supports_direct_upload": False,
        "max_title_len": 0,
        "max_desc_len": 2200,
        "has_separate_title": False,
        "privacy_options": [
            {"id": "public", "label": "Công khai", "desc": "Tài khoản công khai"},
            {"id": "private", "label": "Riêng tư", "desc": "Chỉ người theo dõi đã phê duyệt"}
        ],
        "default_privacy": "public",
        "icon": "instagram",
        "tips": "Bấm biểu tượng dấu cộng (+) 'Tạo' ở thanh bên trái Instagram để chọn video Reel."
    },
    "x_twitter": {
        "id": "x_twitter",
        "name": "X (Twitter)",
        "category": "Tin Tức & Mạng Xã Hội",
        "upload_url": "https://x.com/compose/post",
        "direct_url": "https://x.com/compose/post",
        "supports_direct_upload": False,
        "max_title_len": 0,
        "max_desc_len": 280,
        "has_separate_title": False,
        "privacy_options": [
            {"id": "public", "label": "Công khai (Public)", "desc": "Bất kỳ ai trên X"}
        ],
        "default_privacy": "public",
        "icon": "twitter",
        "tips": "Bấm biểu tượng Đăng bài -> Đính kèm video và dán nội dung kèm hashtag."
    },
    "linkedin": {
        "id": "linkedin",
        "name": "LinkedIn",
        "category": "Mạng Xã Hội Nghề Nghiệp",
        "upload_url": "https://www.linkedin.com/feed/?shareActive=true",
        "direct_url": "https://www.linkedin.com/feed/",
        "supports_direct_upload": False,
        "max_title_len": 0,
        "max_desc_len": 3000,
        "has_separate_title": False,
        "privacy_options": [
            {"id": "public", "label": "Công khai (Bất kỳ ai)", "desc": "Mọi thành viên trên LinkedIn"},
            {"id": "connections", "label": "Chỉ kết nối (Connections)", "desc": "Chỉ những người đã kết nối với bạn"}
        ],
        "default_privacy": "public",
        "icon": "linkedin",
        "tips": "Bấm 'Đăng bài viết' -> Chọn đính kèm Media Video và dán nội dung."
    }
}


def find_chrome_executable() -> Optional[str]:
    """
    Dò tìm tệp thực thi Google Chrome trên máy tính Windows.
    Kiểm tra các đường dẫn cài đặt chuẩn, biến môi trường và Windows Registry.
    """
    # 1. Thử qua PATH
    which_chrome = shutil.which("chrome") or shutil.which("chrome.exe") or shutil.which("google-chrome")
    if which_chrome and os.path.isfile(which_chrome):
        return os.path.abspath(which_chrome)

    # 2. Kiểm tra các thư mục Program Files / AppData phổ biến trên Windows
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    program_files_x86 = os.environ.get("PROGRAMFILES(X86)")

    if program_files:
        candidates.append(os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe"))
    if program_files_x86:
        candidates.append(os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe"))
    if local_appdata:
        candidates.append(os.path.join(local_appdata, "Google", "Chrome", "Application", "chrome.exe"))

    # Các đường dẫn cố định dự phòng
    candidates.extend([
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expanduser(r"~\AppData\Local\Google\Chrome\Application\chrome.exe")
    ])

    for path in candidates:
        if path and os.path.isfile(path):
            return os.path.abspath(path)

    # 3. Kiểm tra qua Windows Registry (nếu là Windows)
    if sys.platform.startswith("win"):
        try:
            import winreg
            reg_paths = [
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
                (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe")
            ]
            for root, subkey in reg_paths:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        val, _ = winreg.QueryValueEx(key, "")
                        if val and os.path.isfile(val):
                            return os.path.abspath(val)
                except OSError:
                    continue
        except Exception:
            pass

    return None


def get_chrome_user_data_dir() -> Optional[str]:
    """
    Trả về thư mục User Data của Google Chrome trên Windows.
    Thường nằm tại: %LOCALAPPDATA%\\Google\\Chrome\\User Data
    """
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        p = os.path.join(local_appdata, "Google", "Chrome", "User Data")
        if os.path.isdir(p):
            return os.path.abspath(p)

    default_p = os.path.expanduser(r"~\AppData\Local\Google\Chrome\User Data")
    if os.path.isdir(default_p):
        return os.path.abspath(default_p)

    return None


def list_chrome_profiles() -> List[Dict[str, Any]]:
    """
    Liệt kê danh sách các Chrome Profile có sẵn trên máy người dùng.
    Đọc từ tệp %LOCALAPPDATA%\\Google\\Chrome\\User Data\\Local State.
    """
    profiles: List[Dict[str, Any]] = []
    user_data_dir = get_chrome_user_data_dir()

    if not user_data_dir:
        # Nếu chưa tìm thấy thư mục hoặc Chrome chưa được mở lần nào
        return [
            {
                "id": "Default",
                "name": "Mặc định (Default)",
                "display_name": "Mặc định (Default Profile)",
                "email": "",
                "avatar_icon": "",
                "is_default": True
            }
        ]

    local_state_file = os.path.join(user_data_dir, "Local State")
    found_profiles_map = {}

    if os.path.isfile(local_state_file):
        try:
            with open(local_state_file, "r", encoding="utf-8", errors="ignore") as f:
                state = json.load(f)
            
            info_cache = state.get("profile", {}).get("info_cache", {})
            for profile_id, pdata in info_cache.items():
                name = pdata.get("name") or profile_id
                email = pdata.get("user_name") or pdata.get("hosted_domain") or ""
                gaia_name = pdata.get("gaia_name") or ""
                avatar = pdata.get("avatar_icon") or ""

                display_parts = []
                if gaia_name:
                    display_parts.append(gaia_name)
                elif name and name != profile_id:
                    display_parts.append(name)
                else:
                    display_parts.append(profile_id)

                if email and email not in display_parts:
                    display_parts.append(f"({email})")

                display_name = " ".join(display_parts) if display_parts else profile_id

                found_profiles_map[profile_id] = {
                    "id": profile_id,
                    "name": name,
                    "display_name": display_name,
                    "email": email,
                    "gaia_name": gaia_name,
                    "avatar_icon": avatar,
                    "is_default": (profile_id == "Default")
                }
        except Exception:
            pass

    # Quét dự phòng trực tiếp các thư mục có Preferences
    try:
        if os.path.isdir(user_data_dir):
            for entry in os.listdir(user_data_dir):
                full_path = os.path.join(user_data_dir, entry)
                if os.path.isdir(full_path):
                    pref_path = os.path.join(full_path, "Preferences")
                    if os.path.isfile(pref_path) and entry not in found_profiles_map:
                        pref_name = entry
                        pref_email = ""
                        try:
                            with open(pref_path, "r", encoding="utf-8", errors="ignore") as pf:
                                p_json = json.load(pf)
                                pref_name = p_json.get("profile", {}).get("name") or entry
                                pref_email = p_json.get("account_info", [{}])[0].get("email", "") if isinstance(p_json.get("account_info"), list) and p_json.get("account_info") else ""
                        except Exception:
                            pass
                        
                        disp = f"{pref_name} ({pref_email})" if pref_email else pref_name
                        found_profiles_map[entry] = {
                            "id": entry,
                            "name": pref_name,
                            "display_name": disp,
                            "email": pref_email,
                            "gaia_name": "",
                            "avatar_icon": "",
                            "is_default": (entry == "Default")
                        }
    except Exception:
        pass

    if found_profiles_map:
        # Sắp xếp: Default lên đầu, sau đó theo Profile 1, Profile 2, hoặc tên bảng chữ cái
        def sort_key(p):
            pid = p["id"]
            if pid == "Default":
                return (0, "")
            num_match = re.match(r"Profile\s*(\d+)", pid, re.IGNORECASE)
            if num_match:
                return (1, int(num_match.group(1)))
            return (2, p["display_name"].lower())

        profiles = sorted(found_profiles_map.values(), key=sort_key)
    else:
        profiles = [
            {
                "id": "Default",
                "name": "Mặc định (Default)",
                "display_name": "Mặc định (Default Profile)",
                "email": "",
                "avatar_icon": "",
                "is_default": True
            }
        ]

    return profiles


def clean_hashtags(tags: Any) -> str:
    """
    Chuẩn hóa danh sách hashtag từ chuỗi hoặc list.
    Ví dụ: 'reviewphim, phimhay' -> '#reviewphim #phimhay'
    """
    if not tags:
        return ""
    if isinstance(tags, list):
        tag_list = tags
    else:
        # Tách theo khoảng trắng hoặc dấu phẩy
        tag_list = re.split(r"[,\s;]+", str(tags).strip())

    cleaned = []
    for t in tag_list:
        t_clean = t.strip()
        if not t_clean:
            continue
        if not t_clean.startswith("#"):
            t_clean = f"#{t_clean}"
        # Loại bỏ các ký tự đặc biệt nguy hiểm trong hashtag
        t_clean = re.sub(r"[^\w#_]", "", t_clean)
        if len(t_clean) > 1 and t_clean not in cleaned:
            cleaned.append(t_clean)

    return " ".join(cleaned)


def prepare_publish_content(
    platform_id: str,
    title: str = "",
    description: str = "",
    caption: str = "",
    hashtags: Any = "",
    privacy: str = "public"
) -> Dict[str, Any]:
    """
    Định dạng và kiểm tra nội dung bài đăng theo tiêu chuẩn của từng mạng xã hội.
    Trả về nội dung đầy đủ và cảnh báo độ dài nếu vượt quá.
    """
    platform = SUPPORTED_PLATFORMS.get(platform_id)
    if not platform:
        raise ValueError(f"Nền tảng '{platform_id}' không được hỗ trợ.")

    clean_tags = clean_hashtags(hashtags)
    title_str = (title or "").strip()
    desc_str = (description or "").strip()
    caption_str = (caption or "").strip()

    warnings = []

    # Ghép nội dung theo định dạng nền tảng
    if platform.get("has_separate_title"):
        # YouTube, Facebook có tiêu đề riêng
        final_title = title_str or caption_str or "Video Mới"
        max_t = platform.get("max_title_len", 100)
        if len(final_title) > max_t:
            warnings.append(f"Tiêu đề vượt quá giới hạn ({len(final_title)}/{max_t} ký tự).")

        # Mô tả = Description + Hashtags
        desc_parts = []
        if desc_str:
            desc_parts.append(desc_str)
        elif caption_str and caption_str != final_title:
            desc_parts.append(caption_str)
        if clean_tags:
            desc_parts.append(clean_tags)

        final_desc = "\n\n".join(desc_parts)
        max_d = platform.get("max_desc_len", 5000)
        if len(final_desc) > max_d:
            warnings.append(f"Mô tả vượt quá giới hạn ({len(final_desc)}/{max_d} ký tự).")

        combined_text = f"{final_title}\n\n{final_desc}"
    else:
        # TikTok, Instagram, X, LinkedIn dùng 1 ô Caption tổng
        final_title = ""
        caption_parts = []
        if caption_str:
            caption_parts.append(caption_str)
        elif title_str:
            caption_parts.append(title_str)
        if desc_str and desc_str not in caption_parts:
            caption_parts.append(desc_str)
        if clean_tags:
            caption_parts.append(clean_tags)

        final_desc = "\n\n".join(caption_parts)
        max_d = platform.get("max_desc_len", 2200)
        if len(final_desc) > max_d:
            warnings.append(f"Nội dung Caption vượt quá giới hạn ({len(final_desc)}/{max_d} ký tự).")

        combined_text = final_desc

    # Quyền riêng tư
    valid_privacies = [p["id"] for p in platform.get("privacy_options", [])]
    if privacy not in valid_privacies:
        privacy = platform.get("default_privacy", "public")

    return {
        "platform_id": platform_id,
        "platform_name": platform.get("name"),
        "title": final_title,
        "description": final_desc,
        "caption": final_desc,
        "hashtags": clean_tags,
        "combined_text": combined_text,
        "privacy": privacy,
        "upload_url": platform.get("upload_url"),
        "direct_url": platform.get("direct_url"),
        "warnings": warnings,
        "char_count": len(combined_text)
    }


def launch_chrome_with_profile(
    profile_id: str,
    target_url: str,
    chrome_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Khởi chạy Google Chrome với Profile chỉ định và mở target_url.
    Không sử dụng Automation flags (để tránh bot flags của nền tảng).
    """
    if not chrome_path:
        chrome_path = find_chrome_executable()

    if not chrome_path or not os.path.isfile(chrome_path):
        return False, "Không tìm thấy trình duyệt Google Chrome trên máy tính của bạn. Vui lòng cài đặt Chrome để sử dụng tính năng này."

    # Xác thực profile_id an toàn: chỉ cho phép ký tự chữ cái, số, dấu gạch ngang, dấu gạch dưới và khoảng trắng
    clean_profile = str(profile_id or "Default").strip()
    if not re.match(r"^[a-zA-Z0-9_\-\. ]+$", clean_profile):
        clean_profile = "Default"

    # Chuẩn hóa URL mục tiêu
    target_url = target_url.strip()
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = "https://" + target_url

    cmd = [
        chrome_path,
        f"--profile-directory={clean_profile}",
        target_url
    ]

    try:
        # Sử dụng CREATE_NO_WINDOW hoặc khởi chạy độc lập tách biệt tiến trình
        creationflags = 0
        if sys.platform.startswith("win"):
            # DETACHED_PROCESS (0x00000008) để tiến trình Chrome sống độc lập với server Flask
            creationflags = 0x00000008

        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            close_fds=True
        )
        return True, f"Đã mở Google Chrome (Profile: {clean_profile}) thành công."
    except Exception as e:
        return False, f"Lỗi khởi chạy Google Chrome: {str(e)}"


def copy_text_to_windows_clipboard(text: str) -> bool:
    """
    Tiện ích sao chép văn bản (hoặc đường dẫn file) vào Clipboard của Windows
    giúp người dùng chỉ cần nhấn Ctrl+V vào ô chọn file / ô nhập liệu trên web.
    """
    if not text:
        return False
    if not sys.platform.startswith("win"):
        return False

    try:
        # Sử dụng lệnh clip của Windows
        process = subprocess.Popen(
            ["clip"],
            stdin=subprocess.PIPE,
            close_fds=True
        )
        process.communicate(input=text.encode("utf-16le"))
        return process.returncode == 0
    except Exception:
        return False


def load_publish_history() -> List[Dict[str, Any]]:
    """Đọc lịch sử thao tác đăng video từ user_data/social_publish_history.json."""
    with _history_lock:
        if not os.path.isfile(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []


def save_publish_history(history_list: List[Dict[str, Any]]) -> bool:
    """Lưu lịch sử thao tác an toàn nguyên tử (atomic write)."""
    with _history_lock:
        try:
            os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
            from routes.security import atomic_write_json
            # Giới hạn tối đa 100 bản ghi gần nhất
            trimmed = history_list[-100:]
            atomic_write_json(HISTORY_FILE, trimmed)
            return True
        except Exception:
            # Fallback nếu không nạp được atomic_write_json
            try:
                temp_file = f"{HISTORY_FILE}.tmp"
                with open(temp_file, "w", encoding="utf-8") as f:
                    json.dump(history_list[-100:], f, ensure_ascii=False, indent=2)
                if os.path.exists(HISTORY_FILE):
                    os.remove(HISTORY_FILE)
                os.rename(temp_file, HISTORY_FILE)
                return True
            except Exception:
                return False


def record_publish_action(
    platform_id: str,
    video_path: str = "",
    title: str = "",
    caption: str = "",
    profile_id: str = "Default",
    privacy: str = "public",
    status: str = "OPENED",
    message: str = ""
) -> Dict[str, Any]:
    """
    Ghi nhận một lượt thao tác vào lịch sử.
    Tuyệt đối không lưu mật khẩu, token hay cookie.
    """
    platform = SUPPORTED_PLATFORMS.get(platform_id, {})
    entry = {
        "id": f"pub_{int(time.time() * 1000)}",
        "timestamp": int(time.time()),
        "time_str": time.strftime("%d/%m/%Y %H:%M:%S", time.localtime()),
        "platform_id": platform_id,
        "platform_name": platform.get("name", platform_id),
        "video_path": video_path,
        "video_name": os.path.basename(video_path) if video_path else "",
        "title": title or caption or "Video",
        "profile_id": profile_id,
        "privacy": privacy,
        "status": status,
        "message": message
    }

    with _history_lock:
        history = load_publish_history()
        history.append(entry)
        save_publish_history(history)

    return entry
