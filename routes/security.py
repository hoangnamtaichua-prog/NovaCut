import os
import threading
import json
import tempfile

from routes.state import ROOT_DIR, USER_DATA_DIR


_selection_lock = threading.RLock()
_selected_roots = set()
_BUILTIN_WRITABLE_DIRS = (
    'output', 'projects', 'temp', 'uploads', 'downloads', 'tiktok_output',
    'clips', 'scratch', 'voices', 'backgroundmusic', 'movies', 'movies_retired'
)


def _real(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def register_user_path(path):
    """Cho phép thư mục mà người dùng vừa chọn qua native file dialog."""
    if not path:
        return
    resolved = _real(path)
    root = resolved if os.path.isdir(resolved) else os.path.dirname(resolved)
    with _selection_lock:
        _selected_roots.add(root)


def _is_within(root, candidate):
    try:
        p_drive, _ = os.path.splitdrive(root)
        c_drive, _ = os.path.splitdrive(candidate)
        if p_drive.lower() != c_drive.lower():
            return False
        return os.path.commonpath((root, candidate)) == root
    except (OSError, ValueError, TypeError):
        return False


def is_path_allowed(path, *, must_exist=False, extensions=None):
    if not path:
        return False
    try:
        resolved = _real(path)
        if must_exist and not os.path.exists(resolved):
            return False
        if extensions and os.path.splitext(resolved)[1].lower() not in {e.lower() for e in extensions}:
            return False
        roots = [_real(USER_DATA_DIR)]
        roots.extend(_real(os.path.join(ROOT_DIR, name)) for name in _BUILTIN_WRITABLE_DIRS)
        roots.extend((_real(os.path.join(ROOT_DIR, 'web', 'samples')),))
        with _selection_lock:
            roots.extend(_selected_roots)
        return any(_is_within(root, resolved) for root in roots)
    except (OSError, ValueError, TypeError):
        return False


def safe_join(root, name, *, extensions=None):
    root_real = _real(root)
    candidate = _real(os.path.join(root_real, str(name or '')))
    if not _is_within(root_real, candidate):
        raise ValueError('Đường dẫn nằm ngoài thư mục được phép.')
    if extensions and os.path.splitext(candidate)[1].lower() not in {e.lower() for e in extensions}:
        raise ValueError('Định dạng file không được phép.')
    return candidate


def parse_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ('true', '1', 'yes', 'on'):
            return True
        if lowered in ('false', '0', 'no', 'off', ''):
            return False
    raise ValueError('Giá trị boolean không hợp lệ.')


def atomic_write_json(path, value):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.novacut_', suffix='.tmp', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise
