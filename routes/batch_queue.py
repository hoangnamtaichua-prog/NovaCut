from flask import Blueprint, jsonify, request, Response
import os
import json
import queue
import subprocess
from batch_queue_manager import BatchQueueManager
import license_manager

batch_queue_bp = Blueprint('batch_queue', __name__)

@batch_queue_bp.route('/api/batch/state', methods=['GET'])
def api_batch_state():
    mgr = BatchQueueManager.get_instance()
    return jsonify(mgr.get_state())

@batch_queue_bp.route('/api/batch/add', methods=['POST'])
def api_batch_add():
    allowed, perm_msg, _ = license_manager.check_permission('can_access_batch')
    if not allowed:
        return jsonify({'error': perm_msg}), 403

    data = request.json or {}
    items = data.get('items', [])
    preset = data.get('preset', 'review')
    preset_config = data.get('preset_config', {})

    if not items:
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
    allowed, perm_msg, _ = license_manager.check_permission('can_access_batch')
    if not allowed:
        return jsonify({'error': perm_msg}), 403

    mgr = BatchQueueManager.get_instance()
    success = mgr.start_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/pause', methods=['POST'])
def api_batch_pause():
    mgr = BatchQueueManager.get_instance()
    success = mgr.pause_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/resume', methods=['POST'])
def api_batch_resume():
    allowed, perm_msg, _ = license_manager.check_permission('can_access_batch')
    if not allowed:
        return jsonify({'error': perm_msg}), 403

    mgr = BatchQueueManager.get_instance()
    success = mgr.resume_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/stop', methods=['POST'])
def api_batch_stop():
    mgr = BatchQueueManager.get_instance()
    success = mgr.stop_queue()
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/retry', methods=['POST'])
def api_batch_retry():
    data = request.json or {}
    task_id = data.get('task_id')
    mgr = BatchQueueManager.get_instance()

    if task_id:
        success = mgr.retry_task(task_id)
        return jsonify({'success': success, 'state': mgr.get_state()})
    else:
        count = mgr.retry_failed_tasks()
        return jsonify({'success': True, 'retried_count': count, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/remove', methods=['POST'])
def api_batch_remove():
    data = request.json or {}
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'error': 'Thiếu task_id'}), 400

    mgr = BatchQueueManager.get_instance()
    success = mgr.remove_task(task_id)
    return jsonify({'success': success, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/clear', methods=['POST'])
def api_batch_clear():
    data = request.json or {}
    completed_only = bool(data.get('completed_only', False))
    mgr = BatchQueueManager.get_instance()
    mgr.clear_queue(completed_only=completed_only)
    return jsonify({'success': True, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/reorder', methods=['POST'])
def api_batch_reorder():
    data = request.json or {}
    task_id = data.get('task_id')
    new_index = data.get('new_index')
    if task_id is None or new_index is None:
        return jsonify({'error': 'Thiếu thông tin sắp xếp'}), 400

    mgr = BatchQueueManager.get_instance()
    mgr.reorder_task(task_id, int(new_index))
    return jsonify({'success': True, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/config', methods=['POST'])
def api_batch_config():
    data = request.json or {}
    auto_shutdown = data.get('auto_shutdown_pc')
    output_dir = data.get('default_output_dir')
    mgr = BatchQueueManager.get_instance()
    mgr.set_config(auto_shutdown=auto_shutdown, default_output_dir=output_dir)
    return jsonify({'success': True, 'state': mgr.get_state()})

@batch_queue_bp.route('/api/batch/open_output', methods=['POST'])
def api_batch_open_output():
    data = request.json or {}
    target_path = data.get('path')
    mgr = BatchQueueManager.get_instance()

    folder = target_path or mgr.default_output_dir
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

@batch_queue_bp.route('/api/batch/stream', methods=['GET'])
def api_batch_stream():
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
