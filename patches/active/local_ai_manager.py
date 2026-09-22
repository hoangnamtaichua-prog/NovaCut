"""
Local AI Manager for NovaCut:
Quản lý dịch vụ AI cục bộ (Ollama) và mô hình ngôn ngữ chuyên sâu cho dịch thuật / rút gọn phụ đề (Qwen 2.5).
Hỗ trợ chạy 100% Offline trên GPU (NVIDIA RTX / CUDA / DirectML), không phụ thuộc vào internet và không tốn chi phí API.
"""

import os
import sys
import json
import time
import shutil
import subprocess
import threading
import urllib.request
import urllib.error

OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
DEFAULT_TRANSLATE_MODEL = "qwen2.5:3b"
HEAVY_TRANSLATE_MODEL = "qwen2.5:7b"
LIGHTWEIGHT_TRANSLATE_MODEL = "qwen2.5:1.5b"
LOCAL_CHUNK_SIZE = 35
LOCAL_CONCURRENCY = 4

def get_ollama_executable():
    """Tìm đường dẫn tệp thực thi ollama trên máy tính Windows/Linux"""
    # 1. Kiểm tra PATH hệ thống
    which_path = shutil.which("ollama") or shutil.which("ollama.exe")
    if which_path and os.path.exists(which_path):
        return os.path.abspath(which_path)

    # 2. Kiểm tra các thư mục mặc định trên Windows
    if sys.platform == "win32":
        user_profile = os.environ.get("USERPROFILE", "")
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        candidates = [
            os.path.join(local_app_data, "Programs", "Ollama", "ollama.exe"),
            os.path.join(user_profile, "AppData", "Local", "Programs", "Ollama", "ollama.exe"),
            r"C:\Program Files\Ollama\ollama.exe",
            r"C:\Program Files (x86)\Ollama\ollama.exe",
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return os.path.abspath(c)
    return None

def is_ollama_service_running(timeout=1.5):
    """Kiểm tra xem dịch vụ Ollama cục bộ có đang lắng nghe không"""
    url = f"{OLLAMA_BASE_URL}/api/version"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as res:
            if res.status == 200:
                data = json.loads(res.read().decode("utf-8"))
                return True, data.get("version", "unknown")
    except Exception:
        pass
    return False, None

def ensure_ollama_service_started():
    """Tự động khởi động Ollama service nếu chưa chạy nhưng đã cài đặt, bật Flash Attention & 4 Parallel Slots"""
    running, version = is_ollama_service_running(timeout=1.0)
    if running:
        return True, "Dịch vụ Ollama đang chạy."

    exe = get_ollama_executable()
    if not exe:
        return False, "Chưa cài đặt Ollama trên máy tính."

    try:
        flags = 0
        if sys.platform == "win32":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        # Cấu hình tối ưu GPU cho RTX 50-series (Flash Attention + 4 Parallel Slots)
        env = os.environ.copy()
        env["OLLAMA_FLASH_ATTENTION"] = "1"
        env["OLLAMA_NUM_PARALLEL"] = "4"
        env["OLLAMA_KEEP_ALIVE"] = "60m"

        # Chạy ollama serve trong luồng ngầm
        subprocess.Popen([exe, "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags, env=env)
        
        # Chờ tối đa 6 giây để service sẵn sàng
        for _ in range(12):
            time.sleep(0.5)
            r, v = is_ollama_service_running(timeout=1.0)
            if r:
                return True, f"Đã khởi động dịch vụ Ollama ({v})."
        return False, "Đã gửi lệnh khởi chạy nhưng dịch vụ Ollama chưa phản hồi kịp thời."
    except Exception as exc:
        return False, f"Lỗi khởi chạy Ollama: {exc}"

def get_installed_models():
    """Lấy danh sách các mô hình AI đã tải trong Ollama"""
    url = f"{OLLAMA_BASE_URL}/api/tags"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2.5) as res:
            if res.status == 200:
                data = json.loads(res.read().decode("utf-8"))
                models = []
                for m in data.get("models", []):
                    name = m.get("name", "")
                    size_gb = round(m.get("size", 0) / (1024 ** 3), 2)
                    models.append({
                        "name": name,
                        "size_gb": size_gb,
                        "modified_at": m.get("modified_at", ""),
                        "is_qwen": "qwen" in name.lower()
                    })
                return models
    except Exception:
        pass
    return []

def get_local_ai_status():
    """Tổng hợp trạng thái toàn diện của Local AI (Ollama + Qwen)"""
    exe = get_ollama_executable()
    is_installed = exe is not None
    is_running, version = is_ollama_service_running()
    models = get_installed_models() if is_running else []
    
    # Tìm xem đã có model Qwen nào chưa
    qwen_models = [m for m in models if m.get("is_qwen")]
    best_model = None
    if qwen_models:
        # Ưu tiên 3b (nhanh 3x-4x) -> 7b -> 1.5b -> các model khác
        qwen3b = next((m for m in qwen_models if "3b" in m["name"]), None)
        qwen7b = next((m for m in qwen_models if "7b" in m["name"]), None)
        qwen15b = next((m for m in qwen_models if "1.5b" in m["name"]), None)
        best_model = qwen3b["name"] if qwen3b else (qwen7b["name"] if qwen7b else (qwen15b["name"] if qwen15b else qwen_models[0]["name"]))

    return {
        "installed": is_installed,
        "executable_path": exe,
        "running": is_running,
        "version": version,
        "models": models,
        "has_qwen": len(qwen_models) > 0,
        "recommended_model": best_model or DEFAULT_TRANSLATE_MODEL,
        "base_url": OLLAMA_BASE_URL
    }

def stream_pull_model(model_name=DEFAULT_TRANSLATE_MODEL):
    """
    Generator kéo model về qua Ollama API (hỗ trợ SSE stream tiến độ % cho frontend)
    """
    ensure_ollama_service_started()
    url = f"{OLLAMA_BASE_URL}/api/pull"
    payload = json.dumps({"name": model_name, "stream": True}).encode("utf-8")
    
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3600) as resp:
            for line in resp:
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8").strip())
                    status = data.get("status", "")
                    total = data.get("total", 0)
                    completed = data.get("completed", 0)
                    pct = int(completed / total * 100) if total > 0 else 0
                    
                    yield {
                        "status": status,
                        "total": total,
                        "completed": completed,
                        "percent": pct
                    }
                    if status == "success":
                        break
                except Exception:
                    pass
    except Exception as e:
        yield {"error": f"Lỗi tải mô hình {model_name}: {str(e)}"}

def _translate_single_chunk(chunk, model, system_prompt, user_prefix, rescue_prefix, target_lang, client):
    """Dịch và tự động cứu hộ cho một mẻ (chunk 35 dòng) phụ đề độc lập với giao thức khóa ID chống lệch dòng"""
    import re
    if not chunk:
        return {}, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    chunk_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    lines = []
    for s in chunk:
        sid = str(s.get("id", "")).strip()
        txt = str(s.get("text", "")).replace("\r", "").replace("\n", " ").strip()
        lines.append(f"{sid}|{txt}")

    user_content = f"{user_prefix}\n" + "\n".join(lines)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ],
            temperature=0.2,
            max_tokens=1500,
            frequency_penalty=0.25
        )
        raw_text = response.choices[0].message.content or ""
        u = getattr(response, "usage", None)
        if u:
            chunk_usage["prompt_tokens"] += (getattr(u, "prompt_tokens", 0) or 0)
            chunk_usage["completion_tokens"] += (getattr(u, "completion_tokens", 0) or 0)
            chunk_usage["total_tokens"] += (getattr(u, "total_tokens", 0) or 0)
    except Exception:
        raw_text = ""

    chunk_map = {}
    for line in raw_text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\[?(\d+)\]?[\s\|\.\:\-\)]\s*(.*)$", line)
        if match:
            sid, trans_text = match.group(1), match.group(2).strip()
            chunk_map[str(sid)] = trans_text

    # Tự động cứu hộ (Auto-Rescue & ID-Locking): Nếu trong chunk này có dòng bị model bỏ sót, gộp dòng hoặc còn dính chữ Hán
    missing_items = []
    for s in chunk:
        sid_str = str(s.get("id", "")).strip()
        trans = chunk_map.get(sid_str, "")
        if not trans or (target_lang == "vi" and re.search(r'[\u4e00-\u9fff]', trans)):
            missing_items.append(s)

    if missing_items:
        try:
            rescue_lines = [f"{str(s.get('id', '')).strip()}|{str(s.get('text', '')).replace(chr(13), '').replace(chr(10), ' ').strip()}" for s in missing_items]
            rescue_user = f"{rescue_prefix}\n" + "\n".join(rescue_lines)
            r_res = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": rescue_user}
                ],
                temperature=0.2,
                max_tokens=1000,
                frequency_penalty=0.25
            )
            r_text = r_res.choices[0].message.content or ""
            ru = getattr(r_res, "usage", None)
            if ru:
                chunk_usage["prompt_tokens"] += (getattr(ru, "prompt_tokens", 0) or 0)
                chunk_usage["completion_tokens"] += (getattr(ru, "completion_tokens", 0) or 0)
                chunk_usage["total_tokens"] += (getattr(ru, "total_tokens", 0) or 0)
            for r_l in r_text.splitlines():
                rm = re.match(r"^\[?(\d+)\]?[\s\|\.\:\-\)]\s*(.*)$", r_l.strip())
                if rm:
                    r_id, r_val = rm.group(1), rm.group(2).strip()
                    if r_val:
                        chunk_map[str(r_id)] = r_val
        except Exception:
            pass

    # Dọn sạch triệt để ký tự Hán tự còn sót lại và khử lặp từ (degeneration loop) nếu có
    for sid_k, trans_v in list(chunk_map.items()):
        cleaned = trans_v
        if target_lang == "vi" and re.search(r'[\u4e00-\u9fff]', cleaned):
            cleaned = re.sub(r'[\u4e00-\u9fff]+', '', cleaned).strip()
        # Khử hiện tượng mô hình AI bị kẹt vòng lặp sinh từ (vd: 'tập tập tập tập...')
        cleaned = re.sub(r'(\b\w+\b)(?:\s+\1){3,}', r'\1', cleaned).strip()
        chunk_map[sid_k] = cleaned

    return chunk_map, chunk_usage

def translate_subtitles_local(subtitles, model=None, source_lang="zh", target_lang="vi", translation_style="cinema", return_usage=False):
    """
    Dịch danh sách phụ đề bằng mô hình Qwen 2.5 cục bộ qua OpenAI-compatible API của Ollama.
    Tối ưu hóa toàn diện (Cải tiến 1, 2, 3):
    1. Tự động dùng model Qwen 2.5 3B (nhanh gấp 3-4 lần bản 7B trên RTX 5060).
    2. Giao thức khóa ID dạng ID|Text chống lệch dòng, bảo toàn nguyên vẹn từng dòng OCR (không gộp).
    3. Tiêm bảng thuật ngữ cổ trang hoàng gia chuẩn xác (Bệ hạ, Trẫm, Thần thiếp, Cửu hoàng tử...).
    4. Xử lý đa luồng Concurrency = 4 trên GPU RTX 5060 đẩy tốc độ lên tối đa.
    """
    if not subtitles:
        if return_usage:
            return [], {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        return []

    ensure_ollama_service_started()

    if not model:
        status = get_local_ai_status()
        model = status.get("recommended_model") or DEFAULT_TRANSLATE_MODEL

    import openai
    client = openai.OpenAI(
        api_key="ollama",
        base_url=f"{OLLAMA_BASE_URL}/v1",
        timeout=360.0
    )

    lang_names = {
        "zh": "tiếng Trung",
        "vi": "tiếng Việt",
        "en": "tiếng Anh",
        "ja": "tiếng Nhật",
        "ko": "tiếng Hàn",
        "auto": "ngôn ngữ gốc"
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    translation_style = str(translation_style or 'cinema').strip().lower()

    if target_lang == "vi":
        system_prompt = (
            "你是专业影视字幕与古装/现代短剧翻译专家。\n"
            "任务：将用户提供的中文台词逐行翻译成自然流畅、地道生动的越南语（Tiếng Việt）字幕。\n\n"
            "【古装与影视核心词汇对照表（严格强制遵守）】：\n"
            "- 陛下 / 皇上 -> Bệ hạ / Hoàng thượng (绝对严禁翻译成'Thượng đế')\n"
            "- 朕 -> Trẫm\n"
            "- 臣妾 -> Thần thiếp (绝对严禁翻译成'con dâu')\n"
            "- 皇子 / 九皇子 -> hoàng tử / Cửu hoàng tử\n"
            "- 驾崩 -> băng hà\n"
            "- 封棺 -> đóng nắp quan tài / đóng quan tài\n"
            "- 诈尸 -> xác chết đội mồ sống lại / bật dậy / sống lại\n"
            "- 狗皇帝 -> tên hoàng đế chó chết / cẩu hoàng đế\n"
            "- 垂帘听政 -> buông rèm nhiếp chính\n"
            "- 满脑子 -> trong đầu toàn là / đầu óc toàn là\n"
            "- 废铜烂铁 -> sắt vụn đồng nát\n"
            "- 女鬼 -> nữ quỷ / ma nữ\n"
            "- 吓唬 / 吓人 -> dọa / dọa người / dọa nạt\n"
            "- 老天真不长眼 -> ông trời thật đúng là không có mắt / trời không có mắt\n"
            "- 跑路 -> chuồn / bỏ trốn / tháo chạy\n"
            "- 摆烂 / 装咸鱼 -> lười biếng / an phận thủ thường / làm cá ươn\n"
            "- 臣妾还以为 -> Thần thiếp cứ ngỡ / Thần thiếp cứ tưởng\n"
            "- 再也见不到您了 -> không bao giờ được gặp lại người nữa\n\n"
            "【绝对铁律（违者废弃）】：\n"
            "1. 输入格式为：ID|台词。输出格式必须严格为：ID|越南语译文。\n"
            "2. 每一行输入对应恰好一行输出！绝对不合并行、不漏行、不跳行、不换行！\n"
            "   遇到断句（例如第9行'臣妾还以为'、第10行'再也见不到您了'），必须分别输出第9行和第10行，严禁合并成一行！\n"
            "3. 输出译文必须100%全部为越南语，严禁在译文中保留哪怕一个汉字！\n"
            "4. 严禁输出任何问候、总结或额外说明。"
        )
        local_style_directives = {
            'cinema': "\n\n【翻译风格要求】：电影院线标准字幕风格，自然流畅、生动细腻、脱俗传神。",
            'street_raw': (
                "\n\n【翻译风格强制要求（市井江湖 / 街头百姓 / 粗鲁通俗 / 强烈情绪）】：\n"
                "- 风格极其接地气、民间、街头江湖与市井生活化（dân dã, bụi bặm, giang hồ, đường phố）。\n"
                "- 人称代词：角色争吵、对立、打斗或熟人调侃时，直接采用 mày - tao, bố mày, ông đây, bà đây, thằng ranh, con ranh, lão già... 等口语称呼。\n"
                "- 粗口与感叹词许可：允许并鼓励在愤怒/骂人/冲突场景中使用地道越南语感叹词、俚语及轻度粗口（如：mẹ kiếp, vãi, mé, chết tiệt, cút mẹ mày đi, khốn nạn, chó chết, cay vãi, ăn cám...），台词务必生动逼真、极富冲击力，严禁书面死板。"
            ),
            'historical': (
                "\n\n【翻译风格强制要求（古装 / 仙侠 / 武侠）】：\n"
                "- 翻译古色古香、气势恢宏。严格遵循经典武侠人称称谓（ta - ngươi, tại hạ, các hạ, huynh - đệ, bệ hạ - thần thiếp, trẫm, bản tọa, bản tôn...），优先使用标准汉越词。"
            ),
            'humorous_bua': (
                "\n\n【翻译风格强制要求（幽默 / 无厘头 / 爆笑）】：\n"
                "- 翻译幽默风趣、无厘头、搞笑自嘲，巧妙融入网络流行语与年轻人口语俚语（hài hước, bựa, lầy lội），极具娱乐喜剧效果。"
            ),
            'romance': (
                "\n\n【翻译风格强制要求（唯美言情 / 浪漫深情）】：\n"
                "- 翻译深情委婉、温柔浪漫、如诗如画。人称亲昵深情（anh - em, chàng - thiếp...），细腻刻画恋爱心境与情感纠葛。"
            ),
            'formal': (
                "\n\n【翻译风格强制要求（严肃正剧 / 纪录片）】：\n"
                "- 翻译严肃客观、忠实原意、文明规范，人称礼貌得体，不使用任何俚语或粗俗词。"
            )
        }
        system_prompt += local_style_directives.get(translation_style, local_style_directives['cinema'])
        user_prefix = "请严格按 ID|越南语译文 逐行翻译以下字幕（严禁漏行、严禁合并）："
        rescue_prefix = "以下断句或行被遗漏，请逐行补译，格式严格为 ID|越南语译文（100%越南语，绝不漏行）："
    else:
        system_prompt = (
            f"You are a professional film subtitle translator.\n"
            f"Your ONLY task is to translate movie subtitles from {src_name} into {tgt_name}.\n"
            f"CRITICAL RULES:\n"
            f"1. Output MUST be 100% in {tgt_name}. Do NOT retain untranslated source characters.\n"
            f"2. Keep the dialogue natural, emotional, and suitable for film/cinema.\n"
            f"3. Strictly maintain the format: ID|<translation>. Do not add any greeting or explanation.\n"
            f"4. Exactly one output line per one input line. Never merge lines."
        )
        local_style_directives_en = {
            'cinema': "\n\n[STYLE]: Cinematic, natural, and emotionally expressive movie dialogue.",
            'street_raw': "\n\n[STYLE]: Gritty, colloquial street style. Authentic street slang, informal pronouns, and mild profanities are permitted during angry/conflict dialogue for realism.",
            'historical': "\n\n[STYLE]: Archaic, noble period piece / martial arts tone.",
            'humorous_bua': "\n\n[STYLE]: Humorous, sarcastic, witty, Gen-Z slang / banter.",
            'romance': "\n\n[STYLE]: Romantic, poetic, tender love dialogue.",
            'formal': "\n\n[STYLE]: Formal, neutral, polite, and literal translation."
        }
        system_prompt += local_style_directives_en.get(translation_style, local_style_directives_en['cinema'])
        user_prefix = f"Translate these subtitles into {tgt_name} (Strict format ID|<translation>):"
        rescue_prefix = f"Translate the following missing lines into {tgt_name}:"

    # Phân chia thành các chunks 35 dòng (KHÔNG gộp OCR, bảo toàn 100% từng dòng để không lệch thoại)
    chunks = [subtitles[i:i + LOCAL_CHUNK_SIZE] for i in range(0, len(subtitles), LOCAL_CHUNK_SIZE)]
    translated_map = {}
    total_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    if len(chunks) <= 1:
        # Nếu chỉ có 1 chunk thì chạy trực tiếp
        chunk_res, c_usage = _translate_single_chunk(chunks[0], model, system_prompt, user_prefix, rescue_prefix, target_lang, client)
        translated_map.update(chunk_res)
        if c_usage:
            for k in total_usage:
                total_usage[k] += c_usage.get(k, 0)
    else:
        # Nhiều chunks: Xử lý song song với ThreadPoolExecutor (max_workers=LOCAL_CONCURRENCY=4)
        from concurrent.futures import ThreadPoolExecutor
        workers = min(LOCAL_CONCURRENCY, len(chunks))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_translate_single_chunk, ch, model, system_prompt, user_prefix, rescue_prefix, target_lang, client)
                for ch in chunks
            ]
            for fut in futures:
                try:
                    c_res, c_usage = fut.result()
                    if c_res:
                        translated_map.update(c_res)
                    if c_usage:
                        for k in total_usage:
                            total_usage[k] += c_usage.get(k, 0)
                except Exception:
                    pass

    # Ánh xạ kết quả chuẩn xác theo đúng ID từng dòng phụ đề gốc
    result_subs = []
    for s in subtitles:
        sid_str = str(s.get("id", "")).strip()
        trans = translated_map.get(sid_str, "")
        
        # Tuyệt đối không để chuỗi lỗi mạng hoặc 500 lọt vào phụ đề
        if "Error 500" in trans or "That's an error" in trans:
            trans = ""

        if trans and target_lang == 'vi':
            trans = re.sub(r'[\u4e00-\u9fff]+\s*[\(\（]([^\)\）]+)[\)\）]', r' \1 ', trans)
            trans = re.sub(r'[\(\（]([^\)\）]+)[\)\）]\s*[\u4e00-\u9fff]+', r' \1 ', trans)
            trans = re.sub(r'[\(\（]\s*[\u4e00-\u9fff]+\s*[\)\）]', '', trans)
            if re.search(r'[\u4e00-\u9fff]', trans):
                trans = re.sub(r'[\u4e00-\u9fff]+', '', trans)
            trans = re.sub(r'\s+', ' ', trans).strip()
            trans = re.sub(r'\s+([,.:;?!])', r'\1', trans)
            if trans and trans[0].islower():
                trans = trans[0].upper() + trans[1:]

        s_copy = dict(s)
        s_copy["translation"] = trans
        result_subs.append(s_copy)

    if return_usage:
        return result_subs, total_usage
    return result_subs

def condense_subtitles_local(subtitles, model=None, target_lang="vi"):
    """
    Rút gọn và chắt lọc nội dung phụ đề (loại bỏ câu đệm, tóm tắt thoại giữ mạch phim) bằng Qwen 2.5
    """
    if not model:
        status = get_local_ai_status()
        model = status.get("recommended_model") or DEFAULT_TRANSLATE_MODEL

    import openai
    client = openai.OpenAI(
        api_key="ollama",
        base_url=f"{OLLAMA_BASE_URL}/v1",
        timeout=360.0
    )

    system_prompt = (
        "Bạn là đạo diễn biên kịch và biên tập video kỳ cựu.\n"
        "Nhiệm vụ của bạn là chắt lọc và rút gọn phụ đề thoại:\n"
        "1. Loại bỏ các câu cảm thán, câu đệm vô nghĩa, lặp từ, hoặc câu thoại rời rạc không mang giá trị cốt truyện.\n"
        "2. Ghép và cô đọng các câu thoại ngắt quãng thành những câu ngắn gọn, súc tích (5-8 giây) để phục vụ làm kịch bản tóm tắt/review phim.\n"
        "3. Trả về đúng định dạng SRT chuẩn (hoặc danh sách [ID] Text rút gọn) không kèm lời chào hỏi hay giải thích."
    )

    lines = []
    for s in subtitles:
        sid = s.get("id", "")
        time_val = s.get("time", "")
        txt = (s.get("translation") or s.get("text") or "").replace("\r", "").replace("\n", " ").strip()
        lines.append(f"[{sid}] ({time_val}) {txt}")

    user_content = "Hãy rút gọn và làm sạch danh sách phụ đề sau:\n\n" + "\n".join(lines)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content or ""
