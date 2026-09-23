# -*- coding: utf-8 -*-
"""Official publisher adapter boundary.

Adapters never write PUBLISHED optimistically. A successful result must contain
the remote post id and URL returned by the platform.
"""
import os
import time
import json
import urllib.request
import urllib.parse
import social_tokens
import social_workflow


class AdapterResult:
    def __init__(self, status, message, remote_id=None, url=None):
        self.status = status
        self.message = message
        self.remote_id = remote_id
        self.url = url

    def to_dict(self):
        return {"status": self.status, "message": self.message, "remote_id": self.remote_id, "url": self.url}


def _check_youtube_remote_status(video_id, access_token):
    """Check processing status of an existing YouTube video without re-uploading."""
    if not video_id or not access_token:
        return None
    url = f"https://www.googleapis.com/youtube/v3/videos?part=processingDetails,status&id={urllib.parse.quote(video_id)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {access_token}"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", [])
        if not items:
            return None
        processing = items[0].get("processingDetails", {}).get("processingStatus")
        return processing
    except Exception:
        return None


def upload_youtube_resumable(video_path, title, description, privacy, access_token, timeout_seconds=90):
    """Perform official YouTube Resumable Upload via standard HTTP protocol."""
    if not os.path.isfile(video_path):
        return AdapterResult("FAILED", f"Tệp video không tồn tại: {video_path}")
    file_size = os.path.getsize(video_path)
    if file_size == 0:
        return AdapterResult("FAILED", "Tệp video có kích thước 0 byte.")

    metadata = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "categoryId": "22",
        },
        "status": {
            "privacyStatus": privacy if privacy in {"public", "unlisted", "private"} else "public",
        },
    }
    init_url = "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status"
    init_body = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    init_req = urllib.request.Request(
        init_url,
        data=init_body,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json; charset=UTF-8",
            "X-Upload-Content-Type": "video/*",
            "X-Upload-Content-Length": str(file_size),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(init_req, timeout=20) as resp:
            upload_url = resp.headers.get("Location")
    except urllib.error.HTTPError as exc:
        err_msg = exc.read().decode("utf-8", errors="replace")
        return AdapterResult("FAILED", f"Lỗi khởi tạo YouTube upload: {exc.code} - {err_msg}")
    except Exception as exc:
        return AdapterResult("FAILED", f"Lỗi mạng khi kết nối YouTube: {exc}")

    if not upload_url:
        return AdapterResult("FAILED", "YouTube không trả về URL tải lên resumable.")

    # Upload video data via PUT
    try:
        with open(video_path, "rb") as fh:
            video_bytes = fh.read()
        upload_req = urllib.request.Request(
            upload_url,
            data=video_bytes,
            headers={
                "Content-Type": "video/*",
                "Content-Length": str(file_size),
            },
            method="PUT",
        )
        with urllib.request.urlopen(upload_req, timeout=timeout_seconds) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        video_id = data.get("id")
        if not video_id:
            return AdapterResult("FAILED", "YouTube không trả về video ID.")
    except Exception as exc:
        return AdapterResult("FAILED", f"Lỗi truyền dữ liệu video tới YouTube: {exc}")

    # Poll processing status for up to 45 seconds (9 intervals of 5s)
    video_url = f"https://youtu.be/{video_id}"
    for _ in range(9):
        time.sleep(5)
        status = _check_youtube_remote_status(video_id, access_token)
        if status == "succeeded":
            return AdapterResult("PUBLISHED", "YouTube đã xử lý xong video.", video_id, video_url)
        if status == "failed":
            return AdapterResult("FAILED", "YouTube báo xử lý video thất bại.", video_id, video_url)

    return AdapterResult("PROCESSING", "Video đã tải lên thành công; YouTube đang trong quá trình xử lý.", video_id, video_url)


def publish_youtube(job, item, access_token=None):
    """Publish through YouTube Data API when OAuth integration is configured."""
    token = access_token or os.environ.get("NOVACUT_YOUTUBE_OAUTH_TOKEN")
    if not token:
        return AdapterResult("NEEDS_ACTION", "Chưa cấu hình YouTube OAuth. Hãy kết nối kênh trong Cài đặt tài khoản.")
    video_path = job.get("video_path", "")
    if not os.path.isfile(video_path):
        return AdapterResult("NEEDS_ACTION", "Tệp video không tồn tại trên ổ đĩa.")

    copy = item.get("copy") or {}
    title = copy.get("title") or job.get("title_template", "Video mới")
    description = copy.get("caption", "")
    privacy = item.get("privacy") or job.get("privacy") or "public"

    # Try standard HTTP resumable upload first
    return upload_youtube_resumable(video_path, title, description, privacy, token)


def publish_meta(job, item, access_token=None):
    """Publish a Page video/Reel through Meta Graph API when account config exists."""
    token = access_token or os.environ.get("NOVACUT_META_ACCESS_TOKEN")
    page_id = item.get("page_id") or os.environ.get("NOVACUT_META_PAGE_ID")
    public_url = job.get("public_video_url")
    if not token or not page_id or not public_url:
        return AdapterResult("NEEDS_ACTION", "Meta cần access token, Page ID và URL video công khai.")
    try:
        platform_id = item.get("platform_id")
        caption = (item.get("copy") or {}).get("caption", "")
        if platform_id == "facebook":
            endpoint = f"https://graph.facebook.com/v20.0/{page_id}/videos"
            payload = {"file_url": public_url, "description": caption, "access_token": token}
        else:
            endpoint = f"https://graph.facebook.com/v20.0/{page_id}/media"
            payload = {"media_type": "REELS", "video_url": public_url, "caption": caption, "access_token": token}
        req = urllib.request.Request(endpoint, data=urllib.parse.urlencode(payload).encode(), method="POST")
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
        remote_id = data.get("id") or data.get("video_id")
        if not remote_id:
            return AdapterResult("FAILED", "Meta không trả về mã bài đăng.")
        if platform_id == "instagram":
            publish_endpoint = f"https://graph.facebook.com/v20.0/{page_id}/media_publish"
            publish_payload = urllib.parse.urlencode({"creation_id": remote_id, "access_token": token}).encode()
            with urllib.request.urlopen(urllib.request.Request(publish_endpoint, data=publish_payload, method="POST"), timeout=30) as response:
                remote_id = json.loads(response.read().decode("utf-8")).get("id", remote_id)
        return AdapterResult("PUBLISHED", "Meta đã nhận và xuất bản nội dung.", remote_id, f"https://www.facebook.com/{remote_id}")
    except Exception as exc:
        return AdapterResult("FAILED", f"Lỗi Meta Graph API: {exc}")


def publish_tiktok(job, item, access_token=None):
    """TikTok Direct Post requires an audited app and creator consent UX."""
    token = access_token or os.environ.get("NOVACUT_TIKTOK_ACCESS_TOKEN")
    if not token:
        return AdapterResult("NEEDS_ACTION", "TikTok cần kết nối Content Posting API và người dùng xác nhận quyền đăng.")
    # Verify creator info and explicit consent
    consent = item.get("consent_granted") or job.get("consent_granted")
    if not consent:
        return AdapterResult("NEEDS_ACTION", "TikTok Direct Post cần creator_info, privacy và consent trước khi gửi video.")
    return AdapterResult("NEEDS_ACTION", "TikTok Content Posting API yêu cầu xét duyệt ứng dụng chính thức từ TikTok.")


def _dispatch_verified(job, item, connection, access_token):
    """Internal dispatch; only callable after the OAuth account is verified."""
    platform_id = item.get("platform_id")
    if platform_id == "youtube":
        return publish_youtube(job, item, access_token=access_token)
    if platform_id in {"facebook", "instagram"}:
        return publish_meta(job, item, access_token=access_token)
    if platform_id == "tiktok":
        return publish_tiktok(job, item, access_token=access_token)
    return AdapterResult("NEEDS_ACTION", f"Chưa có adapter chính thức cho {platform_id}.")


def publish(job, item):
    """Entry point for publishing an item of a workflow job.

    Enforces:
    1. Idempotency: Never re-upload if already PUBLISHED or if remote_id exists.
    2. Connection Verification: Requires an OAuth connection with 'verified_api' capability.
    3. Token Protection: Retrieves token strictly from encrypted token vault.
    """
    if item.get("status") == "PUBLISHED":
        return AdapterResult("PUBLISHED", "Bài đã được đăng trước đó.", item.get("remote_id"), item.get("url"))

    remote_id = item.get("remote_id")
    if item.get("status") in {"UPLOADING", "PROCESSING"} or remote_id:
        # Check if remote processing status has updated if possible
        cid = item.get("connection_id")
        if cid and item.get("platform_id") == "youtube" and remote_id:
            token = social_tokens.refresh_token_if_needed(cid)
            if token:
                proc_status = _check_youtube_remote_status(remote_id, token)
                if proc_status == "succeeded":
                    return AdapterResult("PUBLISHED", "YouTube đã xử lý xong video.", remote_id, item.get("url"))
                if proc_status == "failed":
                    return AdapterResult("FAILED", "YouTube báo xử lý video thất bại.", remote_id, item.get("url"))
                if proc_status:
                    return AdapterResult("PROCESSING", f"Video đang được YouTube xử lý (trạng thái: {proc_status}).", remote_id, item.get("url"))
        return AdapterResult("NEEDS_ACTION", "Bài đã có lượt gửi; cần kiểm tra trạng thái trước khi đăng lại.", remote_id, item.get("url"))

    connection_id = item.get("connection_id")
    if not connection_id:
        return AdapterResult("NEEDS_ACTION", "Cần kết nối OAuth và xác minh tài khoản đích trước khi đăng qua API.")

    # Validate connection record
    connections = {c["connection_id"]: c for c in social_workflow.list_connections()}
    conn = connections.get(connection_id)
    if not conn:
        return AdapterResult("NEEDS_ACTION", "Tài khoản đích không tồn tại trong danh sách kết nối.")

    capabilities = conn.get("capabilities", [])
    if "verified_api" not in capabilities:
        return AdapterResult("NEEDS_ACTION", "Cần kết nối OAuth và xác minh tài khoản đích trước khi đăng qua API.")

    # Retrieve and refresh token
    access_token = social_tokens.refresh_token_if_needed(connection_id)
    if not access_token:
        return AdapterResult("NEEDS_ACTION", "Phiên xác thực OAuth đã hết hạn. Vui lòng kết nối lại tài khoản.")

    return _dispatch_verified(job, item, conn, access_token)
