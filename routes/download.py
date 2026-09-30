from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading, ipaddress, socket
from routes.state import *
from routes.security import is_path_allowed, parse_bool
import asr_manager
from urllib.parse import urlparse

download_bp = Blueprint('download', __name__)
_download_lock = threading.RLock()
_active_downloads = {}  # task_id -> {'cancel_event': threading.Event(), 'url': str, 'start_time': float}
MAX_CONCURRENT_DOWNLOADS = 5
_download_active = False  # Legacy compatibility flag
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
    import downloader, queue, threading, urllib.parse, json, uuid
    data = request.get_json(silent=True) or {}
    url = str(data.get('url', '')).strip()
    raw_task_id = str(data.get('task_id', '')).strip()
    task_id = raw_task_id if raw_task_id and re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', raw_task_id) else str(uuid.uuid4())
    format_id = str(data.get('format_id', 'best'))[:100]
    info_payload = data.get('info')
    video_urls_payload = data.get('video_urls')

    # Nếu payload info có chứa URL cụ thể của tập đang chọn (vd ?p=3), ưu tiên sử dụng
    if isinstance(info_payload, dict):
        info_url = str(info_payload.get('url') or '').strip()
        if info_url and _validate_media_page_url(info_url):
            url = info_url

    if not isinstance(video_urls_payload, list):
        video_urls_payload = None

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

    cancel_event = threading.Event()
    dl_start_time = time.time()
    with _download_lock:
        if len(_active_downloads) >= MAX_CONCURRENT_DOWNLOADS:
            return jsonify({'error': f'Đã đạt giới hạn tối đa số tác vụ tải đồng thời ({MAX_CONCURRENT_DOWNLOADS}). Vui lòng chờ các tác vụ trước hoàn tất.'}), 429
        _active_downloads[task_id] = {
            'cancel_event': cancel_event,
            'url': url,
            'start_time': dl_start_time
        }
        _download_active = True

    q = queue.Queue()

    def progress_callback(prog_data):
        if cancel_event.is_set():
            raise Exception('Tác vụ tải đã bị hủy bởi người dùng.')
        prog_with_id = dict(prog_data) if isinstance(prog_data, dict) else {'message': str(prog_data)}
        prog_with_id['task_id'] = task_id
        q.put(prog_with_id)

    def worker():
        global _download_active
        try:
            if cancel_event.is_set():
                raise Exception('Tác vụ tải đã bị hủy bởi người dùng.')

            final_path, info = downloader.download_media(
                url=url,
                format_id=format_id,
                is_audio=is_audio,
                output_dir=output_dir,
                progress_callback=progress_callback,
                info=info_payload if isinstance(info_payload, dict) else None,
                video_urls=video_urls_payload
            )

            if cancel_event.is_set():
                raise Exception('Tác vụ tải đã bị hủy bởi người dùng.')

            file_size = os.path.getsize(final_path) if os.path.exists(final_path) else 0
            size_mb = f"{file_size / (1024*1024):.1f} MB"

            # Phân tích độ phân giải và thông số kỹ thuật thực tế của video vừa tải
            specs = downloader.probe_video_specs(final_path) or {}
            duration_val = specs.get('duration') or (info.get('duration', 0) if isinstance(info, dict) else 0)

            v_title = (info.get('title') if isinstance(info, dict) else '') or os.path.basename(final_path)
            q.put({
                'status': 'completed',
                'task_id': task_id,
                'file_path': final_path,
                'file_name': os.path.basename(final_path),
                'file_size': size_mb,
                'title': v_title,
                'thumbnail': info.get('thumbnail', '') if isinstance(info, dict) else '',
                'duration': duration_val,
                'audio_url': f"/api/file?path={urllib.parse.quote(final_path)}",
                'specs': specs,
                'resolution': specs.get('resolution', ''),
                'resolution_label': specs.get('resolution_label', ''),
                'width': specs.get('width', 0),
                'height': specs.get('height', 0),
                'fps': specs.get('fps', 0),
                'vcodec': specs.get('vcodec', ''),
                'acodec': specs.get('acodec', ''),
                'aspect_ratio': specs.get('aspect_ratio', ''),
                'specs_summary': specs.get('summary', '')
            })

            # Gửi thông báo Telegram khi tải xong
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_per_video:
                    res_label = specs.get('resolution_label') or specs.get('resolution') or ''
                    notifier.notify_task_success(
                        task_type='download',
                        task_title='Tải Video Xuống',
                        video_title=v_title,
                        output_path=final_path,
                        duration_sec=time.time() - dl_start_time,
                        file_size_mb=file_size / (1024 * 1024) if file_size > 0 else None,
                        extra_info={
                            'Độ phân giải': res_label,
                            'Thời lượng': f"{int(duration_val // 60)}p {int(duration_val % 60)}s" if duration_val else "",
                            'Định dạng': specs.get('vcodec') or ''
                        },
                        task_id=task_id
                    )
            except Exception as _te:
                logging.getLogger(__name__).warning(f"[Telegram] Error sending download notification: {_te}")

        except Exception as e:
            err_msg = str(e)
            if cancel_event.is_set() or 'bị hủy bởi người dùng' in err_msg:
                q.put({
                    'status': 'cancelled',
                    'task_id': task_id,
                    'message': 'Đã hủy tải video'
                })
            else:
                q.put({
                    'status': 'error',
                    'task_id': task_id,
                    'error': err_msg
                })
                # Gửi thông báo Telegram khi tải thất bại
                try:
                    from telegram_notifier import get_telegram_notifier
                    notifier = get_telegram_notifier()
                    if notifier.enabled and notifier.notify_per_video:
                        notifier.notify_task_failure(
                            task_type='download',
                            task_title='Tải Video Xuống',
                            video_title=url,
                            error_message=err_msg,
                            duration_sec=time.time() - dl_start_time,
                            task_id=task_id
                        )
                except Exception as _te:
                    logging.getLogger(__name__).warning(f"[Telegram] Error sending download failure notification: {_te}")
        finally:
            with _download_lock:
                _active_downloads.pop(task_id, None)
                _download_active = len(_active_downloads) > 0

    t = threading.Thread(target=worker, daemon=True)
    t.start()

    def generate():
        while True:
            try:
                item = q.get(timeout=60)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get('status') in ['completed', 'error', 'cancelled']:
                    break
            except queue.Empty:
                yield "data: {\"status\": \"heartbeat\"}\n\n"

    return Response(generate(), mimetype='text/event-stream')


@download_bp.route('/api/download/cancel', methods=['POST'])
def api_download_cancel():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    task_id = str(data.get('task_id', '')).strip()
    cancel_all = parse_bool(data.get('all', False), False)

    with _download_lock:
        if cancel_all:
            cancelled_count = 0
            for tid, entry in list(_active_downloads.items()):
                entry['cancel_event'].set()
                cancelled_count += 1
            return jsonify({'success': True, 'cancelled_count': cancelled_count})
        elif task_id and task_id in _active_downloads:
            _active_downloads[task_id]['cancel_event'].set()
            return jsonify({'success': True, 'task_id': task_id})
        else:
            return jsonify({'success': False, 'message': 'Không tìm thấy tác vụ tải với ID này hoặc tác vụ đã kết thúc'}), 200


@download_bp.route('/api/download/active_tasks', methods=['GET'])
def api_download_active_tasks():
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    with _download_lock:
        tasks = []
        for tid, entry in _active_downloads.items():
            tasks.append({
                'task_id': tid,
                'url': entry.get('url', ''),
                'elapsed': round(time.time() - entry.get('start_time', time.time()), 1)
            })
        return jsonify({
            'success': True,
            'active_count': len(tasks),
            'tasks': tasks
        })


@download_bp.route('/api/download/queue_finished', methods=['POST'])
def api_download_queue_finished():
    """Nhận tín hiệu kết thúc toàn bộ hàng chờ tải xuống và gửi thông báo tổng kết Telegram."""
    permission_error = _require_editor()
    if permission_error:
        return permission_error
    data = request.get_json(silent=True) or {}
    total_count = int(data.get('total_count', 0))
    success_count = int(data.get('success_count', 0))
    failed_count = int(data.get('failed_count', 0))
    cancelled_count = int(data.get('cancelled_count', 0))
    elapsed_sec = float(data.get('elapsed_sec', 0))
    output_dir = str(data.get('output_dir', '')).strip()

    try:
        from telegram_notifier import get_telegram_notifier
        notifier = get_telegram_notifier()
        if notifier.enabled and notifier.notify_batch_done:
            start_ts = time.time() - elapsed_sec if elapsed_sec > 0 else time.time()
            notifier.notify_batch_completed(
                total_count=total_count,
                success_count=success_count,
                failed_count=failed_count,
                cancelled_count=cancelled_count,
                start_time=start_ts,
                end_time=time.time(),
                output_dir=output_dir or "downloads",
                batch_id=f"dl_queue_{int(time.time())}"
            )
            return jsonify({'success': True, 'notified': True})
    except Exception as e:
        logging.getLogger(__name__).warning(f"[Telegram] Error sending download queue summary: {e}")

    return jsonify({'success': True, 'notified': False})


@download_bp.route('/api/download/probe', methods=['POST'])
def api_download_probe():
    """
    API phân tích thông số kỹ thuật & độ phân giải của file video cục bộ hoặc link online
    """
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import downloader
        data = request.get_json(silent=True) or {}
        file_path = str(data.get('file_path', '')).strip()
        url = str(data.get('url', '')).strip()

        if file_path:
            if not is_path_allowed(file_path, must_exist=True):
                return jsonify({'error': 'Đường dẫn tệp không được phép hoặc không tồn tại'}), 403
            specs = downloader.probe_video_specs(file_path)
            if not specs or 'error' in specs:
                return jsonify({'error': specs.get('error', 'Không thể phân tích tệp video') if specs else 'Không thể đọc tệp'}), 400
            return jsonify({'success': True, 'type': 'file', 'specs': specs})

        if url:
            if not _validate_media_page_url(url):
                return jsonify({'error': 'URL không hợp lệ hoặc không thuộc nền tảng hỗ trợ'}), 400
            info = downloader.extract_video_info(url)
            if 'error' in info:
                return jsonify({'error': info['error']}), 400
            return jsonify({'success': True, 'type': 'url', 'info': info})

        return jsonify({'error': 'Vui lòng cung cấp file_path hoặc url để phân tích'}), 400
    except Exception as e:
        return jsonify({'error': f"Lỗi phân tích: {str(e)}"}), 500


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
        norm_target = os.path.normpath(target_path)
        if os.path.isdir(norm_target):
            if os.name == 'nt':
                try:
                    os.startfile(norm_target)
                except Exception:
                    subprocess.Popen(f'explorer "{norm_target}"', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen(['xdg-open', norm_target], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            if os.name == 'nt':
                try:
                    subprocess.Popen(f'explorer /select,"{norm_target}"', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    os.startfile(os.path.dirname(norm_target))
            else:
                subprocess.Popen(['xdg-open', os.path.dirname(norm_target)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return jsonify({'success': True})
    if target_path:
        return jsonify({'success': False, 'error': 'Đường dẫn không hợp lệ hoặc chưa được cho phép'}), 403
    
    default_folder = os.path.join(USER_DATA_DIR, 'downloads')
    os.makedirs(default_folder, exist_ok=True)
    norm_default = os.path.normpath(default_folder)
    if os.name == 'nt':
        try:
            os.startfile(norm_default)
        except Exception:
            subprocess.Popen(f'explorer "{norm_default}"', stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(['xdg-open', norm_default], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return jsonify({'success': True})


@download_bp.route('/api/download/douyin/scan_channel_stream', methods=['POST'])
def api_download_douyin_scan_channel_stream():
    global _douyin_scan_active
    """
    API quét kênh hoặc bộ sưu tập Douyin thời gian thực qua Server-Sent Events (SSE Stream).
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader, queue, threading, json
    data = request.get_json(silent=True) or {}
    channel_url = str(data.get('channel_url', '')).strip()
    source_type = str(data.get('source_type', 'channel')).strip().lower()
    limit = data.get('limit', 50)

    if not channel_url or not _valid_douyin_source(channel_url):
        return jsonify({'error': 'Vui lòng nhập đường dẫn kênh, bộ sưu tập hoặc mã sec_uid/mix_id của Douyin'}), 400

    try:
        limit = int(limit) if limit and str(limit).isdigit() else 50
        if limit <= 0 or limit > 500:
            limit = 50
    except Exception:
        limit = 50

    with _download_lock:
        if _douyin_scan_active:
            return jsonify({'error': 'Một tác vụ quét Douyin khác đang chạy'}), 409
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
            mix_id = douyin_browser_downloader.extract_mix_id(channel_url)
            if source_type == 'collection' or mix_id:
                result = crawler.scan_collection_videos(channel_url, limit=limit, progress_cb=progress_callback)
            else:
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
    API quét toàn bộ hoặc N video mới nhất từ một kênh/bộ sưu tập Douyin (Fallback Synchronous).
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader
    data = request.get_json(silent=True) or {}
    channel_url = str(data.get('channel_url', '')).strip()
    source_type = str(data.get('source_type', 'channel')).strip().lower()
    limit = data.get('limit', 50)

    if not channel_url or not _valid_douyin_source(channel_url):
        return jsonify({'error': 'Vui lòng nhập đường dẫn kênh, bộ sưu tập hoặc mã sec_uid/mix_id của Douyin'}), 400

    try:
        limit = int(limit) if limit and str(limit).isdigit() else 50
        if limit <= 0 or limit > 500:
            limit = 50
    except Exception:
        limit = 50

    with _download_lock:
        if _douyin_scan_active:
            return jsonify({'error': 'Một tác vụ quét Douyin khác đang chạy'}), 409
        _douyin_scan_active = True
    try:
        crawler = douyin_browser_downloader.DouyinBrowserDownloader()
        mix_id = douyin_browser_downloader.extract_mix_id(channel_url)
        if source_type == 'collection' or mix_id:
            result = crawler.scan_collection_videos(channel_url, limit=limit)
        else:
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
    max_workers = int(data.get('max_workers', 3))
    connections_per_file = int(data.get('connections_per_file', 2))
    prefix_index = parse_bool(data.get('prefix_index', True), True)
    auto_merge = parse_bool(data.get('auto_merge', False), False)
    merge_mode = str(data.get('merge_mode', 'auto')).strip()
    sort_order = str(data.get('sort_order', 'as_is')).strip()

    if not videos or not isinstance(videos, list):
        return jsonify({'error': 'Danh sách video tải xuống rỗng'}), 400

    if sort_order in ('oldest_first', 'newest_first'):
        videos = douyin_browser_downloader.sort_videos_chronological(videos, order=sort_order)

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
            batch_result = douyin_browser_downloader.download_channel_batch(
                video_list=videos,
                output_dir=output_dir,
                channel_name=channel_name,
                max_workers=max_workers,
                connections_per_file=connections_per_file,
                prefix_index=prefix_index,
                auto_merge=auto_merge,
                merge_mode=merge_mode,
                progress_cb=progress_callback
            )
            downloaded_files = batch_result.get("downloaded_files", [])
            merged_file = batch_result.get("merged_file")
            manifest_path = batch_result.get("manifest_path")
            q.put({
                'status': 'completed',
                'downloaded_count': len(downloaded_files),
                'total_requested': len(videos),
                'output_dir': output_dir,
                'files': downloaded_files,
                'merged_file': merged_file,
                'manifest_path': manifest_path
            })
            # Gửi thông báo tổng kết Telegram khi tải batch Douyin hoàn tất
            try:
                from telegram_notifier import get_telegram_notifier
                notifier = get_telegram_notifier()
                if notifier.enabled and notifier.notify_batch_done:
                    tot = len(videos)
                    succ = len(downloaded_files)
                    fail = max(0, tot - succ)
                    notifier.notify_batch_completed(
                        total_count=tot,
                        success_count=succ,
                        failed_count=fail,
                        output_dir=output_dir,
                        batch_id=f"douyin_batch_{int(time.time())}"
                    )
            except Exception as _te:
                logging.getLogger(__name__).warning(f"[Telegram] Error sending Douyin batch notification: {_te}")
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


@download_bp.route('/api/download/douyin/retry_failed', methods=['POST'])
def api_download_douyin_retry_failed():
    """
    API tải lại các video bị lỗi từ batch_manifest.json
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader, queue, threading, json
    data = request.get_json(silent=True) or {}
    output_dir = data.get('output_dir', '').strip()
    manifest_path = data.get('manifest_path', '').strip()
    target_path = manifest_path or output_dir

    if not target_path:
        return jsonify({'error': 'Vui lòng cung cấp output_dir hoặc manifest_path'}), 400

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
            res = douyin_browser_downloader.retry_failed_batch_items(
                target_path,
                max_workers=int(data.get('max_workers', 3)),
                connections_per_file=int(data.get('connections_per_file', 2)),
                progress_cb=progress_callback
            )
            q.put({
                'status': 'completed',
                'result': res
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


@download_bp.route('/api/download/douyin/merge', methods=['POST'])
def api_download_douyin_merge():
    """
    API ghép nối các tập video Douyin đã tải.
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import downloader
    data = request.get_json(silent=True) or {}
    files = data.get('files', [])
    output_path = data.get('output_path', '').strip()
    output_dir = data.get('output_dir', '').strip()
    merge_mode = str(data.get('merge_mode', 'auto')).strip()

    if not files and output_dir:
        if os.path.exists(output_dir):
            files = sorted([
                os.path.join(output_dir, f) for f in os.listdir(output_dir)
                if f.lower().endswith('.mp4') and not f.startswith('Merged_')
            ])

    if not files or len(files) < 2:
        return jsonify({'error': 'Cần ít nhất 2 video để ghép nối'}), 400

    if not output_path:
        dir_name = os.path.dirname(files[0])
        output_path = os.path.join(dir_name, "Merged_Collection.mp4")

    try:
        merged_file = downloader.merge_collection_episodes(files, output_path, merge_mode=merge_mode)
        try:
            from telegram_notifier import get_telegram_notifier
            notifier = get_telegram_notifier()
            if notifier.enabled and notifier.notify_per_video:
                notifier.notify_task_success(
                    task_type='download',
                    task_title='Ghép Video Douyin',
                    video_title=os.path.basename(merged_file),
                    output_path=merged_file,
                    extra_info={'Số tập ghép': len(files), 'Chế độ': merge_mode}
                )
        except Exception as _te:
            logging.getLogger(__name__).warning(f"[Telegram] Error sending merge notification: {_te}")
        return jsonify({'success': True, 'merged_file': merged_file})
    except Exception as e:
        return jsonify({'error': f"Lỗi ghép video: {str(e)}"}), 500



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


# =========================================================================
# DOUYIN ACCOUNT & COOKIE API ROUTES
# =========================================================================
@download_bp.route('/api/download/douyin/status', methods=['GET'])
def api_download_douyin_status():
    """Kiểm tra trạng thái đăng nhập Douyin (xác minh cookie với server Douyin)"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import douyin_cookie_manager
        has_file = douyin_cookie_manager.is_douyin_logged_in()
        verify = {'valid': False, 'uname': None, 'user_id': None, 'sec_uid': None, 'avatar_url': None, 'description': None}
        if has_file:
            try:
                verify = douyin_cookie_manager.verify_douyin_cookie()
            except Exception as _e:
                verify['description'] = str(_e)

        return jsonify({
            'success': True,
            'logged_in': has_file,
            'cookie_valid': verify['valid'],
            'uname': verify.get('uname'),
            'user_id': verify.get('user_id'),
            'sec_uid': verify.get('sec_uid'),
            'avatar_url': verify.get('avatar_url'),
            'description': verify.get('description')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@download_bp.route('/api/download/douyin/save_cookie', methods=['POST'])
def api_download_douyin_save_cookie():
    """Lưu Cookie Douyin thủ công và xác thực ngay"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import douyin_cookie_manager
        data = request.get_json(silent=True) or {}
        cookie_text = str(data.get('cookie', '')).strip()
        if not cookie_text:
            return jsonify({'error': 'Vui lòng nhập Cookie hoặc sessionid Douyin'}), 400
        ok = douyin_cookie_manager.save_douyin_cookie(cookie_text)
        if not ok:
            return jsonify({'error': 'Không thể định dạng hoặc lưu Cookie'}), 400

        verify = douyin_cookie_manager.verify_douyin_cookie()
        return jsonify({
            'success': True,
            'cookie_valid': verify['valid'],
            'uname': verify.get('uname'),
            'avatar_url': verify.get('avatar_url'),
            'message': 'Đã lưu và xác thực Cookie Douyin thành công!' if verify['valid'] else f"Đã lưu Cookie nhưng: {verify.get('description', 'Chưa thể xác minh')}"
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@download_bp.route('/api/download/douyin/logout', methods=['POST'])
def api_download_douyin_logout():
    """Đăng xuất và xóa Cookie Douyin"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import douyin_cookie_manager
        douyin_cookie_manager.clear_douyin_cookie()
        return jsonify({'success': True, 'message': 'Đã đăng xuất tài khoản Douyin thành công.'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@download_bp.route('/api/download/douyin/open_login', methods=['POST'])
def api_download_douyin_open_login():
    """
    API mở trình duyệt để người dùng đăng nhập Douyin 1 lần duy nhất (vượt giới hạn 18 video của khách).
    """
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import douyin_browser_downloader, threading
        crawler = douyin_browser_downloader.DouyinBrowserDownloader(headless=False)
        t = threading.Thread(target=crawler.open_login_window, daemon=True)
        t.start()
        return jsonify({'success': True, 'message': 'Đang mở cửa sổ trình duyệt để đăng nhập...'})
    except Exception as e:
        return jsonify({'error': f"Lỗi mở trình duyệt đăng nhập: {str(e)}"}), 500


# =========================================================================
# BILIBILI BBDown API ROUTES
# =========================================================================
@download_bp.route('/api/download/bilibili/status', methods=['GET'])
def api_download_bilibili_status():
    """Kiểm tra trạng thái đăng nhập Bilibili (bao gồm xác minh cookie với server)"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import bilibili_downloader
        has_file = bilibili_downloader.is_bilibili_logged_in()
        has_bbdown = bilibili_downloader.get_bbdown_path() is not None

        # Xác minh cookie thực sự với Bilibili API (không chỉ check file tồn tại)
        verify = {'valid': False, 'uname': None, 'is_vip': False, 'mid': None}
        if has_file:
            try:
                verify = bilibili_downloader.verify_bilibili_cookie()
            except Exception:
                pass

        return jsonify({
            'success': True,
            'logged_in': has_file,           # Cookie file tồn tại (legacy compat)
            'cookie_valid': verify['valid'],  # Cookie còn hoạt động với server
            'uname': verify.get('uname'),
            'is_vip': verify.get('is_vip', False),
            'mid': verify.get('mid'),
            'has_bbdown': has_bbdown
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@download_bp.route('/api/download/bilibili/login_qr', methods=['POST'])
def api_download_bilibili_login_qr():
    """Khởi động lấy mã QR đăng nhập Bilibili bằng BBDown"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import bilibili_downloader
        res = bilibili_downloader.start_qr_login()
        if not res.get('success'):
            return jsonify({'error': res.get('error', 'Không thể tạo mã QR')}), 400
        return jsonify(res)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@download_bp.route('/api/download/bilibili/login_poll', methods=['GET'])
def api_download_bilibili_login_poll():
    """Kiểm tra trạng thái quét mã QR Bilibili"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import bilibili_downloader
        res = bilibili_downloader.poll_qr_login_status()
        return jsonify(res)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@download_bp.route('/api/download/bilibili/save_cookie', methods=['POST'])
def api_download_bilibili_save_cookie():
    """Lưu Cookie hoặc SESSDATA Bilibili thủ công"""
    try:
        permission_error = _require_editor()
        if permission_error:
            return permission_error
        import bilibili_downloader
        data = request.get_json(silent=True) or {}
        cookie_text = str(data.get('cookie', '')).strip()
        if not cookie_text:
            return jsonify({'error': 'Vui lòng nhập Cookie hoặc SESSDATA'}), 400
        ok = bilibili_downloader.save_bilibili_cookie(cookie_text)
        if ok:
            return jsonify({'success': True, 'message': 'Đã lưu Cookie Bilibili thành công!'})
        return jsonify({'error': 'Không thể lưu Cookie'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500
