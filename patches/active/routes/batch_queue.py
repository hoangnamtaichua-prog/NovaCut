from flask import Blueprint, jsonify, request, Response
import os
import json
import queue
import subprocess
from batch_queue_manager import BatchQueueManager
import license_manager
from routes.security import is_path_allowed, parse_bool

def _ps_literal(value):
    return "'" + str(value or '').replace("'", "''") + "'"

batch_queue_bp = Blueprint('batch_queue', __name__)

def _require_batch_permission():
    allowed, perm_msg, _ = license_manager.check_permission('can_access_batch')
    if not allowed:
        return jsonify({'error': perm_msg}), 403
    return None

@batch_queue_bp.route('/api/batch/state', methods=['GET'])
def api_batch_state():
    denied = _require_batch_permission()
    if denied:
        return denied
    mgr = BatchQueueManager.get_instance()
    return jsonify(mgr.get_state())

@batch_queue_bp.route('/api/batch/add', methods=['POST'])
def api_batch_add():
    denied = _require_batch_permission()
    if denied:
        return denied

    data = request.json or {}
    items = data.get('items', [])
    preset = data.get('preset', 'review')
    preset_config = data.get('preset_config', {})

    if not isinstance(items, list) or not items:
        return jsonify({'error': 'Danh sách nạp vào hàng đợi không được để trống'}), 400

    mgr = BatchQueueManager.get_instance()
    added = mgr.add_tasks(items, preset=preset, preset_config=preset_config)
    return jsonify({
        'success': True,
        'added_count': len(added),
        'added_tasks': added,
        'state': mgr.get_state()
    })

@batch_queue_bp.route('/api/batch/start', methods=['POST'])
def api_batch_start():
    denied = _require_batch_permission()
    if denied:
        return denied

    mgr = BatchQueueManager.get_instance()
    success = mgr.start_queue()
    return jsonify({'success': success, 'state': mgr.get_state()}), (200 if success else 409)

@batch_queue_bp.route('/api/batch/pause', methods=['POST'])
def api_batch_pause():
    denied = _require_batch_permission()
    if denied:
        return denied
    mgr = BatchQueueManager.get_instance()
    success = mgr.pause_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/resume', methods=['POST'])
def api_batch_resume():
    denied = _require_batch_permission()
    if denied:
        return denied

    mgr = BatchQueueManager.get_instance()
    success = mgr.resume_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/stop', methods=['POST'])
def api_batch_stop():
    denied = _require_batch_permission()
    if denied:
        return denied
    mgr = BatchQueueManager.get_instance()
    success = mgr.stop_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/retry', methods=['POST'])
def api_batch_retry():
    denied = _require_batch_permission()
    if denied:
        return denied
    data = request.json or {}
    task_id = data.get('task_id')
    mgr = BatchQueueManager.get_instance()

    if task_id:
        success = mgr.retry_task(task_id)
        return jsonify({'success': success, 'state': mgr.get_state()}), (200 if success else 404)
    else:
        count = mgr.retry_failed_tasks()
        return jsonify({'success': True, 'retried_count': count, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/remove', methods=['POST'])
def api_batch_remove():
    denied = _require_batch_permission()
    if denied:
        return denied
    data = request.json or {}
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'error': 'Thiếu task_id'}), 400

    mgr = BatchQueueManager.get_instance()
    success = mgr.remove_task(task_id)
    return jsonify({'success': success, 'state': mgr.get_state()}), (200 if success else 404)

@batch_queue_bp.route('/api/batch/clear', methods=['POST'])
def api_batch_clear():
    denied = _require_batch_permission()
    if denied:
        return denied
    data = request.json or {}
    try:
        completed_only = parse_bool(data.get('completed_only', False))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    mgr = BatchQueueManager.get_instance()
    mgr.clear_queue(completed_only=completed_only)
    return jsonify({'success': True, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/reorder', methods=['POST'])
def api_batch_reorder():
    denied = _require_batch_permission()
    if denied:
        return denied
    data = request.json or {}
    task_id = data.get('task_id')
    new_index = data.get('new_index')
    if task_id is None or new_index is None:
        return jsonify({'error': 'Thiếu thông tin sắp xếp'}), 400

    mgr = BatchQueueManager.get_instance()
    try:
        parsed_index = int(new_index)
    except (TypeError, ValueError):
        return jsonify({'error': 'Vị trí sắp xếp không hợp lệ'}), 400
    success = mgr.reorder_task(task_id, parsed_index)
    return jsonify({'success': success, 'state': mgr.get_state()}), (200 if success else 404)

@batch_queue_bp.route('/api/batch/config', methods=['POST'])
def api_batch_config():
    denied = _require_batch_permission()
    if denied:
        return denied
    data = request.json or {}
    auto_shutdown = data.get('auto_shutdown_pc')
    output_dir = data.get('default_output_dir')
    if output_dir and not is_path_allowed(output_dir):
        return jsonify({'error': 'Thư mục đầu ra chưa được người dùng cho phép'}), 403
    mgr = BatchQueueManager.get_instance()
    mgr.set_config(auto_shutdown=auto_shutdown, default_output_dir=output_dir)
    return jsonify({'success': True, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/open_output', methods=['POST'])
def api_batch_open_output():
    denied = _require_batch_permission()
    if denied:
        return denied
    data = request.json or {}
    target_path = data.get('path')
    mgr = BatchQueueManager.get_instance()

    folder = target_path or mgr.default_output_dir
    if not is_path_allowed(folder):
        return jsonify({'error': 'Đường dẫn đầu ra chưa được người dùng cho phép'}), 403
    if not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    try:
        if os.name == 'nt':
            if os.path.isfile(folder):
                subprocess.Popen(['explorer', '/select,', os.path.normpath(folder)])
            else:
                os.startfile(folder)
            return jsonify({'success': True, 'opened': folder})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

    return jsonify({'success': True})

@batch_queue_bp.route('/api/batch/cancel_shutdown', methods=['POST'])
def api_batch_cancel_shutdown():
    denied = _require_batch_permission()
    if denied:
        return denied
    success = BatchQueueManager.get_instance().cancel_pc_shutdown()
    return jsonify({'success': success}), (200 if success else 409)

@batch_queue_bp.route('/api/batch/stream', methods=['GET'])
def api_batch_stream():
    denied = _require_batch_permission()
    if denied:
        return denied
    mgr = BatchQueueManager.get_instance()
    q = queue.Queue(maxsize=100)
    mgr.subscribe(q)

    def event_stream():
        # Send initial full state immediately upon connection
        init_state = mgr.get_state()
        yield f"data: {json.dumps({'event': 'initial_state', 'data': init_state}, ensure_ascii=False)}\n\n"

        try:
            while True:
                try:
                    msg = q.get(timeout=15)
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except queue.Empty:
                    # Heartbeat ping
                    yield "data: {\"event\": \"ping\"}\n\n"
        except GeneratorExit:
            mgr.unsubscribe(q)

    return Response(event_stream(), mimetype='text/event-stream')

@batch_queue_bp.route('/api/batch/preflight', methods=['GET'])
def api_batch_preflight():
    denied = _require_batch_permission()
    if denied:
        return denied

    import ffmpeg_installer
    import asr_manager
    import auto_edit_pipeline

    ff_path = ffmpeg_installer.get_ffmpeg_path()
    has_ffmpeg = bool(ff_path and os.path.exists(ff_path))

    whisper_cli = asr_manager.get_whisper_cli()
    whisper_model = asr_manager.get_whisper_model_path("base")
    has_asr = bool(whisper_cli and whisper_model)

    openai_key, _, _ = auto_edit_pipeline.resolve_openai_credentials({})
    has_openai = bool(openai_key)

    return jsonify({
        'success': True,
        'ffmpeg': {
            'ready': has_ffmpeg,
            'path': ff_path or ''
        },
        'asr': {
            'ready': has_asr,
            'cli': whisper_cli or '',
            'model': whisper_model or ''
        },
        'ai_key': {
            'ready': has_openai
        }
    })

@batch_queue_bp.route('/api/batch/select_files', methods=['POST'])
def api_batch_select_files():
    denied = _require_batch_permission()
    if denied:
        return denied

    from routes.security import register_user_path
    data = request.json or {}
    title = data.get('title', 'Chọn các file video để xử lý hàng loạt')
    file_paths = []

    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        res = filedialog.askopenfilenames(
            title=title,
            filetypes=[
                ('Video Files', '*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v'),
                ('All Files', '*.*')
            ]
        )
        root.destroy()
        if res:
            file_paths = list(res)
    except Exception:
        file_paths = []

        try:
            ps_cmd = f"""
            Add-Type -AssemblyName System.Windows.Forms
            $f = New-Object System.Windows.Forms.OpenFileDialog
            $f.Title = {_ps_literal(title)}
            $f.Filter = 'Video Files (*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v)|*.mp4;*.mkv;*.avi;*.mov;*.flv;*.webm;*.m4v|All Files (*.*)|*.*'
            $f.Multiselect = $true
            if ($f.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {{
                $f.FileNames
            }}
            """
            proc = subprocess.run(
                ['powershell', '-WindowStyle', 'Hidden', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                capture_output=True, text=True, timeout=60,
                creationflags=0x08000000
            )
            file_paths = [p.strip() for p in proc.stdout.splitlines() if p.strip()]
        except Exception:
            pass

    valid_paths = [os.path.normpath(p) for p in file_paths if os.path.exists(p)]
    for p in valid_paths:
        register_user_path(p)

    return jsonify({
        'success': True,
        'files': valid_paths,
        'count': len(valid_paths)
    })
