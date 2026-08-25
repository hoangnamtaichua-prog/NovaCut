"""
Batch Queue Manager cho NovaCut - AI Video & Review Editor
Chế độ xử lý hàng loạt hàng đợi tự động chạy qua đêm (Overnight Batch Engine):
1. Nạp đa nguồn: Danh sách URL (Douyin, TikTok, YouTube, Bilibili) hoặc File/Folder video trên máy.
2. Preset Pipeline: Auto Review Phim AI, Auto Biên Tập Lồng Tiếng TTS, Auto Clean 9:16 Chống Bản Quyền.
3. Fault-Tolerant & Chống Treo: Bỏ qua lỗi và tự động nhảy task tiếp theo, lưu trạng thái vào user_data/batch_queue_state.json.
4. Điều khiển: Bắt đầu, Tạm dừng, Hủy, Chạy lại lỗi, Tự động tắt máy sau khi xong (Shutdown PC).
"""

import os
import sys
import json
import time
import uuid
import queue
import logging
import threading
import traceback
import subprocess
import shutil

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT_DIR, 'user_data', 'batch_queue_state.json')

logger = logging.getLogger('batch_queue')
logger.setLevel(logging.INFO)

class BatchTask:
    def __init__(self, task_dict=None):
        data = task_dict or {}
        self.id = data.get('id') or f"task_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
        self.source_type = data.get('source_type', 'url') # 'url' or 'file'
        self.source_url = data.get('source_url', '')
        self.file_path = data.get('file_path', '')
        self.title = data.get('title') or (os.path.basename(self.file_path) if self.file_path else self.source_url)
        self.thumbnail = data.get('thumbnail', '')
        self.duration = float(data.get('duration', 0.0))
        
        # Pipeline preset configuration
        self.preset = data.get('preset', 'review') # 'review', 'dubbing', 'anti_copyright'
        self.preset_config = data.get('preset_config') or {}
        
        # Execution status
        self.status = data.get('status', 'pending') # 'pending', 'downloading', 'processing', 'completed', 'failed', 'cancelled'
        self.progress = int(data.get('progress', 0))
        self.current_step_text = data.get('current_step_text', 'Đang chờ trong hàng đợi...')
        self.output_path = data.get('output_path', '')
        self.error_message = data.get('error_message', '')
        
        self.created_at = data.get('created_at', time.time())
        self.started_at = data.get('started_at', None)
        self.finished_at = data.get('finished_at', None)

    def to_dict(self):
        return {
            'id': self.id,
            'source_type': self.source_type,
            'source_url': self.source_url,
            'file_path': self.file_path,
            'title': self.title,
            'thumbnail': self.thumbnail,
            'duration': self.duration,
            'preset': self.preset,
            'preset_config': self.preset_config,
            'status': self.status,
            'progress': self.progress,
            'current_step_text': self.current_step_text,
            'output_path': self.output_path,
            'error_message': self.error_message,
            'created_at': self.created_at,
            'started_at': self.started_at,
            'finished_at': self.finished_at
        }

class BatchQueueManager:
    _instance = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self.tasks = []
        self.is_running = False
        self.is_paused = False
        self.stop_requested = False
        self.current_task_id = None
        
        self.worker_thread = None
        self.listeners = set()
        self.listeners_lock = threading.Lock()
        
        self.auto_shutdown_pc = False
        self.default_output_dir = os.path.join(ROOT_DIR, 'output', 'batch')
        
        self._load_state()

    def _load_state(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            if os.path.exists(STATE_FILE):
                with open(STATE_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.auto_shutdown_pc = data.get('auto_shutdown_pc', False)
                    self.default_output_dir = data.get('default_output_dir', self.default_output_dir)
                    loaded_tasks = data.get('tasks', [])
                    for t_data in loaded_tasks:
                        task = BatchTask(t_data)
                        # Reset any stuck 'processing' or 'downloading' state from previous crash
                        if task.status in ['processing', 'downloading']:
                            task.status = 'pending'
                            task.current_step_text = 'Đã khôi phục sau khi khởi động lại ứng dụng'
                            task.progress = 0
                        self.tasks.append(task)
        except Exception as e:
            logger.error(f"Error loading batch queue state: {e}")

    def save_state(self):
        try:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            data = {
                'auto_shutdown_pc': self.auto_shutdown_pc,
                'default_output_dir': self.default_output_dir,
                'tasks': [t.to_dict() for t in self.tasks]
            }
            with open(STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving batch queue state: {e}")

    def subscribe(self, q):
        with self.listeners_lock:
            self.listeners.add(q)

    def unsubscribe(self, q):
        with self.listeners_lock:
            self.listeners.discard(q)

    def broadcast(self, event_type, data):
        message = {
            'event': event_type,
            'data': data,
            'timestamp': time.time()
        }
        with self.listeners_lock:
            dead_queues = set()
            for q in self.listeners:
                try:
                    q.put_nowait(message)
                except Exception:
                    dead_queues.add(q)
            for q in dead_queues:
                self.listeners.discard(q)

    def add_tasks(self, raw_items, preset='review', preset_config=None):
        preset_config = preset_config or {}
        added = []
        with self._lock:
            for item in raw_items:
                if isinstance(item, str):
                    clean = item.strip()
                    if not clean:
                        continue
                    if clean.startswith(('http://', 'https://')):
                        t = BatchTask({
                            'source_type': 'url',
                            'source_url': clean,
                            'preset': preset,
                            'preset_config': preset_config
                        })
                    else:
                        t = BatchTask({
                            'source_type': 'file',
                            'file_path': clean,
                            'preset': preset,
                            'preset_config': preset_config
                        })
                    self.tasks.append(t)
                    added.append(t)
                elif isinstance(item, dict):
                    item['preset'] = item.get('preset', preset)
                    item['preset_config'] = item.get('preset_config', preset_config)
                    t = BatchTask(item)
                    self.tasks.append(t)
                    added.append(t)

            self.save_state()

        self.broadcast('queue_updated', self.get_state())
        return [t.to_dict() for t in added]

    def remove_task(self, task_id):
        with self._lock:
            target = next((t for t in self.tasks if t.id == task_id), None)
            if target:
                if self.current_task_id == task_id:
                    self.stop_requested = True
                self.tasks = [t for t in self.tasks if t.id != task_id]
                self.save_state()
        self.broadcast('queue_updated', self.get_state())
        return True

    def clear_queue(self, completed_only=False):
        with self._lock:
            if completed_only:
                self.tasks = [t for t in self.tasks if t.status not in ['completed', 'failed', 'cancelled']]
            else:
                if self.is_running:
                    self.stop_requested = True
                self.tasks = []
            self.save_state()
        self.broadcast('queue_updated', self.get_state())
        return True

    def reorder_task(self, task_id, new_index):
        with self._lock:
            target_idx = next((i for i, t in enumerate(self.tasks) if t.id == task_id), None)
            if target_idx is not None and 0 <= new_index < len(self.tasks):
                task = self.tasks.pop(target_idx)
                self.tasks.insert(new_index, task)
                self.save_state()
        self.broadcast('queue_updated', self.get_state())
        return True

    def retry_task(self, task_id):
        with self._lock:
            target = next((t for t in self.tasks if t.id == task_id), None)
            if target:
                target.status = 'pending'
                target.progress = 0
                target.error_message = ''
                target.current_step_text = 'Đã đặt lại chờ xử lý'
                self.save_state()
        self.broadcast('queue_updated', self.get_state())
        return True

    def retry_failed_tasks(self):
        count = 0
        with self._lock:
            for t in self.tasks:
                if t.status in ['failed', 'cancelled']:
                    t.status = 'pending'
                    t.progress = 0
                    t.error_message = ''
                    t.current_step_text = 'Đã đặt lại chờ xử lý'
                    count += 1
            if count > 0:
                self.save_state()
        self.broadcast('queue_updated', self.get_state())
        return count

    def set_config(self, auto_shutdown=None, default_output_dir=None):
        with self._lock:
            if auto_shutdown is not None:
                self.auto_shutdown_pc = bool(auto_shutdown)
            if default_output_dir is not None:
                self.default_output_dir = str(default_output_dir).strip()
            self.save_state()
        self.broadcast('config_updated', {
            'auto_shutdown_pc': self.auto_shutdown_pc,
            'default_output_dir': self.default_output_dir
        })
        return True

    def start_queue(self):
        with self._lock:
            if self.is_running and not self.is_paused:
                return False
            self.is_running = True
            self.is_paused = False
            self.stop_requested = False

            if not self.worker_thread or not self.worker_thread.is_alive():
                self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
                self.worker_thread.start()

        self.broadcast('queue_started', self.get_state())
        return True

    def pause_queue(self):
        with self._lock:
            self.is_paused = True
        self.broadcast('queue_paused', self.get_state())
        return True

    def resume_queue(self):
        return self.start_queue()

    def stop_queue(self):
        with self._lock:
            self.is_running = False
            self.is_paused = False
            self.stop_requested = True
            if self.current_task_id:
                curr = next((t for t in self.tasks if t.id == self.current_task_id), None)
                if curr and curr.status in ['downloading', 'processing']:
                    curr.status = 'cancelled'
                    curr.current_step_text = 'Đã hủy theo yêu cầu người dùng'
            self.current_task_id = None
            self.save_state()
        self.broadcast('queue_stopped', self.get_state())
        return True

    def get_state(self):
        total = len(self.tasks)
        completed = sum(1 for t in self.tasks if t.status == 'completed')
        failed = sum(1 for t in self.tasks if t.status == 'failed')
        pending = sum(1 for t in self.tasks if t.status == 'pending')
        running = sum(1 for t in self.tasks if t.status in ['downloading', 'processing'])

        return {
            'is_running': self.is_running,
            'is_paused': self.is_paused,
            'current_task_id': self.current_task_id,
            'auto_shutdown_pc': self.auto_shutdown_pc,
            'default_output_dir': self.default_output_dir,
            'stats': {
                'total': total,
                'completed': completed,
                'failed': failed,
                'pending': pending,
                'running': running
            },
            'tasks': [t.to_dict() for t in self.tasks]
        }

    # =========================================================================
    # CORE WORKER LOOP & PIPELINE DISPATCHER
    # =========================================================================
    def _worker_loop(self):
        logger.info("Batch Queue Worker started.")
        while self.is_running:
            if self.stop_requested:
                break

            if self.is_paused:
                time.sleep(0.5)
                continue

            # Find next pending task
            next_task = None
            with self._lock:
                for t in self.tasks:
                    if t.status == 'pending':
                        next_task = t
                        break

            if not next_task:
                # No more pending tasks!
                logger.info("All tasks in Batch Queue have finished.")
                break

            self.current_task_id = next_task.id
            next_task.started_at = time.time()
            self.save_state()
            self.broadcast('task_started', next_task.to_dict())

            try:
                self._process_single_task(next_task)
            except Exception as e:
                logger.error(f"Fatal error processing task {next_task.id}: {traceback.format_exc()}")
                next_task.status = 'failed'
                next_task.error_message = str(e)
                next_task.current_step_text = f"🛑 Lỗi: {str(e)}"
            finally:
                next_task.finished_at = time.time()
                self.current_task_id = None
                self.save_state()
                self.broadcast('task_finished', next_task.to_dict())
                self.broadcast('queue_updated', self.get_state())

            time.sleep(1.0)

        with self._lock:
            self.is_running = False
            self.is_paused = False
            self.current_task_id = None
            self.save_state()

        self.broadcast('queue_finished', self.get_state())

        # Check Auto-Shutdown PC
        if self.auto_shutdown_pc and not self.stop_requested:
            self._trigger_pc_shutdown()

    def _trigger_pc_shutdown(self):
        try:
            logger.info("Auto-shutdown PC triggered. Shutting down in 60 seconds...")
            self.broadcast('shutdown_countdown', {'seconds': 60})
            if os.name == 'nt':
                subprocess.run(['shutdown', '/s', '/t', '60', '/c', 'NovaCut đã hoàn thành toàn bộ hàng đợi xử lý video qua đêm. Máy tính sẽ tự động tắt trong 60 giây.'], check=False)
        except Exception as e:
            logger.error(f"Failed to shutdown PC: {e}")

    def _process_single_task(self, task):
        def update_progress(pct, text=None):
            task.progress = max(0, min(100, int(pct)))
            if text:
                task.current_step_text = text
            self.broadcast('task_progress', {
                'id': task.id,
                'progress': task.progress,
                'current_step_text': task.current_step_text
            })

        update_progress(5, "Đang chuẩn bị dữ liệu đầu vào...")

        # -------------------------------------------------------------
        # STEP 1: RESOLVE LOCAL VIDEO FILE (DOWNLOAD IF URL)
        # -------------------------------------------------------------
        local_video_path = task.file_path
        if task.source_type == 'url' or (task.source_url and not os.path.exists(local_video_path or '')):
            update_progress(10, f"Đang tải video từ liên kết mạng...")
            task.status = 'downloading'
            self.broadcast('task_status_changed', task.to_dict())

            import downloader
            download_dir = os.path.join(ROOT_DIR, 'downloads', 'batch_temp')
            os.makedirs(download_dir, exist_ok=True)

            def dl_prog(p_data):
                if p_data.get('status') == 'downloading':
                    percent = p_data.get('percent', 0)
                    scaled_pct = int(10 + (percent * 0.25))
                    update_progress(scaled_pct, f"Đang tải video: {percent:.1f}% ({p_data.get('speed_str', '')})")

            dl_file, info = downloader.download_media(
                url=task.source_url,
                output_dir=download_dir,
                progress_callback=dl_prog
            )

            if not dl_file or not os.path.exists(dl_file):
                raise RuntimeError(f"Không thể tải video từ URL: {task.source_url}")

            local_video_path = dl_file
            task.file_path = dl_file
            task.title = info.get('title') or os.path.basename(dl_file)
            task.thumbnail = info.get('thumbnail') or ''
            task.duration = float(info.get('duration') or 0.0)

        if not local_video_path or not os.path.exists(local_video_path):
            raise FileNotFoundError(f"Không tìm thấy tệp video: {local_video_path}")

        task.status = 'processing'
        self.broadcast('task_status_changed', task.to_dict())
        update_progress(35, "Bắt đầu xử lý pipeline...")

        # -------------------------------------------------------------
        # STEP 2: DISPATCH TO PRESET PIPELINE
        # -------------------------------------------------------------
        preset = task.preset or 'review'
        config = task.preset_config or {}
        output_dir = config.get('output_dir') or self.default_output_dir
        os.makedirs(output_dir, exist_ok=True)

        base_name = os.path.splitext(os.path.basename(local_video_path))[0]
        timestamp_suffix = time.strftime('%Y%m%d_%H%M%S')
        out_filename = f"{base_name}_{preset}_{timestamp_suffix}.mp4"
        final_output_path = os.path.join(output_dir, out_filename)

        if preset == 'review':
            self._run_preset_movie_review(task, local_video_path, final_output_path, config, update_progress)
        elif preset == 'dubbing':
            self._run_preset_dubbing(task, local_video_path, final_output_path, config, update_progress)
        elif preset == 'anti_copyright':
            self._run_preset_anti_copyright(task, local_video_path, final_output_path, config, update_progress)
        else:
            # Default fallback to Review Phim
            self._run_preset_movie_review(task, local_video_path, final_output_path, config, update_progress)

        if not os.path.exists(final_output_path):
            raise RuntimeError(f"Pipeline hoàn thành nhưng không tìm thấy file đầu ra: {final_output_path}")

        task.output_path = final_output_path
        task.status = 'completed'
        task.progress = 100
        task.current_step_text = f"✅ Hoàn thành xuất sắc: {os.path.basename(final_output_path)}"

    # -------------------------------------------------------------------------
    # PRESET 1: AUTO MOVIE REVIEW / RECAP AI
    # -------------------------------------------------------------------------
    def _run_preset_movie_review(self, task, video_path, output_path, config, update_progress):
        import asr_manager
        import ffmpeg_installer

        update_progress(40, "Đang chạy trích xuất phụ đề tự động (ASR Whisper)...")
        srt_path = asr_manager.get_or_create_srt(video_path, None)
        if not srt_path or not os.path.exists(srt_path):
            raise RuntimeError("Trích xuất ASR phụ đề thất bại")

        update_progress(55, "Đang tạo kịch bản tóm tắt AI (LLM Recap)...")
        import auto_edit_pipeline
        payload = {
            'video_path': video_path,
            'srt_path': srt_path,
            'voice_id': config.get('voice_id', 'ngoc_huyen'),
            'voice_speed': float(config.get('voice_speed', 1.0)),
            'orig_volume': float(config.get('orig_volume', 0.15)),
            'output_dir': os.path.dirname(output_path),
            'output_name': os.path.basename(output_path),
            'aspect_ratio': config.get('aspect_ratio', '9:16'),
            'auto_subtitles': bool(config.get('auto_subtitles', True)),
            'openai_model': config.get('openai_model', 'gpt-5.6-luna'),
            'bgm': config.get('bgm', {'enabled': True, 'volume': 12}),
            'review_style': config.get('review_style', 'dramatic'),
            'custom_style_prompt': config.get('custom_style_prompt', '')
        }

        def check_stop():
            return self.stop_requested or task.status == 'cancelled'

        update_progress(65, "Đang tạo giọng đọc TTS & cắt ghép phân cảnh...")
        gen = auto_edit_pipeline.run_auto_edit_workflow(payload, check_stop)
        for chunk in gen:
            if check_stop():
                task.status = 'cancelled'
                raise RuntimeError("Nhiệm vụ đã bị dừng bởi người dùng")
            if chunk.startswith('data: '):
                line = chunk[6:].strip()
                if '[PROGRESS]' in line:
                    try:
                        p_val = int(line.split('[PROGRESS]')[1].strip())
                        scaled = int(65 + (p_val * 0.35))
                        update_progress(scaled)
                    except Exception:
                        pass
                elif 'Render' in line or 'FFmpeg' in line or 'TTS' in line:
                    update_progress(task.progress, line[:80])

    # -------------------------------------------------------------------------
    # PRESET 2: AUTO DUBBING & SUBTITLE TRANSLATION
    # -------------------------------------------------------------------------
    def _run_preset_dubbing(self, task, video_path, output_path, config, update_progress):
        import auto_edit_pipeline
        
        payload = {
            'video_path': video_path,
            'voice_id': config.get('voice_id', 'ngoc_huyen'),
            'voice_speed': float(config.get('voice_speed', 1.0)),
            'orig_volume': float(config.get('orig_volume', 0.05)),
            'output_dir': os.path.dirname(output_path),
            'output_name': os.path.basename(output_path),
            'aspect_ratio': config.get('aspect_ratio', 'original'),
            'auto_subtitles': bool(config.get('auto_subtitles', True)),
            'remove_original_vocals': bool(config.get('remove_original_vocals', True)),
            'bgm': config.get('bgm', {'enabled': False})
        }

        def check_stop():
            return self.stop_requested or task.status == 'cancelled'

        update_progress(45, "Đang xử lý lồng tiếng AI Narration...")
        gen = auto_edit_pipeline.run_narration_workflow(payload, check_stop)
        for chunk in gen:
            if check_stop():
                task.status = 'cancelled'
                raise RuntimeError("Nhiệm vụ đã bị dừng bởi người dùng")
            if chunk.startswith('data: '):
                line = chunk[6:].strip()
                if '[PROGRESS]' in line:
                    try:
                        p_val = int(line.split('[PROGRESS]')[1].strip())
                        scaled = int(45 + (p_val * 0.55))
                        update_progress(scaled)
                    except Exception:
                        pass

    # -------------------------------------------------------------------------
    # PRESET 3: AUTO CLEAN & RE-FORMAT 9:16 ANTI-COPYRIGHT
    # -------------------------------------------------------------------------
    def _run_preset_anti_copyright(self, task, video_path, output_path, config, update_progress):
        import ffmpeg_installer
        ffmpeg_path = ffmpeg_installer.ensure_ffmpeg()

        update_progress(40, "Đang cấu hình bộ lọc chống bản quyền (Flip + Zoom 1.05x + Speed 1.05x)...")
        speed = float(config.get('speed', 1.05))
        zoom = float(config.get('zoom', 1.05))
        mirror = bool(config.get('mirror', True))
        aspect = config.get('aspect_ratio', '9:16')

        # Video filters
        v_filters = []
        if mirror:
            v_filters.append("hflip")
        if speed != 1.0:
            v_filters.append(f"setpts={1.0/speed:.4f}*PTS")
        if zoom > 1.0:
            v_filters.append(f"scale=iw*{zoom:.2f}:ih*{zoom:.2f},crop=iw/{zoom:.2f}:ih/{zoom:.2f}")

        # Aspect ratio format
        if aspect == '9:16':
            v_filters.append("scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black")
        elif aspect == '16:9':
            v_filters.append("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black")

        v_filter_str = ",".join(v_filters) if v_filters else "null"
        a_filter_str = f"atempo={speed:.4f}" if speed != 1.0 else "anull"

        cmd = [
            ffmpeg_path, '-y', '-hide_banner', '-loglevel', 'error',
            '-i', video_path,
            '-filter:v', v_filter_str,
            '-filter:a', a_filter_str,
            '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '22',
            '-c:a', 'aac', '-b:a', '192k',
            output_path
        ]

        update_progress(60, "Đang render video thành phẩm...")
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, **ffmpeg_installer.get_stealth_subprocess_kwargs())
        if proc.returncode != 0:
            raise RuntimeError(f"FFmpeg Render Anti-Copyright lỗi: {proc.stderr[:300]}")
        update_progress(95, "Hoàn tất render!")
