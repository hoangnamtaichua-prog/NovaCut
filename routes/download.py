from flask import Blueprint, jsonify, request, send_from_directory, send_file, Response
import os, subprocess, sys, mimetypes, json, logging, traceback, re, time, threading
from routes.state import *
import asr_manager

download_bp = Blueprint('download', __name__)

@download_bp.route('/api/download/info', methods=['POST'])
def api_download_info():
    try:
        import downloader
        data = request.json or {}
        url = data.get('url', '').strip()
        if not url:
            return jsonify({'error': 'Vui lòng nhập liên kết video'}), 400
        
        result = downloader.extract_video_info(url)
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': f"Lỗi phân tích: {str(e)}"}), 500

@download_bp.route('/api/download/start', methods=['POST'])
def api_download_start():
    import downloader, queue, threading, urllib.parse, json
    data = request.json or {}
    url = data.get('url', '').strip()
    format_id = data.get('format_id', 'best')
    is_audio = data.get('is_audio', False)
    output_dir = data.get('output_dir', '').strip()
    video_urls = data.get('video_urls')
    info_payload = data.get('info')
    
    if not output_dir:
        output_dir = os.path.join(ROOT_DIR, 'downloads')
    os.makedirs(output_dir, exist_ok=True)
    
    if not url:
        return jsonify({'error': 'Vui lòng cung cấp URL video'}), 400

    q = queue.Queue()

    def progress_callback(prog_data):
        q.put(prog_data)

    def worker():
        try:
            final_path, info = downloader.download_media(
                url=url,
                format_id=format_id,
                is_audio=is_audio,
                output_dir=output_dir,
                progress_callback=progress_callback,
                info=info_payload,
                video_urls=video_urls
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
    import subprocess
    data = request.json or {}
    folder_path = data.get('folder_path', '').strip()
    file_path = data.get('file_path', '').strip()
    
    target_path = folder_path or file_path
    if target_path and os.path.exists(target_path):
        if os.path.isdir(target_path):
            subprocess.Popen(f'explorer "{os.path.normpath(target_path)}"')
        else:
            subprocess.Popen(f'explorer /select,"{os.path.normpath(target_path)}"')
        return jsonify({'success': True})
    
    default_folder = os.path.join(ROOT_DIR, 'downloads')
    os.makedirs(default_folder, exist_ok=True)
    subprocess.Popen(f'explorer "{os.path.normpath(default_folder)}"')
    return jsonify({'success': True})


@download_bp.route('/api/download/douyin/scan_channel_stream', methods=['POST'])
def api_download_douyin_scan_channel_stream():
    """
    API quét kênh Douyin thời gian thực qua Server-Sent Events (SSE Stream).
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader, queue, threading, json
    data = request.json or {}
    channel_url = data.get('channel_url', '').strip()
    limit = data.get('limit', 30)

    if not channel_url:
        return jsonify({'error': 'Vui lòng nhập đường dẫn kênh hoặc mã sec_uid của Douyin'}), 400

    try:
        limit = int(limit) if limit and str(limit).isdigit() else 30
        if limit <= 0 or limit > 300:
            limit = 30
    except Exception:
        limit = 30

    q = queue.Queue()

    def progress_callback(pct, msg):
        q.put({
            'status': 'progress',
            'pct': pct,
            'msg': msg
        })

    def worker():
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
    """
    API quét toàn bộ hoặc N video mới nhất từ một kênh Douyin (Fallback Synchronous).
    """
    import license_manager
    allowed, perm_msg, _ = license_manager.check_permission('can_access_editor')
    if not allowed:
        return jsonify({'error': f"Chức năng bị khóa: {perm_msg}", 'license_required': True}), 403

    import douyin_browser_downloader
    data = request.json or {}
    channel_url = data.get('channel_url', '').strip()
    limit = data.get('limit', 30)

    if not channel_url:
        return jsonify({'error': 'Vui lòng nhập đường dẫn kênh hoặc mã sec_uid của Douyin'}), 400

    try:
        limit = int(limit) if limit and str(limit).isdigit() else 30
        if limit <= 0 or limit > 300:
            limit = 30
    except Exception:
        limit = 30

    try:
        crawler = douyin_browser_downloader.DouyinBrowserDownloader()
        result = crawler.scan_channel_videos(channel_url, limit=limit)
        return jsonify(result)
    except Exception as e:
        import traceback
        logging.error(f"[Douyin Channel Scan Error] {traceback.format_exc()}")
        return jsonify({'error': f"Lỗi quét kênh Douyin: {str(e)}"}), 500


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




