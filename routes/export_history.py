import os
import sys
import subprocess
import logging
from flask import Blueprint, request, jsonify

from routes.security import register_user_path
from routes.state import ROOT_DIR
import license_manager
from export_history import get_export_history_service

logger = logging.getLogger(__name__)

export_history_bp = Blueprint('export_history', __name__)

SUPPORTED_VIDEO_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v', '.wmv', '.ts'
}


def _check_export_history_permission():
    """Kiểm tra quyền truy cập lịch sử xuất video.
    Người dùng có quyền nếu sở hữu bất kỳ gói cước nào (editor, review, batch, tts).
    """
    last_msg = "Chưa kích hoạt bản quyền."
    for feat in ('can_access_editor', 'can_access_review', 'can_access_batch', 'tts_unlimited_local'):
        try:
            allowed, msg, _ = license_manager.check_permission(feat)
            if allowed:
                return True, ""
            if msg:
                last_msg = msg
        except Exception:
            pass
    return False, last_msg


@export_history_bp.before_request
def check_permission_before_request():
    allowed, msg = _check_export_history_permission()
    if not allowed:
        return jsonify({
            'success': False,
            'error': 'LICENSE_REQUIRED',
            'message': msg
        }), 403


@export_history_bp.route('/api/export-history', methods=['GET'])
def get_export_history():
    """Lấy danh sách lịch sử xuất video có phân trang, tìm kiếm và bộ lọc."""
    try:
        service = get_export_history_service()
        search = request.args.get('search', '').strip()
        source_tool = request.args.get('source_tool', '').strip()
        status = request.args.get('status', '').strip()
        from_date = request.args.get('from_date', '').strip()
        to_date = request.args.get('to_date', '').strip()
        
        try:
            page = max(1, int(request.args.get('page', 1)))
        except (TypeError, ValueError):
            page = 1
            
        try:
            limit = min(100, max(1, int(request.args.get('limit', 50))))
        except (TypeError, ValueError):
            limit = 50

        result = service.query_exports(
            search=search,
            source_tool=source_tool,
            status=status,
            from_date=from_date,
            to_date=to_date,
            page=page,
            limit=limit
        )
        return jsonify({
            'success': True,
            'items': result['items'],
            'total': result['total'],
            'page': result['page'],
            'limit': result['limit'],
            'total_pages': result['total_pages']
        })
    except Exception as e:
        logger.error(f"[ExportHistory] Error querying exports: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': 'INTERNAL_ERROR',
            'message': str(e)
        }), 500


@export_history_bp.route('/api/export-history/<record_id>', methods=['GET'])
def get_export_detail(record_id):
    """Lấy chi tiết 1 bản ghi lịch sử xuất."""
    try:
        service = get_export_history_service()
        item = service.get_export_by_id(record_id)
        if not item:
            return jsonify({
                'success': False,
                'error': 'NOT_FOUND',
                'message': 'Không tìm thấy bản ghi lịch sử'
            }), 404
        return jsonify({'success': True, 'item': item})
    except Exception as e:
        logger.error(f"[ExportHistory] Error getting export detail {record_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@export_history_bp.route('/api/export-history/<record_id>/open', methods=['POST'])
def open_export_video(record_id):
    """Mở phát video mặc định của hệ thống theo ID bảo mật từ DB."""
    try:
        service = get_export_history_service()
        item = service.get_export_by_id(record_id)
        if not item:
            return jsonify({
                'success': False,
                'error': 'NOT_FOUND',
                'message': 'Không tìm thấy bản ghi lịch sử'
            }), 404

        output_path = str(item.get('output_path') or '').strip().strip('"\'')
        if not output_path:
            return jsonify({
                'success': False,
                'error': 'INVALID_PATH',
                'message': 'Đường dẫn tệp video trống hoặc không hợp lệ'
            }), 400

        if not os.path.isabs(output_path):
            output_path = os.path.abspath(os.path.join(ROOT_DIR, output_path))
        norm_path = os.path.normpath(output_path)
        
        # Kiểm tra phần mở rộng video hợp lệ
        ext = os.path.splitext(norm_path)[1].lower()
        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
            return jsonify({
                'success': False,
                'error': 'INVALID_FILE_TYPE',
                'message': f'Định dạng tệp không được hỗ trợ: {ext}'
            }), 400

        if not os.path.exists(norm_path) or not os.path.isfile(norm_path):
            return jsonify({
                'success': False,
                'error': 'FILE_NOT_FOUND',
                'message': 'Tệp video không còn tồn tại tại đường dẫn đã lưu'
            }), 404

        # Cho phép đường dẫn trong hệ thống an ninh
        register_user_path(norm_path)

        # Mở file an toàn trên Windows
        if os.name == 'nt':
            os.startfile(norm_path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', norm_path])
        else:
            subprocess.Popen(['xdg-open', norm_path])

        return jsonify({
            'success': True,
            'message': 'Đã mở video thành công',
            'path': norm_path
        })
    except Exception as e:
        logger.error(f"[ExportHistory] Error opening video {record_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Lỗi khi mở video: {str(e)}"}), 500


@export_history_bp.route('/api/export-history/<record_id>/reveal', methods=['POST'])
def reveal_export_folder(record_id):
    """Mở File Explorer và chọn tệp video theo ID từ DB."""
    try:
        service = get_export_history_service()
        item = service.get_export_by_id(record_id)
        if not item:
            return jsonify({
                'success': False,
                'error': 'NOT_FOUND',
                'message': 'Không tìm thấy bản ghi lịch sử'
            }), 404

        output_path = str(item.get('output_path') or '').strip().strip('"\'')
        if not output_path:
            return jsonify({
                'success': False,
                'error': 'INVALID_PATH',
                'message': 'Đường dẫn tệp video trống hoặc không hợp lệ'
            }), 400

        if not os.path.isabs(output_path):
            output_path = os.path.abspath(os.path.join(ROOT_DIR, output_path))

        # Phân giải realpath để lấy đúng ký tự hoa/thường trên hệ thống tệp
        try:
            if os.path.exists(output_path):
                output_path = os.path.realpath(output_path)
        except Exception:
            pass

        norm_path = os.path.normpath(output_path)
        # Chuẩn hóa ký tự ổ đĩa trên Windows thành chữ HOA (C:\, D:\, G:\)
        if os.name == 'nt' and len(norm_path) >= 2 and norm_path[1] == ':':
            norm_path = norm_path[0].upper() + norm_path[1:]

        folder = os.path.dirname(norm_path) if not os.path.isdir(norm_path) else norm_path
        if os.name == 'nt' and len(folder) >= 2 and folder[1] == ':':
            folder = folder[0].upper() + folder[1:]

        # Nếu thư mục cụ thể không còn tồn tại, tìm thư mục cha gần nhất còn tồn tại
        if not os.path.exists(folder):
            curr = folder
            fallback_folder = None
            for _ in range(5):
                parent = os.path.dirname(curr)
                if parent and parent != curr and os.path.isdir(parent):
                    fallback_folder = parent
                    break
                curr = parent
            if fallback_folder:
                folder = fallback_folder
            else:
                return jsonify({
                    'success': False,
                    'error': 'FOLDER_NOT_FOUND',
                    'message': f'Thư mục chứa tệp không còn tồn tại trên ổ đĩa ({folder})'
                }), 404

        register_user_path(norm_path)
        register_user_path(folder)

        if os.path.exists(norm_path) and not os.path.isdir(norm_path):
            if os.name == 'nt':
                # Trên Windows:
                # 1. Ổ đĩa ảo/mạng như Google Drive (G:\) hoặc đường dẫn UNC (\\) không tương thích với explorer /select
                #    và sẽ tự động rơi về thư mục Documents mặc định -> mở thẳng thư mục qua os.startfile.
                # 2. Với ổ đĩa cục bộ, explorer /select,"<norm_path>" yêu cầu ổ đĩa viết HOA và nháy kép.
                is_cloud_or_virtual = norm_path.upper().startswith(('G:', '\\\\')) or 'GOOGLE DRIVE' in norm_path.upper()
                if not is_cloud_or_virtual:
                    try:
                        subprocess.Popen(f'explorer /select,"{norm_path}"')
                    except Exception:
                        try:
                            os.startfile(folder)
                        except Exception:
                            subprocess.Popen(f'explorer "{folder}"')
                else:
                    try:
                        os.startfile(folder)
                    except Exception:
                        subprocess.Popen(f'explorer "{folder}"')
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', norm_path])
            else:
                subprocess.Popen(['xdg-open', folder])
            return jsonify({
                'success': True,
                'message': f'Đã mở thư mục lưu trữ video trong File Explorer: {folder}',
                'path': norm_path,
                'folder': folder
            })
        elif os.path.exists(folder):
            if os.name == 'nt':
                try:
                    os.startfile(folder)
                except Exception:
                    subprocess.Popen(f'explorer "{folder}"')
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', folder])
            else:
                subprocess.Popen(['xdg-open', folder])
            return jsonify({
                'success': True,
                'message': f'Đã mở thư mục lưu trữ trong File Explorer: {folder}',
                'path': folder,
                'folder': folder
            })
        else:
            return jsonify({
                'success': False,
                'error': 'FOLDER_NOT_FOUND',
                'message': f'Thư mục chứa tệp không còn tồn tại trên ổ đĩa ({folder})'
            }), 404
    except Exception as e:
        logger.error(f"[ExportHistory] Error revealing folder {record_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': f"Lỗi khi mở thư mục: {str(e)}"}), 500


@export_history_bp.route('/api/export-history/<record_id>', methods=['DELETE'])
def delete_export_record(record_id):
    """Xóa bản ghi lịch sử khỏi SQLite (KHÔNG xóa tệp video trên ổ đĩa)."""
    try:
        service = get_export_history_service()
        success = service.delete_export(record_id)
        if not success:
            return jsonify({
                'success': False,
                'error': 'NOT_FOUND',
                'message': 'Không tìm thấy bản ghi cần xóa'
            }), 404
        return jsonify({
            'success': True,
            'message': 'Đã xóa bản ghi lịch sử'
        })
    except Exception as e:
        logger.error(f"[ExportHistory] Error deleting record {record_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@export_history_bp.route('/api/export-history', methods=['DELETE'])
def clear_all_export_history():
    """Xóa TOÀN BỘ lịch sử xuất video khỏi SQLite DB (KHÔNG xóa file trên ổ đĩa)."""
    try:
        service = get_export_history_service()
        deleted_count = service.clear_all_exports()
        return jsonify({
            'success': True,
            'deleted_count': deleted_count,
            'message': f'Đã xóa {deleted_count} bản ghi lịch sử'
        })
    except Exception as e:
        logger.error(f"[ExportHistory] Error clearing all history: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@export_history_bp.route('/api/export-history/import/scan', methods=['POST'])
def start_import_scan():
    """Bắt đầu quét thư mục để tìm video cũ cần nhập vào lịch sử."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        folder_path = data.get('folder_path', '').strip()
        include_subfolders = bool(data.get('include_subfolders', False))

        if not folder_path:
            return jsonify({
                'success': False,
                'error': 'MISSING_PATH',
                'message': 'Vui lòng cung cấp đường dẫn thư mục cần quét'
            }), 400

        norm_path = os.path.normpath(folder_path)
        if not os.path.exists(norm_path) or not os.path.isdir(norm_path):
            return jsonify({
                'success': False,
                'error': 'INVALID_FOLDER',
                'message': 'Thư mục không tồn tại hoặc không phải là thư mục hợp lệ'
            }), 400

        register_user_path(norm_path)

        service = get_export_history_service()
        scan_id = service.start_import_scan(norm_path, include_subfolders=include_subfolders)

        return jsonify({
            'success': True,
            'scan_id': scan_id,
            'message': 'Bắt đầu quét thư mục video'
        })
    except Exception as e:
        logger.error(f"[ExportHistory] Error starting import scan: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@export_history_bp.route('/api/export-history/import/scan/<scan_id>', methods=['GET'])
def get_import_scan_progress(scan_id):
    """Lấy tiến độ quét thư mục import."""
    try:
        service = get_export_history_service()
        progress = service.get_import_scan_progress(scan_id)
        if not progress:
            return jsonify({
                'success': False,
                'error': 'SCAN_NOT_FOUND',
                'message': 'Không tìm thấy phiên quét'
            }), 404
        return jsonify({'success': True, 'scan': progress})
    except Exception as e:
        logger.error(f"[ExportHistory] Error getting scan progress {scan_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@export_history_bp.route('/api/export-history/import/scan/<scan_id>/cancel', methods=['POST'])
def cancel_import_scan(scan_id):
    """Hủy tiến trình quét import đang chạy."""
    try:
        service = get_export_history_service()
        success = service.cancel_import_scan(scan_id)
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"[ExportHistory] Error cancelling scan {scan_id}: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500


@export_history_bp.route('/api/export-history/import/commit', methods=['POST'])
def commit_import_candidates():
    """Lưu các ứng viên video được chọn vào SQLite DB."""
    try:
        data = request.get_json(force=True, silent=True) or {}
        scan_id = data.get('scan_id', '').strip()
        candidates = data.get('selected_candidates', [])

        if not candidates or not isinstance(candidates, list):
            return jsonify({
                'success': False,
                'error': 'NO_CANDIDATES',
                'message': 'Không có video nào được chọn để nhập'
            }), 400

        service = get_export_history_service()
        result = service.commit_import_candidates(scan_id, candidates)

        return jsonify({
            'success': True,
            'imported_count': result['imported_count'],
            'skipped_count': result['skipped_count'],
            'message': f"Đã nhập thành công {result['imported_count']} video vào lịch sử"
        })
    except Exception as e:
        logger.error(f"[ExportHistory] Error committing import: {e}", exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500
