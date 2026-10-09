# -*- coding: utf-8 -*-
"""
NovaCut Decoupled Export Job Manager
Quản lý tác vụ xuất video nền độc lập với kết nối SSE HTTP, duy trì bộ đệm sự kiện
cho phép kết nối lại (reconnect), phát heartbeat định kỳ, quản lý vòng đời child process,
và lưu trữ trạng thái bền vững (persistence).
"""

import os
import sys
import time
import json
import uuid
import logging
import threading
import subprocess
import collections
from datetime import datetime, timezone
from platformdirs import user_data_dir

logger = logging.getLogger(__name__)

USER_DATA_DIR = user_data_dir('NovaCut', 'NovaCut', roaming=True)
JOBS_DIR = os.path.join(USER_DATA_DIR, 'export_jobs')
LOGS_DIR = os.path.join(USER_DATA_DIR, 'export_logs')
os.makedirs(JOBS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)


class JobState:
    QUEUED = 'queued'
    RUNNING = 'running'
    CANCELLING = 'cancelling'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'
    CANCELLED = 'cancelled'
    INTERRUPTED = 'interrupted'

    TERMINAL_STATES = {SUCCEEDED, FAILED, CANCELLED, INTERRUPTED}


class JobStage:
    PREPARING = 'preparing'
    TTS_GENERATING = 'tts_generating'
    STEM_SEPARATING = 'stem_separating'
    BUILDING_FILTERS = 'building_filters'
    ENCODING = 'encoding'
    FINALIZING = 'finalizing'


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _terminate_pid(pid):
    if not pid:
        return False
    try:
        if os.name == 'nt':
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(pid)],
                capture_output=True,
                timeout=10,
                creationflags=0x08000000
            )
        else:
            import signal
            os.kill(pid, signal.SIGKILL)
        return True
    except Exception as e:
        logger.warning(f"[JobManager] Không thể kill PID {pid}: {e}")
        return False


class ExportJob:
    """Đại diện cho một tác vụ xuất video độc lập."""

    def __init__(self, job_id=None, params=None, source_tool='editor', export_run_id=None):
        self.job_id = job_id or f"exp_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}"
        self.export_run_id = export_run_id or self.job_id
        self.source_tool = source_tool
        self.params = params or {}
        self.state = JobState.QUEUED
        self.stage = JobStage.PREPARING
        self.stage_progress = 0.0
        self.stage_message = "Đang chuẩn bị..."
        self.overall_progress = 0.0
        self.created_at = _now_iso()
        self.updated_at = self.created_at
        self.last_progress_at = time.monotonic()
        self.output_path = None
        self.size_mb = None
        self.history_id = None
        self.error = None
        self.error_details = None

        self.stop_event = threading.Event()
        self._lock = threading.RLock()
        self._cond = threading.Condition(self._lock)
        self._seq = 0
        self._event_buffer = collections.deque(maxlen=2000)
        self._child_processes = set()

        self.log_file_path = os.path.join(LOGS_DIR, f"job_{self.job_id}.log")
        self._init_log_file()
        self.persist_state()

    def _init_log_file(self):
        try:
            with open(self.log_file_path, 'w', encoding='utf-8') as f:
                f.write(f"=== NOVACUT EXPORT JOB LOG: {self.job_id} ===\n")
                f.write(f"Created: {self.created_at}\n")
                f.write(f"Source Tool: {self.source_tool}\n")
                f.write(f"Input: {self.params.get('inputVideo', 'N/A')}\n")
                f.write(f"Output: {self.params.get('outputName', 'N/A')}\n")
                f.write("=" * 50 + "\n\n")
        except Exception as e:
            logger.error(f"[JobManager] Lỗi khởi tạo file log: {e}")

    def append_raw_log(self, text):
        try:
            with open(self.log_file_path, 'a', encoding='utf-8') as f:
                f.write(f"[{time.strftime('%H:%M:%S')}] {text}\n")
        except Exception:
            pass

    def register_process(self, proc):
        with self._lock:
            if proc:
                self._child_processes.add(proc)

    def unregister_process(self, proc):
        with self._lock:
            self._child_processes.discard(proc)

    def terminate_child_processes(self):
        with self._lock:
            procs = list(self._child_processes)
            self._child_processes.clear()
        for p in procs:
            try:
                if p and p.poll() is None:
                    _terminate_pid(p.pid)
            except Exception:
                pass

    def is_terminal(self):
        with self._lock:
            return self.state in JobState.TERMINAL_STATES

    def is_stopped(self):
        return self.stop_event.is_set()

    def set_running(self):
        with self._lock:
            if self.state != JobState.QUEUED:
                return
            self.state = JobState.RUNNING
            self.updated_at = _now_iso()
            self.last_progress_at = time.monotonic()
            self._cond.notify_all()
        self.persist_state()

    def set_stage(self, stage, progress=0.0, message=None):
        with self._lock:
            if self.is_terminal():
                return
            self.stage = stage
            self.stage_progress = float(progress)
            if message:
                self.stage_message = str(message)
            self.updated_at = _now_iso()
            self.last_progress_at = time.monotonic()

            stage_event = {
                'stage': self.stage,
                'progress': self.stage_progress,
                'message': self.stage_message
            }
            self._emit_event_locked('stage', stage_event)
            self._cond.notify_all()
        self.persist_state()

    def emit_log(self, text, level='info'):
        clean_text = str(text).strip()
        if not clean_text:
            return
        self.append_raw_log(f"[{level.upper()}] {clean_text}")
        with self._lock:
            self._emit_event_locked('log', {'text': clean_text, 'level': level})
            self._cond.notify_all()

    def emit_progress(self, stage, progress, message=None, speed=None, eta=None):
        with self._lock:
            if self.is_terminal():
                return
            self.stage = stage
            self.stage_progress = float(progress)
            if message:
                self.stage_message = str(message)
            self.updated_at = _now_iso()
            self.last_progress_at = time.monotonic()

            payload = {
                'stage': stage,
                'progress': self.stage_progress,
                'message': self.stage_message,
                'speed': speed,
                'eta': eta
            }
            self._emit_event_locked('progress', payload)
            self._cond.notify_all()

        int_pct = int(progress)
        if int_pct % 5 == 0 and int_pct != getattr(self, '_last_disk_log_pct', -1):
            self._last_disk_log_pct = int_pct
            speed_info = f" | {speed}x" if speed else ""
            eta_info = f" | Còn lại: {eta}" if eta else ""
            self.append_raw_log(f"[PROGRESS] {stage}: {int_pct}%{speed_info}{eta_info} - {message or ''}")

    def set_success(self, output_path, size_mb, history_id=None):
        with self._lock:
            if self.is_terminal():
                return
            self.state = JobState.SUCCEEDED
            self.stage = JobStage.FINALIZING
            self.stage_progress = 100.0
            self.overall_progress = 100.0
            self.output_path = output_path
            self.size_mb = size_mb
            self.history_id = history_id
            self.updated_at = _now_iso()
            self.last_progress_at = time.monotonic()

            payload = {
                'path': output_path,
                'size_mb': round(size_mb, 2) if size_mb else 0.0,
                'history_id': history_id,
                'job_id': self.job_id
            }
            self._emit_event_locked('success', payload)
            self._cond.notify_all()
        self.append_raw_log(f"SUCCESS: {output_path} ({size_mb} MB)")
        self.persist_state()

    def set_failed(self, reason, details=None):
        with self._lock:
            if self.is_terminal():
                return
            self.state = JobState.FAILED
            self.error = str(reason)
            self.error_details = details or {}
            self.updated_at = _now_iso()
            self.last_progress_at = time.monotonic()

            payload = {
                'reason': self.error,
                'stage': self.stage,
                'details': self.error_details,
                'job_id': self.job_id
            }
            self._emit_event_locked('failed', payload)
            self._cond.notify_all()
        self.append_raw_log(f"FAILED in stage {self.stage}: {reason}")
        self.persist_state()

    def set_cancelled(self, reason="Người dùng đã dừng tác vụ"):
        with self._lock:
            if self.is_terminal():
                return
            self.state = JobState.CANCELLED
            self.error = str(reason)
            self.updated_at = _now_iso()
            self.last_progress_at = time.monotonic()

            payload = {
                'reason': self.error,
                'stage': self.stage,
                'job_id': self.job_id
            }
            self._emit_event_locked('cancelled', payload)
            self._cond.notify_all()
        self.append_raw_log(f"CANCELLED: {reason}")
        self.persist_state()

    def request_cancel(self, reason="Yêu cầu dừng tác vụ"):
        with self._lock:
            if self.is_terminal():
                return False
            self.state = JobState.CANCELLING
            self.stop_event.set()
            self.updated_at = _now_iso()
            self._cond.notify_all()
        self.append_raw_log(f"REQUEST CANCEL: {reason}")
        self.terminate_child_processes()
        self.persist_state()
        return True

    def _emit_event_locked(self, event_type, data):
        self._seq += 1
        event_obj = {
            'seq': self._seq,
            'type': event_type,
            'data': data,
            'timestamp': time.time()
        }
        self._event_buffer.append(event_obj)

    def get_events_after(self, after_seq=0):
        with self._lock:
            return [e for e in self._event_buffer if e['seq'] > after_seq]

    def stream_events(self, start_seq=0, heartbeat_interval=10.0):
        """
        Generator phát stream SSE độc lập.
        - Phát lại các sự kiện có seq > start_seq từ buffer.
        - Ngủ đợi sự kiện mới qua Condition variable; nếu hết timeout phát heartbeat comment.
        - Tiếp tục cho đến khi tác vụ ở trạng thái terminal và toàn bộ sự kiện đã được gửi.
        - KHÔNG bị ảnh hưởng bởi GeneratorExit của client khác.
        """
        last_sent_seq = int(start_seq or 0)
        yield f": job_id: {self.job_id}\n\n"

        while True:
            events_to_send = []
            is_done = False

            with self._lock:
                for ev in self._event_buffer:
                    if ev['seq'] > last_sent_seq:
                        events_to_send.append(ev)

                if not events_to_send:
                    if self.is_terminal():
                        is_done = True
                    else:
                        # Đợi sự kiện mới hoặc timeout để phát heartbeat
                        signaled = self._cond.wait(timeout=heartbeat_interval)
                        if not signaled:
                            # Timeout -> phát heartbeat SSE
                            hb_payload = {
                                'job_id': self.job_id,
                                'stage': self.stage,
                                'progress': self.stage_progress,
                                'state': self.state,
                                'uptime': round(time.monotonic() - self.last_progress_at, 1)
                            }
                            yield f": heartbeat\n\n"
                            yield f"data: [HEARTBEAT] {json.dumps(hb_payload)}\n\n"
                            continue
                        else:
                            for ev in self._event_buffer:
                                if ev['seq'] > last_sent_seq:
                                    events_to_send.append(ev)
                            if not events_to_send and self.is_terminal():
                                is_done = True

            for ev in events_to_send:
                last_sent_seq = ev['seq']
                ev_type = ev['type']
                ev_data = ev['data']

                if ev_type == 'log':
                    text = ev_data.get('text', '')
                    yield f"id: {ev['seq']}\ndata: {text}\n\n"
                elif ev_type == 'progress':
                    msg = ev_data.get('message') or ''
                    pct = ev_data.get('progress', 0)
                    speed = ev_data.get('speed')
                    speed_str = f" | {speed}x" if speed else ""
                    eta = ev_data.get('eta')
                    eta_str = f" | Còn lại: {eta}" if eta else ""
                    yield f"id: {ev['seq']}\ndata: ⏳ [Tiến độ: {int(pct)}%{speed_str}{eta_str}] {msg}\n\n"
                    yield f"id: {ev['seq']}\ndata: [EVENT:PROGRESS] {json.dumps(ev_data)}\n\n"
                elif ev_type == 'stage':
                    yield f"id: {ev['seq']}\ndata: [EVENT:STAGE] {json.dumps(ev_data)}\n\n"
                elif ev_type == 'success':
                    yield f"id: {ev['seq']}\ndata: [EVENT:SUCCESS] {json.dumps(ev_data)}\n\n"
                    yield f"id: {ev['seq']}\ndata: --- HOÀN THÀNH QUÁ TRÌNH TẠO ---\n\n"
                elif ev_type == 'failed':
                    yield f"id: {ev['seq']}\ndata: [EVENT:FAILED] {json.dumps(ev_data)}\n\n"
                elif ev_type == 'cancelled':
                    yield f"id: {ev['seq']}\ndata: [EVENT:CANCELLED] {json.dumps(ev_data)}\n\n"

            if is_done and not events_to_send:
                break

    def to_dict(self):
        with self._lock:
            return {
                'job_id': self.job_id,
                'export_run_id': self.export_run_id,
                'source_tool': self.source_tool,
                'state': self.state,
                'stage': self.stage,
                'stage_progress': self.stage_progress,
                'stage_message': self.stage_message,
                'overall_progress': self.overall_progress,
                'created_at': self.created_at,
                'updated_at': self.updated_at,
                'last_progress_at': self.last_progress_at,
                'output_path': self.output_path,
                'size_mb': self.size_mb,
                'history_id': self.history_id,
                'error': self.error,
                'error_details': self.error_details,
                'log_file': self.log_file_path,
                'last_seq': self._seq
            }

    def persist_state(self):
        try:
            target_path = os.path.join(JOBS_DIR, f"{self.job_id}.json")
            tmp_path = target_path + f".tmp_{os.getpid()}_{threading.get_ident()}_{int(time.time()*1000)}.json"
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
            if os.path.exists(target_path):
                try:
                    os.replace(tmp_path, target_path)
                except Exception:
                    os.remove(target_path)
                    os.rename(tmp_path, target_path)
            else:
                os.rename(tmp_path, target_path)
        except Exception as e:
            logger.error(f"[JobManager] Lỗi lưu trạng thái job {self.job_id}: {e}")


class ExportJobManager:
    """Quản lý tập trung các tác vụ xuất video trong NovaCut."""

    def __init__(self):
        self._lock = threading.RLock()
        self._jobs = {}
        self._active_job = None
        self._reconcile_saved_jobs()

    def _reconcile_saved_jobs(self):
        """
        Khôi phục metadata từ đĩa. Nếu phát hiện job cũ còn ở trạng thái running
        hoặc cancelling sau khi ứng dụng restart, chuyển thành interrupted.
        """
        if not os.path.exists(JOBS_DIR):
            return
        for fname in os.listdir(JOBS_DIR):
            if fname.endswith('.json'):
                try:
                    fpath = os.path.join(JOBS_DIR, fname)
                    with open(fpath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    job_id = data.get('job_id')
                    state = data.get('state')
                    if state in (JobState.RUNNING, JobState.CANCELLING, JobState.QUEUED):
                        data['state'] = JobState.INTERRUPTED
                        data['error'] = 'Tiến trình bị gián đoạn do khởi động lại ứng dụng hoặc máy chủ.'
                        data['updated_at'] = _now_iso()
                        with open(fpath, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass

    def create_job(self, params, run_fn, source_tool='editor', export_run_id=None):
        with self._lock:
            if self._active_job and not self._active_job.is_terminal():
                raise RuntimeError("Một tác vụ xuất video khác đang chạy. Vui lòng chờ hoàn tất hoặc hủy tác vụ hiện tại.")

            job = ExportJob(params=params, source_tool=source_tool, export_run_id=export_run_id)
            self._jobs[job.job_id] = job
            self._active_job = job

            def _worker_wrapper():
                job.set_running()
                try:
                    run_fn(job)
                except Exception as e:
                    logger.exception(f"[JobManager] Ngoại lệ ngoài ý muốn trong worker {job.job_id}: {e}")
                    job.set_failed(f"Lỗi thực thi worker: {e}", details={'traceback': str(e)})
                finally:
                    job.terminate_child_processes()
                    with self._lock:
                        if self._active_job is job:
                            self._active_job = None

            t = threading.Thread(target=_worker_wrapper, name=f"ExportWorker-{job.job_id}", daemon=True)
            t.start()
            return job

    def get_job(self, job_id):
        with self._lock:
            if job_id in self._jobs:
                return self._jobs[job_id]
        # Thử đọc từ đĩa nếu không có trong memory
        job_file = os.path.join(JOBS_DIR, f"{job_id}.json")
        if os.path.exists(job_file):
            try:
                with open(job_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data
            except Exception:
                pass
        return None

    def get_active_job(self):
        with self._lock:
            if self._active_job and not self._active_job.is_terminal():
                return self._active_job
            return None

    def cancel_job(self, job_id=None, reason="Người dùng đã gửi yêu cầu dừng"):
        with self._lock:
            job = None
            if job_id:
                job = self._jobs.get(job_id)
            elif self._active_job:
                job = self._active_job

            if not job or isinstance(job, dict):
                return False

            stopped = job.request_cancel(reason=reason)
            return stopped


# Singleton instance
_manager_instance = None
_manager_lock = threading.Lock()


def get_export_job_manager() -> ExportJobManager:
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = ExportJobManager()
        return _manager_instance
