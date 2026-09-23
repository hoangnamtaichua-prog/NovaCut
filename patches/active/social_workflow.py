# -*- coding: utf-8 -*-
"""Persistent social publishing workflow primitives.

This module deliberately stops at a reviewable publish plan. Platform adapters
must update the job to PUBLISHED only after the platform confirms the post.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timezone

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_FILE = os.path.join(ROOT_DIR, "user_data", "social_publish_jobs.json")
CONNECTIONS_FILE = os.path.join(ROOT_DIR, "user_data", "social_connections.json")
_LOCK = threading.RLock()

PLATFORM_LIMITS = {
    "youtube": {"title": 100, "caption": 5000},
    "facebook": {"title": 255, "caption": 2000},
    "instagram": {"title": 0, "caption": 2200},
    "tiktok": {"title": 0, "caption": 2200},
    "x_twitter": {"title": 0, "caption": 280},
    "linkedin": {"title": 0, "caption": 3000},
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _read_jobs():
    try:
        with open(JOBS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def _write_jobs(jobs):
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    tmp = JOBS_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(jobs, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, JOBS_FILE)


def list_connections():
    try:
        with open(CONNECTIONS_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save_connection(
    platform_id,
    account_label,
    profile_id="Default",
    capabilities=None,
    account_type="chrome_profile",
    remote_account_id=None,
    avatar_url=None,
    connection_id=None,
):
    if platform_id not in PLATFORM_LIMITS:
        raise ValueError("Nền tảng không hợp lệ")
    label = str(account_label or "").strip()
    if not label:
        raise ValueError("Tên tài khoản không được để trống")

    with _LOCK:
        items = list_connections()
        existing = next((c for c in items if c.get("connection_id") == connection_id), None) if connection_id else None
        if existing:
            existing["account_label"] = label
            existing["profile_id"] = str(profile_id or "Default")
            if capabilities is not None:
                existing["capabilities"] = capabilities
            if account_type:
                existing["account_type"] = account_type
            if remote_account_id:
                existing["remote_account_id"] = str(remote_account_id)
            if avatar_url:
                existing["avatar_url"] = str(avatar_url)
            existing["updated_at"] = _now()
            record = existing
        else:
            record = {
                "connection_id": connection_id or uuid.uuid4().hex,
                "platform_id": platform_id,
                "account_label": label,
                "profile_id": str(profile_id or "Default"),
                "account_type": account_type or "chrome_profile",
                "capabilities": capabilities or ["manual_browser"],
                "remote_account_id": str(remote_account_id) if remote_account_id else None,
                "avatar_url": str(avatar_url) if avatar_url else None,
                "created_at": _now(),
            }
            items.append(record)

        os.makedirs(os.path.dirname(CONNECTIONS_FILE), exist_ok=True)
        tmp = CONNECTIONS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(items, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, CONNECTIONS_FILE)
    return record


def delete_connection(connection_id):
    """Delete a connection record and clean up associated encrypted tokens."""
    if not connection_id:
        return False
    import social_tokens
    with _LOCK:
        items = list_connections()
        filtered = [c for c in items if c.get("connection_id") != connection_id]
        if len(filtered) == len(items):
            return False
        os.makedirs(os.path.dirname(CONNECTIONS_FILE), exist_ok=True)
        tmp = CONNECTIONS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(filtered, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, CONNECTIONS_FILE)
    social_tokens.delete_token(connection_id)
    return True


def _hashtags(seed):
    words = [w.strip(".,!?;:#") for w in seed.split()]
    tags = ["#reviewphim", "#phimhay", "#shorts"]
    for word in words:
        if len(word) >= 4 and word.isalnum():
            tag = "#" + word.lower()
            if tag not in tags:
                tags.append(tag)
        if len(tags) >= 6:
            break
    return " ".join(tags)


def build_platform_copy(title_template, platform_id):
    """Create deterministic, editable copy when an AI provider is unavailable."""
    title = " ".join(str(title_template or "Video mới").split())
    tags = _hashtags(title)
    if platform_id == "youtube":
        caption = f"{title}\n\nXem đến cuối để biết diễn biến tiếp theo.\n\n{tags}"
    elif platform_id == "facebook":
        caption = f"{title}\n\nBạn đoán kết thúc sẽ như thế nào? {tags}"
    elif platform_id == "instagram":
        caption = f"{title}\n\nMột phân cảnh không thể bỏ qua. {tags}"
    elif platform_id == "tiktok":
        caption = f"{title} 👀\n\n{tags}"
    else:
        caption = f"{title} {tags}"
    limit = PLATFORM_LIMITS.get(platform_id, {}).get("caption", 2200)
    return {
        "title": title[: PLATFORM_LIMITS.get(platform_id, {}).get("title", 0)] if PLATFORM_LIMITS.get(platform_id, {}).get("title", 0) else "",
        "caption": caption[:limit],
        "hashtags": tags,
    }


def _ai_platform_copy(title_template, platform_id):
    """Ask the local Ollama service for copy; return None when unavailable."""
    try:
        import local_ai_manager
        if not local_ai_manager.is_ollama_service_running(timeout=0.8)[0]:
            return None
        import openai
        model = local_ai_manager.get_local_ai_status().get("recommended_model")
        if not model:
            return None
        client = openai.OpenAI(api_key="ollama", base_url=f"{local_ai_manager.OLLAMA_BASE_URL}/v1", timeout=20.0)
        response = client.chat.completions.create(
            model=model,
            temperature=0.7,
            messages=[
                {"role": "system", "content": "Bạn là biên tập viên mạng xã hội Việt Nam. Chỉ trả JSON hợp lệ với các khóa title, caption, hashtags. Không bịa chi tiết video."},
                {"role": "user", "content": f"Viết nội dung cho nền tảng {platform_id}. Tiêu đề mẫu: {title_template}. Caption phải ngắn, tự nhiên, có lời kêu gọi xem đến cuối."},
            ],
        )
        raw = (response.choices[0].message.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").replace("json", "", 1).strip()
        result = json.loads(raw)
        if not isinstance(result, dict):
            return None
        fallback = build_platform_copy(title_template, platform_id)
        result.setdefault("title", fallback["title"])
        result.setdefault("caption", fallback["caption"])
        result.setdefault("hashtags", fallback["hashtags"])
        limit = PLATFORM_LIMITS[platform_id]["caption"]
        result["caption"] = str(result["caption"])[:limit]
        return result
    except Exception:
        return None


def create_publish_plan(video_path, title_template, platform_ids, use_ai=True, connection_ids=None):
    if not os.path.isfile(video_path):
        raise FileNotFoundError("Tệp video không tồn tại")
    if not str(title_template or "").strip():
        raise ValueError("Tiêu đề mẫu không được để trống")
    platforms = [p for p in platform_ids if p in PLATFORM_LIMITS]
    if not platforms:
        raise ValueError("Cần chọn ít nhất một nền tảng hợp lệ")
    connections = {c["connection_id"]: c for c in list_connections()}
    selected_connections = connection_ids or []
    if selected_connections and any(cid not in connections for cid in selected_connections):
        raise ValueError("Tài khoản đích không tồn tại")
    copies = []
    for platform_id in platforms:
        copy = _ai_platform_copy(title_template, platform_id) if use_ai else None
        target = next((c for c in connections.values() if c["platform_id"] == platform_id and (not selected_connections or c["connection_id"] in selected_connections)), None)
        copies.append({
            "platform_id": platform_id,
            "connection_id": target["connection_id"] if target else None,
            "account_label": target["account_label"] if target else None,
            "account_type": target.get("account_type", "chrome_profile") if target else None,
            "capabilities": target.get("capabilities", []) if target else [],
            "status": "READY",
            "copy": copy or build_platform_copy(title_template, platform_id),
            "copy_source": "ollama" if copy else "fallback",
        })
    job = {
        "job_id": uuid.uuid4().hex,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "READY_FOR_PUBLISH",
        "video_path": os.path.abspath(video_path),
        "title_template": str(title_template).strip(),
        "platforms": copies,
    }
    with _LOCK:
        jobs = _read_jobs()
        jobs.append(job)
        _write_jobs(jobs)
    return job


def update_platform_copy(job_id, platform_id, title=None, caption=None, hashtags=None, connection_id=None):
    """Allows user to customize copy and target account for a platform before publishing."""
    with _LOCK:
        jobs = _read_jobs()
        job = next((j for j in jobs if j.get("job_id") == job_id), None)
        if not job:
            return None
        item = next((p for p in job.get("platforms", []) if p.get("platform_id") == platform_id), None)
        if not item:
            raise ValueError("Nền tảng không nằm trong job")
        if item.get("status") == "PUBLISHED":
            raise ValueError("Không thể sửa bài đã xuất bản thành công")

        copy = item.setdefault("copy", {})
        if title is not None:
            copy["title"] = str(title).strip()
        if caption is not None:
            copy["caption"] = str(caption).strip()
        if hashtags is not None:
            copy["hashtags"] = str(hashtags).strip()

        if connection_id is not None:
            connections = {c["connection_id"]: c for c in list_connections()}
            if connection_id:
                if connection_id not in connections:
                    raise ValueError("Tài khoản đích không tồn tại")
                target = connections[connection_id]
                item["connection_id"] = target["connection_id"]
                item["account_label"] = target["account_label"]
                item["account_type"] = target.get("account_type", "chrome_profile")
                item["capabilities"] = target.get("capabilities", [])
            else:
                item["connection_id"] = None
                item["account_label"] = None
                item["account_type"] = None
                item["capabilities"] = []

        item["copy_source"] = "user_edited"
        job["updated_at"] = _now()
        _write_jobs(jobs)
        return job


def get_publish_job(job_id):
    with _LOCK:
        return next((j for j in _read_jobs() if j.get("job_id") == job_id), None)


ALLOWED_STATUSES = {"READY", "UPLOADING", "PROCESSING", "PUBLISHED", "FAILED", "NEEDS_ACTION"}


def update_platform_status(job_id, platform_id, status, remote_id=None, url=None, message=None):
    if status not in ALLOWED_STATUSES:
        raise ValueError("Trạng thái không hợp lệ")
    if status == "PUBLISHED" and (not remote_id or not url):
        raise ValueError("Thiếu mã bài đăng và liên kết xác nhận từ nền tảng")
    with _LOCK:
        jobs = _read_jobs()
        job = next((j for j in jobs if j.get("job_id") == job_id), None)
        if not job:
            return None
        item = next((p for p in job.get("platforms", []) if p.get("platform_id") == platform_id), None)
        if not item:
            raise ValueError("Nền tảng không nằm trong job")
        item["status"] = status
        if remote_id is not None:
            item["remote_id"] = str(remote_id)
        if url is not None:
            item["url"] = str(url)
        if message is not None:
            item["message"] = str(message)
        statuses = [p.get("status") for p in job.get("platforms", [])]
        if all(s == "PUBLISHED" for s in statuses):
            job["status"] = "PUBLISHED"
        elif any(s in {"UPLOADING", "PROCESSING"} for s in statuses):
            job["status"] = "IN_PROGRESS"
        elif "NEEDS_ACTION" in statuses:
            job["status"] = "NEEDS_ACTION"
        elif all(s in {"FAILED", "PUBLISHED"} for s in statuses):
            job["status"] = "PARTIAL" if "PUBLISHED" in statuses else "FAILED"
        else:
            job["status"] = "IN_PROGRESS"
        job["updated_at"] = _now()
        _write_jobs(jobs)
        return job


def _worker_publish(job_id, target_platforms):
    import social_adapters
    job = get_publish_job(job_id)
    if not job:
        return
    for item in job.get("platforms", []):
        p_id = item.get("platform_id")
        if target_platforms and p_id not in target_platforms:
            continue
        if item.get("status") in {"PUBLISHED"}:
            continue
        update_platform_status(job_id, p_id, "UPLOADING", message="Đang kết nối và truyền dữ liệu video...")
        try:
            fresh_job = get_publish_job(job_id)
            fresh_item = next((p for p in fresh_job.get("platforms", []) if p.get("platform_id") == p_id), item)
            result = social_adapters.publish(fresh_job, fresh_item)
            update_platform_status(job_id, p_id, result.status, result.remote_id, result.url, result.message)
        except Exception as exc:
            update_platform_status(job_id, p_id, "FAILED", message=f"Lỗi ngoại lệ: {exc}")


def start_background_publish(job_id, platform_ids=None):
    job = get_publish_job(job_id)
    if not job:
        raise ValueError("Không tìm thấy job")
    targets = set(platform_ids) if platform_ids else None
    t = threading.Thread(target=_worker_publish, args=(job_id, targets), daemon=True)
    t.start()
    return True
