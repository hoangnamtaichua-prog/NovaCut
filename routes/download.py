from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, ipaddress, socket
from routes.state import *
from routes.security import is_path_allowed, parse_bool
import asr_manager
from urllib.parse import urlparse

download_bp = Blueprint('download', __name__)
_download_lock = threading.RLock()
_download_active = False
_douyin_scan_active = False
_douyin_batch_active = False


def _require_editor():
    import license_manager
    allowed, message, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'success': False, 'error': message}), 403
    return None


def _is_public_https_url(value, allowed_domains=None):
    try:
        parsed = urlparse(str(value or '').strip())
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            return False
        host = parsed.hostname.lower().rstrip('.')
        if allowed_domains and not any(host == domain or host.endswith('.' + domain) for domain in allowed_domains):
            return False
        for item in socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM):
            ip = ipaddress.ip_address(item[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        return True
    except Exception:
        return False


def _validate_media_page_url(value):
    domains = {
        'youtube.com', 'youtu.be', 'tiktok.com', 'douyin.com', 'iesdouyin.com',
        'bilibili.com', 'facebook.com', 'instagram.com', 'twitter.com', 'x.com', 'vimeo.com'
    }
    domains.update(x.strip().lower() for x in os.environ.get('NOVACUT_ALLOWED_DOWNLOAD_HOSTS', '').split(',') if x.strip())
    return _is_public_https_url(value, domains)


def _normalize_output_dir(value):
    output_dir = str(value or os.path.join(USER_DATA_DIR, 'downloads')).strip()
    if not os.path.isabs(output_dir):
        output_dir = os.path.abspath(os.path.join(ROOT_DIR, output_dir))
    if not is_path_allowed(output_dir):
        raise ValueError('Thư mục tải xuống chưa được người dùng cho phép.')
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _valid_douyin_source(value):
    source = str(value or '').strip()
    if re.fullmatch(r'[a-zA-Z0-9_-]{6,160}', source):
        return True
    return _is_public_https_url(source, {'douyin.com', 'iesdouyin.com'})


def _sanitize_douyin_videos(items):
    if not isinstance(items, list) or not items or len(items) > 300:
        raise ValueError('Danh sách video phải có từ 1 đến 300 mục.')
    sanitized = []
    for raw in items:
        if not isinstance(raw, dict):
            raise ValueError('Một mục video không đúng định dạng.')
        page_url = str(raw.get('url') or '').strip()
        download_url = str(raw.get('download_url') or '').strip()
        image_urls = raw.get('image_urls') or []
        if page_url and not _valid_douyin_source(page_url):
            raise ValueError('URL trang Douyin không hợp lệ.')
        if download_url and not _is_public_https_url(download_url):
            raise ValueError('URL tải video không hợp lệ.')
        if not isinstance(image_urls, list) or len(image_urls) > 100 or any(not _is_public_https_url(url) for url in image_urls):
            raise ValueError('Danh sách URL ảnh không hợp lệ.')
        item = dict(raw)
        item['url'] = page_url
        item['download_url'] = download_url
        item['image_urls'] = [str(url) for url in image_urls]
        item['aweme_id'] = re.sub(r'[^a-zA-Z0-9_-]', '', str(raw.get('aweme_id') or ''))[:100]
        item['title'] = str(raw.get('title') or '')[:500]
        item['clean_title'] = str(raw.get('clean_title') or raw.get('title') or '')[:500]
        sanitized.append(item)
    return sanitized

@download_bp.route('/api/download/info', methods=['POST'])
def api_download_info():
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import downloader
        data = request.get_json(silent=True) or {}
        url = str(data.get('url', '')).strip()
        if not url:
            return jsonify({'error': 'Vui lòng nhập liên kết video'}), 400
        if not _validate_media_page_url(url):
            return jsonify({'error': 'URL không hợp lệ hoặc tên miền chưa được cho phép'}), 400
        
        result = downloader.extract_video_info(url)
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f"Lỗi phân tích: {str(e)}"}), 500

@download_bp.route('/api/download/start', methods=['POST'])
def api_download_start():
    global _download_active
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    import downloader, queue, threading, urllib.parse, json
    data = request.get_json(silent=True) or {}
    url = str(data.get('url', '')).strip()
    format_id = str(data.get('format_id', 'best'))[:100]
    try:
        is_audio = parse_bool(data.get('is_audio'), False)
        output_dir = _normalize_output_dir(data.get('output_dir'))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    
    if not url:
        return jsonify({'error': 'Vui lòng cung cấp URL video'}), 400
    if not _validate_media_page_url(url):
        return jsonify({'error': 'URL không hợp lệ hoặc tên miền chưa được cho phép'}), 400
    if not re.fullmatch(r'[a-zA-Z0-9_+.,:/-]{1,100}', format_id):
        return jsonify({'error': 'Format ID không hợp lệ'}), 400
    with _download_lock:
        if _download_active:
            return jsonify({'error': 'Một tác vụ tải video khác đang chạy'}), 409
        _download_active = True

    q = queue.Queue()

    def progress_callback(prog_data):
        q.put(prog_data)

    def worker():
        global _download_active
        try:
            final_path, info = downloader.download_media(
                url=url,
                format_id=format_id,
                is_audio=is_audio,
                output_dir=output_dir,
                progress_callback=progress_callback,
                info=None,
                video_urls=None
            )
            file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
            size_mb = f"{file_size / (1024*1024):.1f} MB"
            
            q.put({
                'status': 'completed',
                'file_path': final_path,
                'file_name': os.path.basename(final_path),
                'file_size': size_mb,
                'title': info.get('title', os.path.basename(final_path)),
                'thumbnail': info.get('thumbnail', ''),
                'duration': info.get('duration', 0),
                'audio_url': f"/api/file?path={urllib.parse.quote(final_path)}"
            })
        except Exception as e:
            q.put({
                'status': 'error',
                'error': str(e)
            })
        finally:
            with _download_lock:
                _download_active = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = q.get(timeout=60)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get('status') in ['completed', 'error']:
                    break
            except queue.Empty:
                yield "data: {\"status\": \"heartbeat\"}\n\n"

    return Response(generate(), mimetype='text/event-stream')

@download_bp.route('/api/download/open_folder', methods=['POST'])
def api_download_open_folder():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    folder_path = data.get('folder_path', '').strip()
    file_path = data.get('file_path', '').strip()
    
    target_path = folder_path or file_path
    if target_path and is_path_allowed(target_path, must_exist=True):
        if os.path.isdir(target_path):
            args = ['explorer', os.path.normpath(target_path)] if os.name == 'nt' else ['xdg-open', os.path.normpath(target_path)]
        else:
            args = ['explorer', f'/select,{os.path.normpath(target_path)}'] if os.name == 'nt' else ['xdg-open', os.path.dirname(os.path.normpath(target_path))]
        subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'success': True})
    if target_path:
        return jsonify({'success': False, 'error': 'Đường dẫn không hợp lệ hoặc chưa được cho phép'}), 403
    
    default_folder = os.path.join(USER_DATA_DIR, 'downloads')
    os.makedirs(default_folder, exist_ok=True)
    args = ['explorer', os.path.normpath(default_folder)] if os.name == 'nt' else ['xdg-open', os.path.normpath(default_folder)]
    subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify({'success': True})


@download_bp.route('/api/download/douyin/scan_channel_stream', methods=['POST'])
def api_download_douyin_scan_channel_stream():
    global _douyin_scan_active
    """
    API quét kênh Douyin thời gian thực qua Server-Sent Events (SSE Stream).
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader, queue, threading, json
    data = request.get_json(silent=True) or {}
    channel_url = str(data.get('channel_url', '')).strip()
    limit = data.get('limit', 30)

    if not channel_url or not _valid_douyin_source(channel_url):
        return jsonify({'error': 'Vui lòng nhập đường dẫn kênh hoặc mã sec_uid của Douyin'}), 400

    try:
        limit = int(limit) if limit and str(limit).isdigit() else 30
        if limit <= 0 or limit > 300:
            limit = 30
    except Exception:
        limit = 30

    with _download_lock:
        if _douyin_scan_active:
            return jsonify({'error': 'Một tác vụ quét kênh Douyin khác đang chạy'}), 409
        _douyin_scan_active = True

    q = queue.Queue()

    def progress_callback(pct, msg):
        q.put({
            'status': 'progress',
            'pct': pct,
            'msg': msg
        })

    def worker():
        global _douyin_scan_active
        try:
            crawler = douyin_browser_downloader.DouyinBrowserDownloader()
            result = crawler.scan_channel_videos(channel_url, limit=limit, progress_cb=progress_callback)
            q.put({
                'status': 'completed',
                'pct': 100,
                'result': result
            })
        except Exception as e:
            import traceback
            logging.error(f"[Douyin Channel Scan Error] {traceback.format_exc()}")
            q.put({
                'status': 'error',
                'error': str(e)
            })
        finally:
            with _download_lock:
                _douyin_scan_active = False

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = q.get(timeout=60)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get('status') in ['completed', 'error']:
                    break
            except queue.Empty:
                yield "data: {\"status\": \"heartbeat\"}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@download_bp.route('/api/download/douyin/scan_channel', methods=['POST'])
def api_download_douyin_scan_channel():
    global _douyin_scan_active
    """
    API quét toàn bộ hoặc N video mới nhất từ một kênh Douyin (Fallback Synchronous).
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader
    data = request.get_json(silent=True) or {}
    channel_url = str(data.get('channel_url', '')).strip()
    limit = data.get('limit', 30)

    if not channel_url or not _valid_douyin_source(channel_url):
        return jsonify({'error': 'Vui lòng nhập đường dẫn kênh hoặc mã sec_uid của Douyin'}), 400

    try:
        limit = int(limit) if limit and str(limit).isdigit() else 30
        if limit <= 0 or limit > 300:
            limit = 30
    except Exception:
        limit = 30

    with _download_lock:
        if _douyin_scan_active:
            return jsonify({'error': 'Một tác vụ quét kênh Douyin khác đang chạy'}), 409
        _douyin_scan_active = True
    try:
        crawler = douyin_browser_downloader.DouyinBrowserDownloader()
        result = crawler.scan_channel_videos(channel_url, limit=limit)
        return jsonify(result)
    except Exception as e:
        import traceback
        logging.error(f"[Douyin Channel Scan Error] {traceback.format_exc()}")
        return jsonify({'error': f"Lỗi quét kênh Douyin: {str(e)}"}), 500
    finally:
        with _download_lock:
            _douyin_scan_active = False


@download_bp.route('/api/download/douyin/batch_download', methods=['POST'])
def api_download_douyin_batch_download():
    """
    API tải hàng loạt danh sách video Douyin qua SSE Stream tiến trình.
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader, queue, threading, json
    data = request.json or {}
    videos = data.get('videos', [])
    output_dir = data.get('output_dir', '').strip()
    channel_name = data.get('channel_name', '').strip()

    if not videos or not isinstance(videos, list):
        return jsonify({'error': 'Danh sách video tải xuống rỗng'}), 400

    if not output_dir:
        output_dir = os.path.join(ROOT_DIR, 'downloads')
    os.makedirs(output_dir, exist_ok=True)

    q = queue.Queue()

    def progress_callback(completed, total, video_info, file_path, status_tag):
        q.put({
            'status': 'progress',
            'completed': completed,
            'total': total,
            'pct': int(completed / total * 100) if total > 0 else 0,
            'current_title': video_info.get('title', '') if video_info else '',
            'file_path': file_path or '',
            'tag': status_tag
        })

    def worker():
        try:
            downloaded_files = douyin_browser_downloader.download_channel_batch(
                video_list=videos,
                output_dir=output_dir,
                channel_name=channel_name,
                max_workers=3,
                progress_cb=progress_callback
            )
            q.put({
                'status': 'completed',
                'downloaded_count': len(downloaded_files),
                'total_requested': len(videos),
                'output_dir': output_dir,
                'files': downloaded_files
            })
        except Exception as e:
            q.put({
                'status': 'error',
                'error': str(e)
            })

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = q.get(timeout=60)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get('status') in ['completed', 'error']:
                    break
            except queue.Empty:
                yield "data: {\"status\": \"heartbeat\"}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@download_bp.route('/api/download/douyin/cancel_batch', methods=['POST'])
def api_download_douyin_cancel_batch():
    """
    API dừng/hủy tác vụ tải hàng loạt video Douyin ngay lập tức.
    """
    import douyin_browser_downloader
    try:
        douyin_browser_downloader.cancel_active_batch_download()
        return jsonify({'success': True, 'message': 'Đã gửi tín hiệu dừng tiến trình tải.'})
    except Exception as e:
        return jsonify({'error': f"Lỗi dừng tải: {str(e)}"}), 500


@download_bp.route('/api/download/douyin/open_login', methods=['POST'])
def api_download_douyin_open_login():
    """
    API mở trình duyệt để người dùng đăng nhập Douyin 1 lần duy nhất (vượt giới hạn 18 video của khách).
    """
    import douyin_browser_downloader, threading
    try:
        crawler = douyin_browser_downloader.DouyinBrowserDownloader(headless=False)
        t = threading.Thread(target=crawler.open_login_window, daemon=True)
        t.start()
        return jsonify({'success': True, 'message': 'Đang mở cửa sổ trình duyệt để đăng nhập...'})
    except Exception as e:
        return jsonify({'error': f"Lỗi mở trình duyệt đăng nhập: {str(e)}"}), 500




