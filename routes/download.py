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
    file_path = data.get('file_path', '')
    if not file_path or not os.path.exists(file_path):
        folder = os.path.join(ROOT_DIR, 'downloads')
        os.makedirs(folder, exist_ok=True)
        subprocess.Popen(f'explorer "{folder}"')
        return jsonify({'success': True})
    
    subprocess.Popen(f'explorer /select,"{file_path}"')
    return jsonify({'success': True})

