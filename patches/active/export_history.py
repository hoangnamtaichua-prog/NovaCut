import os
import sys
import sqlite3
import threading
import uuid
import json
import logging
from datetime import datetime, timezone
import platformdirs

logger = logging.getLogger(__name__)

SUPPORTED_VIDEO_EXTENSIONS = {
    '.mp4', '.mkv', '.avi', '.mov', '.flv', '.webm', '.m4v', '.wmv', '.ts'
}

VALID_SOURCE_KINDS = {
    'editor', 'batch_editor', 'review', 'narration', 'batch_queue', 'comic_review', 'import'
}


def get_default_db_path() -> str:
    """Trả về đường dẫn SQLite mặc định trong USER_DATA_DIR (%APPDATA%/NovaCut)."""
    data_dir = platformdirs.user_data_dir('NovaCut', 'NovaCut', roaming=True)
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, 'export_history.sqlite3')


def normalize_video_path(path: str) -> str:
    """Chuẩn hóa đường dẫn video: lowercase trên Windows, canonical realpath."""
    if not path:
        return ""
    cleaned = str(path).strip().strip('"\'')
    try:
        real = os.path.realpath(os.path.abspath(cleaned))
        return os.path.normcase(real)
    except Exception:
        return os.path.normcase(os.path.normpath(cleaned))


class ExportHistoryService:
    """
    Service quản lý SQLite lưu trữ lịch sử xuất video.
    Thread-safe, transaction an toàn và hỗ trợ migration tự động.
    """

    def __init__(self, db_path=None):
        self.db_path = db_path or get_default_db_path()
        self._lock = threading.RLock()
        self._active_scans = {}
        self._scans_lock = threading.Lock()
        self._init_db()

    def _get_connection(self):
        """Tạo connection SQLite ngắn hạn với timeout và WAL mode."""
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except Exception:
            pass
        return conn

    def _init_db(self):
        """Khởi tạo cấu trúc bảng và quản lý migration qua PRAGMA user_version."""
        db_dir = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(db_dir, exist_ok=True)

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("PRAGMA user_version")
                version = cur.fetchone()[0]

                if version == 0:
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS exports (
                            id TEXT PRIMARY KEY,
                            event_key TEXT NOT NULL UNIQUE,
                            output_path TEXT NOT NULL,
                            normalized_path TEXT NOT NULL,
                            filename TEXT NOT NULL,
                            source_kind TEXT NOT NULL,
                            origin TEXT NOT NULL CHECK(origin IN ('export', 'import')),
                            completed_at TEXT,
                            recorded_at TEXT NOT NULL,
                            imported_at TEXT,
                            file_mtime_ns INTEGER,
                            file_size_bytes INTEGER NOT NULL,
                            job_id TEXT,
                            project_name TEXT,
                            params_json TEXT
                        )
                    """)
                    cur.execute("CREATE INDEX IF NOT EXISTS exports_time ON exports(recorded_at DESC, id DESC)")
                    cur.execute("CREATE INDEX IF NOT EXISTS exports_source ON exports(source_kind, recorded_at DESC)")
                    cur.execute("CREATE INDEX IF NOT EXISTS exports_path ON exports(normalized_path)")
                    cur.execute("CREATE INDEX IF NOT EXISTS exports_event ON exports(event_key)")
                    cur.execute("PRAGMA user_version = 1")
                    conn.commit()

    # =========================================================================
    # RECORD EXPORT
    # =========================================================================
    def record_export(self, output_path: str, source_kind: str = None, export_run_id: str = None,
                      completed_at: str = None, job_id: str = None, project_name: str = None,
                      source_tool: str = None, params: dict = None, event_key: str = None) -> str:
        """
        Ghi nhận một video đã xuất thành công vào lịch sử.
        - Kiểm tra file tồn tại trên đĩa
        - Chống trùng lặp bằng unique event_key
        - Trả về record_id (string)
        - Nếu gặp lỗi DB, không raise exception làm hỏng luồng render của user
        """
        if not output_path:
            return None

        norm_path = normalize_video_path(output_path)
        if not norm_path or not os.path.isfile(norm_path):
            logger.warning(f"[ExportHistory] Bỏ qua ghi nhận: file không tồn tại trên đĩa ({output_path})")
            return None

        try:
            stat = os.stat(norm_path)
            file_size_bytes = stat.st_size
            file_mtime_ns = getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1e9))
        except Exception as e:
            logger.warning(f"[ExportHistory] Không thể đọc stat file {norm_path}: {e}")
            return None

        filename = os.path.basename(os.path.normpath(output_path))
        tool = source_kind or source_tool or 'editor'
        source = tool if tool in VALID_SOURCE_KINDS else 'editor'
        
        rec_id = str(uuid.uuid4())
        run_id = str(export_run_id).strip() if export_run_id else rec_id
        final_event_key = event_key or f"{run_id}:{norm_path}"
        
        now_utc = datetime.now(timezone.utc).isoformat()
        final_completed_at = completed_at or now_utc

        params_str = None
        if params is not None:
            try:
                params_str = json.dumps(params, ensure_ascii=False)
            except Exception:
                params_str = str(params)

        with self._lock:
            try:
                with self._get_connection() as conn:
                    cur = conn.cursor()
                    # Kiểm tra xem event_key đã tồn tại chưa (Idempotency)
                    cur.execute("SELECT id FROM exports WHERE event_key = ?", (final_event_key,))
                    existing = cur.fetchone()
                    if existing:
                        return existing['id']

                    cur.execute("""
                        INSERT INTO exports (
                            id, event_key, output_path, normalized_path, filename,
                            source_kind, origin, completed_at, recorded_at, imported_at,
                            file_mtime_ns, file_size_bytes, job_id, project_name, params_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rec_id,
                        final_event_key,
                        os.path.normpath(output_path),
                        norm_path,
                        filename,
                        source,
                        'export',
                        final_completed_at,
                        now_utc,
                        None,
                        file_mtime_ns,
                        file_size_bytes,
                        str(job_id) if job_id else None,
                        str(project_name) if project_name else None,
                        params_str
                    ))
                    conn.commit()
                    return rec_id
            except sqlite3.IntegrityError:
                # Đụng độ UNIQUE(event_key) do race-condition
                try:
                    with self._get_connection() as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT id FROM exports WHERE event_key = ?", (final_event_key,))
                        row = cur.fetchone()
                        return row['id'] if row else None
                except Exception:
                    return None
            except Exception as e:
                logger.error(f"[ExportHistory] Lỗi ghi nhận lịch sử vào DB: {e}", exc_info=True)
                return None

    # =========================================================================
    # QUERY & SEARCH
    # =========================================================================
    def query_exports(self, search: str = None, source_tool: str = None, status: str = None,
                      from_date: str = None, to_date: str = None, page: int = 1, limit: int = 50,
                      q: str = None, source: str = None, page_size: int = None):
        """
        Truy vấn danh sách lịch sử xuất video có phân trang và bộ lọc.
        - Tìm kiếm tên file hoặc đường dẫn an toàn (parameterized, escape wildcard)
        - Hỗ trợ lọc theo công cụ (source_kind / source_tool)
        - Lọc theo ngày hoàn thành / ngày thêm
        - Lọc theo trạng thái file (available, missing, unreachable)
        - Trả về {items, total, page, limit, page_size, total_pages}
        """
        search_query = search if search is not None else q
        tool_query = source_tool if source_tool is not None else source
        limit_val = limit if limit is not None else (page_size or 50)
        
        page = max(1, int(page or 1))
        page_size = max(1, min(100, int(limit_val or 50)))

        where_clauses = []
        params = []

        # 1. Tìm kiếm chuỗi (filename hoặc output_path)
        if search_query and str(search_query).strip():
            query_str = str(search_query).strip()
            escaped_q = query_str.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            like_pattern = f"%{escaped_q}%"
            where_clauses.append("(filename LIKE ? ESCAPE '\\' OR output_path LIKE ? ESCAPE '\\')")
            params.extend([like_pattern, like_pattern])

        # 2. Lọc theo nguồn công cụ (source_kind)
        if tool_query and str(tool_query).strip() and str(tool_query).strip() != 'all':
            s_val = str(tool_query).strip()
            if s_val == 'imported' or s_val == 'import':
                where_clauses.append("origin = 'import'")
            elif s_val in VALID_SOURCE_KINDS:
                where_clauses.append("source_kind = ?")
                params.append(s_val)

        # 3. Lọc khoảng ngày
        if from_date and str(from_date).strip():
            f_val = str(from_date).strip()
            if len(f_val) == 10:
                f_val = f"{f_val}T00:00:00"
            where_clauses.append("COALESCE(completed_at, recorded_at) >= ?")
            params.append(f_val)

        if to_date and str(to_date).strip():
            t_val = str(to_date).strip()
            if len(t_val) == 10:
                t_val = f"{t_val}T23:59:59.999999"
            where_clauses.append("COALESCE(completed_at, recorded_at) <= ?")
            params.append(t_val)

        where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()

                # Nếu có lọc theo status, ta cần duyệt kiểm tra status của các file
                if status and status.strip() in ('available', 'missing', 'unreachable'):
                    desired_status = status.strip()
                    select_all_sql = f"SELECT * FROM exports {where_sql} ORDER BY recorded_at DESC, id DESC"
                    cur.execute(select_all_sql, params)
                    all_rows = cur.fetchall()

                    filtered_items = []
                    for r in all_rows:
                        item = self._format_export_row(r)
                        if item['file_status'] == desired_status:
                            filtered_items.append(item)

                    total = len(filtered_items)
                    offset = (page - 1) * page_size
                    page_items = filtered_items[offset:offset + page_size]
                    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1

                    return {
                        'items': page_items,
                        'total': total,
                        'page': page,
                        'limit': page_size,
                        'page_size': page_size,
                        'total_pages': total_pages
                    }
                else:
                    count_sql = f"SELECT COUNT(*) FROM exports {where_sql}"
                    cur.execute(count_sql, params)
                    total = cur.fetchone()[0]

                    offset = (page - 1) * page_size
                    select_sql = f"""
                        SELECT * FROM exports 
                        {where_sql}
                        ORDER BY recorded_at DESC, id DESC
                        LIMIT ? OFFSET ?
                    """
                    items_params = list(params) + [page_size, offset]
                    cur.execute(select_sql, items_params)
                    rows = cur.fetchall()

                    items = [self._format_export_row(r) for r in rows]
                    total_pages = max(1, (total + page_size - 1) // page_size) if total > 0 else 1

                    return {
                        'items': items,
                        'total': total,
                        'page': page,
                        'limit': page_size,
                        'page_size': page_size,
                        'total_pages': total_pages
                    }

    def _format_export_row(self, row) -> dict:
        """Định dạng bản ghi SQLite thành dictionary chuẩn."""
        item = dict(row)
        item['source_tool'] = item.get('source_kind', 'editor')
        item['file_status'] = self.check_file_status(item.get('normalized_path'))
        
        raw_params = item.get('params_json')
        if raw_params:
            try:
                item['params_json'] = json.loads(raw_params)
            except Exception:
                item['params_json'] = raw_params
        else:
            item['params_json'] = {}
        return item

    def get_export_by_id(self, export_id: str):
        """Lấy thông tin 1 bản ghi xuất theo ID."""
        if not export_id:
            return None
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT * FROM exports WHERE id = ?", (str(export_id),))
                row = cur.fetchone()
                if row:
                    return self._format_export_row(row)
                return None

    def delete_export(self, export_id: str):
        """
        Xóa bản ghi khỏi cơ sở dữ liệu lịch sử.
        TUYỆT ĐỐI KHÔNG xóa tệp video thật trên đĩa.
        """
        if not export_id:
            return False
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM exports WHERE id = ?", (str(export_id),))
                conn.commit()
                return cur.rowcount > 0

    def clear_all_exports(self) -> int:
        """
        Xóa TOÀN BỘ bản ghi lịch sử khỏi cơ sở dữ liệu.
        TUYỆT ĐỐI KHÔNG xóa tệp video thật trên đĩa.
        Trả về số dòng đã xóa.
        """
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM exports")
                conn.commit()
                return cur.rowcount


    def check_file_status(self, path: str) -> str:
        """
        Kiểm tra nhanh tình trạng tệp:
        - 'available': Tệp tồn tại và có thể truy cập
        - 'missing': Tệp không tồn tại tại đường dẫn đã lưu nhưng thư mục cha còn
        - 'unreachable': Không truy cập được ổ đĩa / thư mục cha (ổ rời, ổ mạng ngắt kết nối)
        """
        if not path:
            return 'missing'
        try:
            norm = normalize_video_path(path)
            if os.path.isfile(norm):
                return 'available'
            parent_dir = os.path.dirname(norm)
            if parent_dir and os.path.isdir(parent_dir):
                return 'missing'
            return 'unreachable'
        except Exception:
            return 'unreachable'

    # =========================================================================
    # IMPORT EXISTING VIDEOS (SCAN / PREVIEW / COMMIT)
    # =========================================================================
    def start_import_scan(self, folder_path, include_subfolders: bool = False, recursive: bool = None) -> str:
        """
        Bắt đầu phiên quét thư mục chứa video để nhập vào lịch sử.
        - folder_path có thể là string hoặc list of strings
        - include_subfolders: có quét thư mục con không
        - Trả về scan_id
        """
        if isinstance(folder_path, str):
            folders_input = [folder_path]
        elif isinstance(folder_path, (list, tuple, set)):
            folders_input = list(folder_path)
        else:
            folders_input = []

        valid_folders = []
        for fp in folders_input:
            if fp and os.path.isdir(fp):
                valid_folders.append(os.path.normpath(fp))

        if not valid_folders:
            raise ValueError("Thư mục không tồn tại hoặc không phải là thư mục hợp lệ.")

        is_recursive = include_subfolders if recursive is None else recursive
        scan_id = str(uuid.uuid4())

        scan_info = {
            'scan_id': scan_id,
            'folders': valid_folders,
            'recursive': bool(is_recursive),
            'status': 'running',
            'scanned_count': 0,
            'found_count': 0,
            'skipped_count': 0,
            'candidates': [],
            'error': None
        }

        with self._scans_lock:
            self._active_scans[scan_id] = scan_info

        # Khởi chạy quét ngầm trên thread riêng
        threading.Thread(
            target=self._run_import_scan_worker,
            args=(scan_id, valid_folders, bool(is_recursive)),
            daemon=True
        ).start()

        return scan_id

    def _run_import_scan_worker(self, scan_id: str, folders: list, recursive: bool):
        """Worker thực hiện quét thư mục và tìm các video candidate."""
        with self._scans_lock:
            scan = self._active_scans.get(scan_id)
            if not scan:
                return

        candidates = []
        skipped_count = 0
        scanned_count = 0

        # Lấy danh sách normalized_path đã có trong SQLite để so khớp chống trùng
        existing_paths = set()
        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT normalized_path FROM exports")
                for row in cur.fetchall():
                    existing_paths.add(row['normalized_path'])

        try:
            for root_folder in folders:
                if scan.get('status') == 'cancelled':
                    break

                if recursive:
                    walker = os.walk(root_folder)
                else:
                    try:
                        walker = [(root_folder, [], os.listdir(root_folder))]
                    except Exception as e:
                        logger.warning(f"[ExportHistory] Không thể mở thư mục {root_folder}: {e}")
                        continue

                for dirpath, _, filenames in walker:
                    if scan.get('status') == 'cancelled':
                        break

                    for fname in filenames:
                        if scan.get('status') == 'cancelled':
                            break

                        scanned_count += 1
                        ext = os.path.splitext(fname)[1].lower()
                        if ext not in SUPPORTED_VIDEO_EXTENSIONS:
                            continue

                        full_path = os.path.join(dirpath, fname)
                        norm_path = normalize_video_path(full_path)
                        if not os.path.isfile(norm_path):
                            continue

                        try:
                            stat = os.stat(norm_path)
                            size = stat.st_size
                            mtime_ns = getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1e9))
                            mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                        except Exception:
                            continue

                        if size <= 0:
                            continue

                        already_in_db = norm_path in existing_paths
                        cand_id = str(uuid.uuid4())
                        candidates.append({
                            'candidate_id': cand_id,
                            'output_path': os.path.normpath(full_path),
                            'normalized_path': norm_path,
                            'filename': fname,
                            'file_size_bytes': size,
                            'file_mtime_ns': mtime_ns,
                            'mtime_iso': mtime_iso,
                            'already_exists': already_in_db
                        })

                        with self._scans_lock:
                            scan['scanned_count'] = scanned_count
                            scan['found_count'] = len(candidates)

            with self._scans_lock:
                if scan.get('status') != 'cancelled':
                    scan['candidates'] = candidates
                    scan['found_count'] = len(candidates)
                    scan['scanned_count'] = scanned_count
                    scan['status'] = 'completed'
        except Exception as exc:
            logger.error(f"[ExportHistory] Lỗi trong phiên quét import {scan_id}: {exc}", exc_info=True)
            with self._scans_lock:
                scan['status'] = 'failed'
                scan['error'] = str(exc)

    def get_import_scan_progress(self, scan_id: str) -> dict:
        """Lấy tiến độ quét import."""
        with self._scans_lock:
            scan = self._active_scans.get(scan_id)
            if not scan:
                return None
            return dict(scan)

    def cancel_import_scan(self, scan_id: str) -> bool:
        """Hủy bỏ phiên quét import."""
        with self._scans_lock:
            scan = self._active_scans.get(scan_id)
            if scan and scan['status'] == 'running':
                scan['status'] = 'cancelled'
                return True
        return False

    def commit_import_candidates(self, scan_id: str, selected_candidates: list = None) -> dict:
        """
        Lưu danh sách video candidate vào SQLite DB.
        - origin = 'import'
        - completed_at = None (không bịa ngày xuất)
        - recorded_at & imported_at = now_utc
        - source_kind = 'import'
        """
        imported_count = 0
        skipped_count = 0
        now_utc = datetime.now(timezone.utc).isoformat()

        if not selected_candidates or not isinstance(selected_candidates, list):
            return {'imported_count': 0, 'skipped_count': 0}

        with self._lock:
            with self._get_connection() as conn:
                cur = conn.cursor()
                for cand in selected_candidates:
                    out_path = cand.get('output_path')
                    norm_path = cand.get('normalized_path') or normalize_video_path(out_path)
                    
                    if not norm_path or not os.path.isfile(norm_path):
                        skipped_count += 1
                        continue

                    try:
                        stat = os.stat(norm_path)
                        size = stat.st_size
                        mtime_ns = getattr(stat, 'st_mtime_ns', int(stat.st_mtime * 1e9))
                    except Exception:
                        skipped_count += 1
                        continue

                    rec_id = str(uuid.uuid4())
                    event_key = f"import:{norm_path}"
                    fname = cand.get('filename') or os.path.basename(norm_path)

                    try:
                        cur.execute("""
                            INSERT INTO exports (
                                id, event_key, output_path, normalized_path, filename,
                                source_kind, origin, completed_at, recorded_at, imported_at,
                                file_mtime_ns, file_size_bytes, job_id, project_name, params_json
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            rec_id,
                            event_key,
                            os.path.normpath(out_path),
                            norm_path,
                            fname,
                            'import',
                            'import',
                            None,  # QUY TẮC BẮT BUỘC: Không bịa ngày xuất cho video import!
                            now_utc,
                            now_utc,
                            mtime_ns,
                            size,
                            None,
                            None,
                            json.dumps({'imported_mtime_ns': mtime_ns})
                        ))
                        imported_count += 1
                    except sqlite3.IntegrityError:
                        # Đã có trong DB
                        skipped_count += 1
                conn.commit()

        return {
            'imported_count': imported_count,
            'skipped_count': skipped_count
        }


# Singleton Pattern
_service_instance = None
_service_lock = threading.Lock()


def get_export_history_service() -> ExportHistoryService:
    """Trả về Singleton instance của ExportHistoryService."""
    global _service_instance
    if _service_instance is None:
        with _service_lock:
            if _service_instance is None:
                _service_instance = ExportHistoryService()
    return _service_instance
