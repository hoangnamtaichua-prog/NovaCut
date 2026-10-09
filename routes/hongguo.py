# -*- coding: utf-8 -*-
"""
NovaCut - Hongguo Downloader Gateway API Blueprint
Định tuyến và điều phối các tác vụ tải phim Hồng Quả, bảo vệ bản quyền 2 lớp
và tự động đăng ký quyền truy cập an toàn cho WebView2.
"""

import os
import sys
import re
import json
import logging
import functools
import subprocess
import urllib.parse
from flask import Blueprint, jsonify, request
import license_manager

hongguo_bp = Blueprint('hongguo', __name__, url_prefix='/api/hongguo')
logger = logging.getLogger(__name__)

# Windows DOS reserved device names and illegal path traversal characters
WINDOWS_RESERVED_NAMES = {
    'con', 'prn', 'aux', 'nul',
    'conin$', 'conout$',
    'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
    'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9'
}
FORBIDDEN_NAME_CHARS = ('/', '\\', '\0', ':', '*', '?', '"', '<', '>', '|', '\r', '\n')


def _ensure_path_registered(path: str):
    """Tự động đăng ký thư mục hoặc tệp video vào whitelist an toàn của NovaCut."""
    if not path:
        return
    try:
        from routes.security import register_user_path
        register_user_path(path)
    except Exception as e:
        logger.warning(f"[routes/hongguo] register_user_path failed for '{path}': {e}")


def _get_manager():
    """Lấy thể hiện quản lý dịch vụ Hongguo."""
    from services.hongguo_service import get_service_manager
    return get_service_manager()


@hongguo_bp.before_request
def check_hongguo_permission():
    """
    (Bảo Vệ Bản Quyền Tầng Backend)
    Tự động chặn tất cả các request đến /api/hongguo/* nếu chưa kích hoạt bản quyền.
    Trả về mã lỗi HTTP 403 Forbidden theo đúng chuẩn của NovaCut.
    """
    if request.method == 'OPTIONS':
        return ('', 204)

    try:
        perm = license_manager.check_permission('hongguo_downloader')
        if isinstance(perm, (tuple, list)):
            allowed = perm[0]
            message = perm[1] if len(perm) > 1 else ""
            status = perm[2] if len(perm) > 2 else {}
        else:
            allowed = bool(perm)
            message = "Tính năng yêu cầu kích hoạt bản quyền." if not allowed else ""
            status = {}

        if not allowed:
            return jsonify({
                "success": False,
                "error": message,
                "license_error": True,
                "license_status": status
            }), 403
    except Exception as e:
        logger.error(f"[routes/hongguo] License check exception: {e}")
        return jsonify({
            "success": False,
            "error": f"Lỗi kiểm tra bản quyền: {str(e)}",
            "license_error": True,
            "license_status": {}
        }), 403


def require_hongguo_license(f):
    """Decorator dự phòng kiểm tra quyền tính năng (Defense-in-depth)."""
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        perm = license_manager.check_permission('hongguo_downloader')
        if isinstance(perm, (tuple, list)):
            allowed = perm[0]
            message = perm[1] if len(perm) > 1 else ""
            status = perm[2] if len(perm) > 2 else {}
        else:
            allowed = bool(perm)
            message = "Tính năng yêu cầu kích hoạt bản quyền." if not allowed else ""
            status = {}

        if not allowed:
            return jsonify({
                "success": False,
                "error": message,
                "license_error": True,
                "license_status": status
            }), 403
        return f(*args, **kwargs)
    return decorated_function


# =========================================================================
# 1. Quản lý Trạng thái & Vòng đời Dịch vụ Nền
# =========================================================================

@hongguo_bp.route('/status', methods=['GET'])
def get_status():
    """Lấy trạng thái chi tiết của công cụ, tiến trình Signer và Server."""
    mgr = _get_manager()
    status_data = mgr.get_status()
    out_dir = status_data.get('output_dir')
    if out_dir:
        _ensure_path_registered(out_dir)

    return jsonify({
        "success": True,
        "data": status_data
    })


@hongguo_bp.route('/start', methods=['POST'])
def start_services():
    """Kích hoạt dịch vụ Unidbg Signer và FastAPI Server."""
    mgr = _get_manager()
    success, msg = mgr.start_services()
    status_data = mgr.get_status()
    out_dir = status_data.get('output_dir')
    if out_dir:
        _ensure_path_registered(out_dir)

    if success:
        return jsonify({
            "success": True,
            "message": msg,
            "data": status_data
        })
    return jsonify({
        "success": False,
        "error": msg,
        "data": status_data
    }), 500


@hongguo_bp.route('/stop', methods=['POST'])
def stop_services():
    """Dừng triệt để toàn bộ tiến trình con của Hongguo."""
    mgr = _get_manager()
    success, msg = mgr.stop_services()
    status_data = mgr.get_status()

    if success:
        return jsonify({
            "success": True,
            "message": msg,
            "data": status_data
        })
    return jsonify({
        "success": False,
        "error": msg,
        "data": status_data
    }), 500


# =========================================================================
# 2. Phân giải & Trích xuất Dữ liệu Phim (Proxy Gateway)
# =========================================================================

@hongguo_bp.route('/resolve', methods=['POST'])
def resolve_drama():
    """Phân giải link hoặc ID phim Hồng Quả."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}
    raw_text = body.get('text')
    text = str(raw_text or '').strip()
    if not text or text.lower() == 'none':
        return jsonify({
            "success": False,
            "error": "Vui lòng nhập đường link chia sẻ hoặc ID phim Hồng Quả."
        }), 400

    mgr = _get_manager()
    stat = mgr.get_status()
    if not stat.get('server_running', False):
        started, start_msg = mgr.start_services()
        if not started:
            return jsonify({
                "success": False,
                "error": f"Không thể khởi động dịch vụ tải Hồng Quả: {start_msg}"
            }), 503

    status_code, resp_data = mgr.forward_request('POST', '/dl/resolve', json_data={'text': text})
    if status_code == 200 and isinstance(resp_data, dict):
        resolved = resp_data.get('resolved', [])
        return jsonify({
            "success": True,
            "resolved": resolved
        })

    err_msg = resp_data.get('detail', 'Không thể phân giải thông tin phim.') if isinstance(resp_data, dict) else str(resp_data)
    return jsonify({
        "success": False,
        "error": err_msg
    }), status_code if status_code >= 400 else 500


@hongguo_bp.route('/episodes', methods=['GET'])
def get_episodes():
    """Lấy danh sách tập phim theo series_id."""
    series_id = str(request.args.get('series_id', '')).strip()
    if not series_id:
        return jsonify({
            "success": False,
            "error": "Thiếu tham số series_id."
        }), 400

    mgr = _get_manager()
    stat = mgr.get_status()
    if not stat.get('server_running', False):
        started, start_msg = mgr.start_services()
        if not started:
            return jsonify({
                "success": False,
                "error": f"Không thể khởi động dịch vụ tải Hồng Quả: {start_msg}"
            }), 503

    status_code, resp_data = mgr.forward_request('GET', '/dl/episodes', params={'series_id': series_id})
    if status_code == 200 and isinstance(resp_data, dict):
        return jsonify({
            "success": True,
            **resp_data
        })

    err_msg = resp_data.get('detail', 'Không thể tải danh sách tập phim.') if isinstance(resp_data, dict) else str(resp_data)
    return jsonify({
        "success": False,
        "error": err_msg
    }), status_code if status_code >= 400 else 500


@hongguo_bp.route('/drama-detail', methods=['GET'])
def get_drama_detail():
    """Lấy thông tin chi tiết và tóm tắt bộ phim."""
    series_id = str(request.args.get('series_id', '')).strip()
    if not series_id:
        return jsonify({
            "success": False,
            "error": "Thiếu tham số series_id."
        }), 400

    mgr = _get_manager()
    stat = mgr.get_status()
    if not stat.get('server_running', False):
        started, start_msg = mgr.start_services()
        if not started:
            return jsonify({
                "success": False,
                "error": f"Không thể khởi động dịch vụ tải Hồng Quả: {start_msg}"
            }), 503

    status_code, resp_data = mgr.forward_request('GET', '/dl/drama-detail', params={'series_id': series_id})
    if status_code == 200 and isinstance(resp_data, dict):
        return jsonify({
            "success": True,
            "data": resp_data
        })

    err_msg = resp_data.get('detail', 'Không thể lấy thông tin chi tiết phim.') if isinstance(resp_data, dict) else str(resp_data)
    return jsonify({
        "success": False,
        "error": err_msg
    }), status_code if status_code >= 400 else 500


# =========================================================================
# 3. Quản lý Tác vụ Tải Phim & Tiến độ Real-time
# =========================================================================

@hongguo_bp.route('/submit', methods=['POST'])
def submit_download():
    """Gửi yêu cầu tải phim vào hàng đợi."""
    body = request.get_json(silent=True) or {}
    series_ids = body.get('series_ids', [])
    series_id = body.get('series_id')
    if not series_ids and not series_id:
        return jsonify({
            "success": False,
            "error": "Danh sách series_ids không được để trống."
        }), 400

    mgr = _get_manager()
    stat = mgr.get_status()
    out_dir = stat.get('output_dir')
    if out_dir:
        _ensure_path_registered(out_dir)

    if not stat.get('server_running', False):
        started, start_msg = mgr.start_services()
        if not started:
            return jsonify({
                "success": False,
                "error": f"Không thể khởi động dịch vụ tải Hồng Quả: {start_msg}"
            }), 503

    status_code, resp_data = mgr.forward_request('POST', '/dl/submit', json_data=body)
    if status_code == 200:
        return jsonify({
            "success": True,
            "message": "Đã thêm tác vụ tải vào hàng đợi thành công.",
            "data": resp_data
        })

    err_msg = resp_data.get('detail', 'Không thể gửi tác vụ tải phim.') if isinstance(resp_data, dict) else str(resp_data)
    return jsonify({
        "success": False,
        "error": err_msg
    }), status_code if status_code >= 400 else 500


@hongguo_bp.route('/tasks', methods=['GET'])
def get_tasks():
    """Lấy trạng thái và tiến độ tải phim theo thời gian thực."""
    mgr = _get_manager()
    stat = mgr.get_status()
    if not stat.get('server_running', False):
        return jsonify({
            "success": True,
            "running": False,
            "series": {},
            "log": []
        })

    status_code, resp_data = mgr.forward_request('GET', '/dl/status')
    if status_code == 200 and isinstance(resp_data, dict):
        return jsonify({
            "success": True,
            **resp_data
        })

    return jsonify({
        "success": True,
        "running": False,
        "series": {},
        "log": [],
        "warning": str(resp_data)
    })


@hongguo_bp.route('/cancel', methods=['POST'])
def cancel_download():
    """Hủy tiến trình tải đang diễn ra."""
    mgr = _get_manager()
    stat = mgr.get_status()
    if not stat.get('server_running', False):
        return jsonify({
            "success": True,
            "message": "Dịch vụ hiện không chạy."
        })

    status_code, resp_data = mgr.forward_request('POST', '/dl/cancel')
    if status_code == 200:
        return jsonify({
            "success": True,
            "message": "Đã gửi yêu cầu hủy tác vụ tải.",
            "data": resp_data
        })

    err_msg = resp_data.get('detail', 'Không thể hủy tác vụ tải.') if isinstance(resp_data, dict) else str(resp_data)
    return jsonify({
        "success": False,
        "error": err_msg
    }), status_code if status_code >= 400 else 500


# =========================================================================
# 4. Quản lý Thư viện Phim Đã Tải & Bảo mật Tệp
# =========================================================================

def _extract_candidate_roots(mgr, out_dir=None):
    """Trích xuất danh sách candidate roots hợp lệ, chống mock object failure."""
    candidate_roots = []
    raw_fn = getattr(mgr, 'get_candidate_output_roots', None)
    if callable(raw_fn):
        try:
            res = raw_fn()
            if isinstance(res, (list, tuple, set)):
                candidate_roots = [os.path.normpath(str(r).strip()) for r in res if isinstance(r, (str, bytes)) and str(r).strip()]
        except Exception:
            pass

    if out_dir and isinstance(out_dir, str) and out_dir.strip():
        norm_out = os.path.normpath(out_dir.strip())
        if norm_out not in candidate_roots:
            candidate_roots.insert(0, norm_out)
    return candidate_roots


@hongguo_bp.route('/library', methods=['GET'])
def get_library():
    """Danh sách các bộ phim đã tải trong thư viện."""
    mgr = _get_manager()
    stat = mgr.get_status()
    out_dir = stat.get('output_dir')
    if not out_dir and hasattr(mgr, 'resolve_output_dir'):
        try:
            res_dir = mgr.resolve_output_dir()
            if isinstance(res_dir, str):
                out_dir = res_dir
        except Exception:
            pass

    candidate_roots = _extract_candidate_roots(mgr, out_dir)
    for root in candidate_roots:
        _ensure_path_registered(root)

    items = []
    # 1. Ưu tiên lấy từ server nếu đang chạy
    if stat.get('server_running', False):
        status_code, resp_data = mgr.forward_request('GET', '/dl/library')
        if status_code == 200 and isinstance(resp_data, dict):
            raw_items = resp_data.get('items', [])
            for it in raw_items:
                name = it.get('name') or it.get('title') or ''
                matched_path = None
                for root in candidate_roots:
                    cand = os.path.join(root, name)
                    if os.path.isdir(cand):
                        matched_path = os.path.abspath(cand)
                        break
                if not matched_path:
                    for root in candidate_roots:
                        if not os.path.isdir(root):
                            continue
                        try:
                            for entry in os.scandir(root):
                                if entry.is_dir() and entry.name.lower() == name.lower():
                                    matched_path = os.path.abspath(entry.path)
                                    break
                        except Exception:
                            pass
                        if matched_path:
                            break

                if not matched_path and out_dir:
                    matched_path = os.path.abspath(os.path.join(out_dir, name))

                it['path'] = matched_path
                if matched_path:
                    _ensure_path_registered(matched_path)

                if 'episodes_count' not in it or it['episodes_count'] is None:
                    it['episodes_count'] = it.get('local') if it.get('local') is not None else (it.get('total') or 0)

                items.append(it)

    # 2. Quét cục bộ dự phòng nếu server chưa bật hoặc trả về rỗng
    if not items and candidate_roots:
        seen_dirs = set()
        for root in candidate_roots:
            if not os.path.exists(root) or not os.path.isdir(root):
                continue
            try:
                for entry in os.scandir(root):
                    if entry.is_dir():
                        dir_path = os.path.abspath(entry.path)
                        norm_key = os.path.normcase(dir_path)
                        if norm_key in seen_dirs:
                            continue
                        seen_dirs.add(norm_key)

                        _ensure_path_registered(dir_path)
                        meta_path = os.path.join(dir_path, '.series.json')
                        cover = ""
                        title = entry.name
                        if os.path.exists(meta_path):
                            try:
                                with open(meta_path, 'r', encoding='utf-8') as mf:
                                    mdata = json.load(mf)
                                    cover = mdata.get('cover', '')
                                    title = mdata.get('title') or mdata.get('title_vi') or mdata.get('title_cn') or entry.name
                            except Exception:
                                pass

                        # Đếm các file video (.mp4, .ts, .mkv)
                        video_count = 0
                        try:
                            video_count = len([
                                f for f in os.listdir(dir_path)
                                if f.lower().endswith(('.mp4', '.ts', '.mkv', '.m4v'))
                            ])
                        except Exception:
                            pass

                        if video_count > 0:
                            items.append({
                                "name": entry.name,
                                "title": title,
                                "path": dir_path,
                                "episodes_count": video_count,
                                "cover": cover
                            })
            except Exception as e:
                logger.warning(f"[routes/hongguo] Local scan error on root {root}: {e}")

    # Đăng ký quyền bảo mật cho toàn bộ đường dẫn các phim tìm thấy
    from routes.security import _is_within, _real
    for it in items:
        p = it.get('path')
        if p:
            real_p = _real(p)
            for root in candidate_roots:
                if _is_within(_real(root), real_p) or real_p == _real(root):
                    _ensure_path_registered(p)
                    break

    return jsonify({
        "success": True,
        "items": items,
        "output_dir": out_dir
    })


@hongguo_bp.route('/library/episodes', methods=['GET'])
def get_library_episodes():
    """Lấy danh sách các tệp tập phim trong một bộ phim."""
    folder_name = str(request.args.get('name', '')).strip()
    if not folder_name:
        return jsonify({
            "success": False,
            "error": "Thiếu tham số name (tên thư mục phim)."
        }), 400

    # 1. Multi-pass URL unquoting để ngăn chặn triệt để kỹ thuật lách bộ lọc mã hóa đa cấp (như %252e%252e%252f)
    decoded_name = folder_name
    for _ in range(3):
        unquoted = urllib.parse.unquote(decoded_name)
        if unquoted == decoded_name:
            break
        decoded_name = unquoted
    decoded_name = decoded_name.strip()

    if not decoded_name:
        return jsonify({
            "success": False,
            "error": "Tên thư mục phim không hợp lệ."
        }), 400

    # 2. Chặn các tên thiết bị DOS bảo lưu trên hệ điều hành Windows
    base_stem = os.path.splitext(decoded_name)[0].lower().strip()
    first_stem = decoded_name.split('.')[0].lower().strip()
    if base_stem in WINDOWS_RESERVED_NAMES or first_stem in WINDOWS_RESERVED_NAMES:
        return jsonify({
            "success": False,
            "error": "Tên thư mục phim không hợp lệ."
        }), 400

    # 3. Chặn đứng các ký tự phân cách đường dẫn, ký tự đặc biệt cấm và token traversal
    if (any(c in folder_name for c in FORBIDDEN_NAME_CHARS)
            or any(c in decoded_name for c in FORBIDDEN_NAME_CHARS)
            or '..' in folder_name
            or '..' in decoded_name
            or folder_name in ('.', '..')
            or decoded_name in ('.', '..')):
        return jsonify({
            "success": False,
            "error": "Tên thư mục phim không hợp lệ."
        }), 400

    folder_name = decoded_name

    mgr = _get_manager()
    stat = mgr.get_status()
    out_dir = stat.get('output_dir')
    if not out_dir and hasattr(mgr, 'resolve_output_dir'):
        try:
            res_dir = mgr.resolve_output_dir()
            if isinstance(res_dir, str):
                out_dir = res_dir
        except Exception:
            pass

    candidate_roots = _extract_candidate_roots(mgr, out_dir)
    for root in candidate_roots:
        _ensure_path_registered(root)

    from routes.security import safe_join, _real, _is_within

    # Tìm thư mục thực tế của bộ phim trong các candidate_roots
    target_dir = None
    target_root_found = None

    for root in candidate_roots:
        if not os.path.isdir(root):
            continue
        try:
            candidate_target = safe_join(root, folder_name)
            if os.path.isdir(candidate_target):
                target_dir = candidate_target
                target_root_found = root
                break
        except (ValueError, OSError):
            pass

    # Nếu chưa tìm thấy trực tiếp bằng tên thư mục, quét tra cứu qua .series.json
    if not target_dir:
        for root in candidate_roots:
            if not os.path.isdir(root):
                continue
            try:
                for entry in os.scandir(root):
                    if entry.is_dir():
                        if entry.name.lower() == folder_name.lower():
                            target_dir = entry.path
                            target_root_found = root
                            break
                        meta_file = os.path.join(entry.path, '.series.json')
                        if os.path.isfile(meta_file):
                            try:
                                with open(meta_file, 'r', encoding='utf-8') as mf:
                                    mdata = json.load(mf)
                                    m_titles = [
                                        str(mdata.get('title', '')).strip().lower(),
                                        str(mdata.get('title_vi', '')).strip().lower(),
                                        str(mdata.get('title_cn', '')).strip().lower(),
                                        str(mdata.get('series_id', '')).strip().lower()
                                    ]
                                    if folder_name.lower() in m_titles:
                                        target_dir = entry.path
                                        target_root_found = root
                                        break
                            except Exception:
                                pass
                if target_dir:
                    break
            except Exception:
                pass

    if not target_dir:
        # Fallback tạo đường dẫn với out_dir nếu out_dir tồn tại
        if not out_dir:
            return jsonify({
                "success": False,
                "error": "Chưa xác định được thư mục tải về."
            }), 400
        try:
            target_dir = safe_join(out_dir, folder_name)
            target_root_found = out_dir
        except (ValueError, OSError):
            return jsonify({
                "success": False,
                "error": "Tên thư mục phim không hợp lệ hoặc nằm ngoài phạm vi cho phép."
            }), 400

    real_root = _real(target_root_found)
    real_target = _real(target_dir)

    # Đảm bảo target_dir là thư mục con hợp lệ của candidate root
    if not (_is_within(real_root, real_target) and real_target != real_root):
        return jsonify({
            "success": False,
            "error": "Thư mục phim phải là thư mục con trực tiếp của thư mục tải về."
        }), 400

    _ensure_path_registered(real_target)

    episodes = []
    # 4. Thử qua server
    if stat.get('server_running', False):
        status_code, resp_data = mgr.forward_request('GET', '/dl/library/episodes', params={'name': folder_name})
        if status_code == 200 and isinstance(resp_data, dict):
            episodes = resp_data.get('episodes', [])

    # 5. Quét cục bộ dự phòng
    if not episodes and os.path.isdir(real_target):
        try:
            for fname in sorted(os.listdir(real_target)):
                if fname.lower().endswith(('.mp4', '.ts', '.mkv', '.m4v')):
                    fpath = os.path.join(real_target, fname)
                    fsize = os.path.getsize(fpath)
                    m = re.search(r'(\d+)', fname)
                    ep_num = int(m.group(1)) if m else 0
                    episodes.append({
                        "name": fname,
                        "path": fpath,
                        "size": fsize,
                        "ep_num": ep_num
                    })
        except Exception as e:
            logger.warning(f"[routes/hongguo] Local scan episodes error: {e}")

    # 6. Đăng ký quyền bảo mật cho từng tệp video
    for ep in episodes:
        p = ep.get('path')
        if p and os.path.isabs(p) and _is_within(real_target, _real(p)):
            _ensure_path_registered(p)

    return jsonify({
        "success": True,
        "episodes": episodes
    })


@hongguo_bp.route('/open-folder', methods=['POST'])
def open_folder():
    """Mở thư mục tải về hoặc thư mục phim trong File Explorer của hệ điều hành một cách an toàn."""
    body = request.get_json(silent=True) or {}
    if not isinstance(body, dict):
        body = {}

    mgr = _get_manager()
    stat = mgr.get_status()
    out_dir = stat.get('output_dir')
    if not out_dir and hasattr(mgr, 'resolve_output_dir'):
        try:
            res_dir = mgr.resolve_output_dir()
            if isinstance(res_dir, str):
                out_dir = res_dir
        except Exception:
            pass

    candidate_roots = _extract_candidate_roots(mgr, out_dir)
    for root in candidate_roots:
        _ensure_path_registered(root)

    raw_folder = body.get('folder')
    if raw_folder is not None:
        raw_folder = str(raw_folder).strip()
        if not raw_folder or raw_folder.lower() == 'none':
            raw_folder = None

    from routes.security import safe_join, _real, _is_within, is_path_allowed

    target_folder = None

    try:
        if not raw_folder:
            # Người dùng bấm mở thư mục gốc: Mở out_dir hiện tại
            if not out_dir:
                return jsonify({
                    "success": False,
                    "error": "Chưa xác định được thư mục lưu trữ."
                }), 400
            os.makedirs(out_dir, exist_ok=True)
            target_folder = _real(out_dir)
            _ensure_path_registered(target_folder)
        else:
            # Multi-pass URL unquoting để ngăn chặn traversal và mã hóa lách luật
            decoded_folder = raw_folder
            for _ in range(3):
                unquoted = urllib.parse.unquote(decoded_folder)
                if unquoted == decoded_folder:
                    break
                decoded_folder = unquoted
            decoded_folder = decoded_folder.strip()

            if not decoded_folder:
                return jsonify({
                    "success": False,
                    "error": "Đường dẫn thư mục không hợp lệ."
                }), 400

            # 1. Kiểm tra ký tự bất hợp pháp trên đường dẫn Windows
            if any(c in raw_folder for c in ('\0', '*', '?', '"', '<', '>', '|')) or any(c in decoded_folder for c in ('\0', '*', '?', '"', '<', '>', '|')):
                return jsonify({
                    "success": False,
                    "error": "Đường dẫn thư mục chứa ký tự không hợp lệ."
                }), 400

            # 2. Chặn các tên thiết bị DOS bảo lưu trên Windows
            leaf_name = os.path.basename(decoded_folder)
            leaf_base = os.path.splitext(leaf_name)[0].lower().strip()
            leaf_first = leaf_name.split('.')[0].lower().strip()
            if leaf_base in WINDOWS_RESERVED_NAMES or leaf_first in WINDOWS_RESERVED_NAMES:
                return jsonify({
                    "success": False,
                    "error": "Đường dẫn thư mục không hợp lệ (tên thiết bị hệ thống cấm)."
                }), 400

            if os.path.isabs(decoded_folder):
                # Đường dẫn tuyệt đối: Kiểm tra tính hợp lệ qua candidate roots hoặc whitelist NovaCut
                real_target = _real(decoded_folder)
                is_in_candidates = any(
                    (_is_within(_real(root), real_target) or real_target == _real(root))
                    for root in candidate_roots
                )
                is_existing_allowed = is_path_allowed(real_target, must_exist=True)

                if not (is_in_candidates or is_existing_allowed):
                    return jsonify({
                        "success": False,
                        "error": "Thư mục không hợp lệ hoặc nằm ngoài phạm vi cho phép."
                    }), 400

                target_folder = real_target
                _ensure_path_registered(target_folder)
            else:
                # Đường dẫn tương đối hoặc tên phim: Tìm kiếm trong candidate_roots
                found_target = None
                for root in candidate_roots:
                    if not os.path.isdir(root):
                        continue
                    try:
                        c_target = safe_join(root, decoded_folder)
                        if os.path.exists(c_target):
                            found_target = c_target
                            break
                    except (ValueError, OSError):
                        pass

                # Nếu chưa tìm thấy, quét thư mục con theo tên phim hoặc metadata
                if not found_target:
                    for root in candidate_roots:
                        if not os.path.isdir(root):
                            continue
                        try:
                            for entry in os.scandir(root):
                                if entry.is_dir():
                                    if entry.name.lower() == decoded_folder.lower():
                                        found_target = entry.path
                                        break
                                    meta_file = os.path.join(entry.path, '.series.json')
                                    if os.path.isfile(meta_file):
                                        try:
                                            with open(meta_file, 'r', encoding='utf-8') as mf:
                                                mdata = json.load(mf)
                                                m_titles = [
                                                    str(mdata.get('title', '')).strip().lower(),
                                                    str(mdata.get('title_vi', '')).strip().lower(),
                                                    str(mdata.get('title_cn', '')).strip().lower(),
                                                    str(mdata.get('series_id', '')).strip().lower()
                                                ]
                                                if decoded_folder.lower() in m_titles:
                                                    found_target = entry.path
                                                    break
                                        except Exception:
                                            pass
                            if found_target:
                                break
                        except Exception:
                            pass

                if not found_target:
                    # Fallback vào out_dir
                    if not out_dir:
                        return jsonify({
                            "success": False,
                            "error": "Chưa xác định được thư mục lưu trữ gốc."
                        }), 400
                    found_target = safe_join(out_dir, decoded_folder)

                target_folder = _real(found_target)
                _ensure_path_registered(target_folder)

        # Đảm bảo target_folder hoặc thư mục cha của nó tồn tại
        if not os.path.exists(target_folder):
            ext = os.path.splitext(target_folder)[1]
            if not ext:
                os.makedirs(target_folder, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_folder), exist_ok=True)

        # Mở thư mục hoặc tệp bằng trình quản lý tệp tin hệ điều hành
        norm_target = os.path.normpath(target_folder)
        if os.name == 'nt':
            if os.path.isfile(norm_target):
                subprocess.Popen(
                    f'explorer /select,"{norm_target}"',
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            else:
                try:
                    os.startfile(norm_target)
                except Exception:
                    subprocess.Popen(
                        ['explorer.exe', norm_target],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
        elif sys.platform == 'darwin':
            args = ['open', '-R', norm_target] if os.path.isfile(norm_target) else ['open', norm_target]
            subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            p_to_open = os.path.dirname(norm_target) if os.path.isfile(norm_target) else norm_target
            subprocess.Popen(['xdg-open', p_to_open], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        return jsonify({
            "success": True,
            "message": f"Đã mở {target_folder}",
            "path": target_folder
        })
    except (ValueError, OSError) as e:
        logger.warning(f"[routes/hongguo] open_folder validation/os error: {e}")
        return jsonify({
            "success": False,
            "error": f"Lỗi truy cập thư mục: {str(e)}"
        }), 400
    except Exception as e:
        logger.error(f"[routes/hongguo] Failed to open folder: {e}")
        return jsonify({
            "success": False,
            "error": f"Không thể mở thư mục: {str(e)}"
        }), 500
