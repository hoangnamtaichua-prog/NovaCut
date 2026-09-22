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


class AdapterResult:
    def __init__(self, status, message, remote_id=None, url=None):
        self.status = status
        self.message = message
        self.remote_id = remote_id
        self.url = url

    def to_dict(self):
        return {"status": self.status, "message": self.message, "remote_id": self.remote_id, "url": self.url}


def _youtube_configured():
    return bool(os.environ.get("NOVACUT_YOUTUBE_OAUTH_TOKEN")) or bool(os.environ.get("NOVACUT_YOUTUBE_CLIENT_SECRET"))


def publish_youtube(job, item):
    """Publish through YouTube Data API when OAuth integration is configured.

    The dependency and credentials are intentionally loaded lazily. This keeps
    the desktop app usable without Google libraries and prevents secrets from
    entering job JSON or logs.
    """
    if not _youtube_configured():
        return AdapterResult("NEEDS_ACTION", "Chưa cấu hình YouTube OAuth. Hãy kết nối kênh trong Cài đặt tài khoản.")
    try:
        from googleapiclient.discovery import build  # noqa: F401
        from googleapiclient.http import MediaFileUpload  # noqa: F401
        from google.oauth2.credentials import Credentials
    except ImportError:
        return AdapterResult("NEEDS_ACTION", "Thiếu google-api-python-client; chưa thể bật đăng YouTube chính thức.")
    try:
        token = os.environ.get("NOVACUT_YOUTUBE_OAUTH_TOKEN")
        if not token or not os.path.isfile(job.get("video_path", "")):
            return AdapterResult("NEEDS_ACTION", "Thiếu access token hoặc video không tồn tại.")
        credentials = Credentials(token=token, scopes=["https://www.googleapis.com/auth/youtube.upload"])
        youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        copy = item.get("copy") or {}
        body = {"snippet": {"title": copy.get("title") or job.get("title_template", "Video mới"), "description": copy.get("caption", ""), "categoryId": "22"}, "status": {"privacyStatus": "public"}}
        upload = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(job["video_path"], chunksize=8 * 1024 * 1024, resumable=True)).execute()
        video_id = upload.get("id")
        if not video_id:
            return AdapterResult("FAILED", "YouTube không trả về video ID.")
        for _ in range(12):
            info = youtube.videos().list(part="processingDetails,status", id=video_id).execute().get("items", [])
            if info:
                processing = info[0].get("processingDetails", {}).get("processingStatus")
                if processing == "succeeded":
                    return AdapterResult("PUBLISHED", "YouTube đã xử lý xong video.", video_id, f"https://youtu.be/{video_id}")
                if processing == "failed":
                    return AdapterResult("FAILED", "YouTube báo xử lý video thất bại.", video_id, f"https://youtu.be/{video_id}")
            time.sleep(5)
        return AdapterResult("PROCESSING", "Video đã tải lên; YouTube vẫn đang xử lý.", video_id, f"https://youtu.be/{video_id}")
    except Exception as exc:
        return AdapterResult("FAILED", f"Lỗi YouTube upload: {exc}")


def publish(job, item):
    if item.get("status") == "PUBLISHED":
        return AdapterResult("PUBLISHED", "Bài đã được đăng trước đó.", item.get("remote_id"), item.get("url"))
    if item.get("status") in {"UPLOADING", "PROCESSING"} or item.get("remote_id"):
        return AdapterResult("NEEDS_ACTION", "Bài đã có lượt gửi; cần kiểm tra trạng thái trước khi đăng lại.", item.get("remote_id"), item.get("url"))
    # A browser profile label is not an authenticated API account. Do not use
    # machine-wide credentials to silently publish to a different account.
    return AdapterResult("NEEDS_ACTION", "Cần kết nối OAuth và xác minh tài khoản đích trước khi đăng qua API.")


def _dispatch_verified(job, item):
    """Internal dispatch; only callable after the OAuth account is verified."""
    if item.get("platform_id") == "youtube":
        return publish_youtube(job, item)
    if item.get("platform_id") in {"facebook", "instagram"}:
        return publish_meta(job, item)
    if item.get("platform_id") == "tiktok":
        return publish_tiktok(job, item)
    return AdapterResult("NEEDS_ACTION", f"Chưa có adapter chính thức cho {item.get('platform_id')}.")


def publish_tiktok(job, item):
    """TikTok Direct Post requires an audited app and creator consent UX."""
    if not os.environ.get("NOVACUT_TIKTOK_ACCESS_TOKEN"):
        return AdapterResult("NEEDS_ACTION", "TikTok cần kết nối Content Posting API và người dùng xác nhận quyền đăng.")
    return AdapterResult("NEEDS_ACTION", "TikTok Direct Post cần creator_info, privacy và consent trước khi gửi video.")


def publish_meta(job, item):
    """Publish a Page video/Reel through Meta Graph API when account config exists."""
    token = os.environ.get("NOVACUT_META_ACCESS_TOKEN")
    page_id = os.environ.get("NOVACUT_META_PAGE_ID")
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
