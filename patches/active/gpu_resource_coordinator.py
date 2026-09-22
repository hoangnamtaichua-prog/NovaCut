"""
gpu_resource_coordinator.py - App-Level GPU Resource Coordinator
Coordinates exclusive and shared GPU access between VieNeu TTS, RapidOCR, Faster-Whisper ASR, and RVC.
Prevents CUDA Out-Of-Memory (OOM) on 8 GB VRAM GPUs (like RTX 5060) by queueing heavy workloads,
prompting resident model unloads at safe batch boundaries, and tracking GPU wait/reload times.
"""

import time
import threading
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger("gpu_resource_coordinator")
logger.setLevel(logging.INFO)


class GPUResourceCoordinator:
    def __init__(self):
        self._lock = threading.RLock()
        self._condition = threading.Condition(self._lock)
        self._current_holder: Optional[str] = None
        self._yield_requested: bool = False
        self._tts_worker_client = None
        self._unload_callbacks: Dict[str, Any] = {}
        
        # Diagnostics
        self._total_acquisitions = 0
        self._stats: Dict[str, Dict[str, Any]] = {
            "tts": {"acquire_count": 0, "total_wait_sec": 0.0, "total_held_sec": 0.0, "last_reload_sec": 0.0},
            "ocr": {"acquire_count": 0, "total_wait_sec": 0.0, "total_held_sec": 0.0},
            "asr": {"acquire_count": 0, "total_wait_sec": 0.0, "total_held_sec": 0.0},
            "rvc": {"acquire_count": 0, "total_wait_sec": 0.0, "total_held_sec": 0.0},
        }
        self._acquire_start_times: Dict[str, float] = {}

    def register_tts_worker(self, worker_client):
        """Registers the active VieNeu worker client to allow graceful GPU yielding."""
        with self._lock:
            self._tts_worker_client = worker_client

    def register_unload_callback(self, task_name: str, callback):
        """Registers an unload callback to be invoked when task_name is asked to yield GPU."""
        with self._lock:
            self._unload_callbacks[task_name] = callback

    def should_tts_yield(self) -> bool:
        """Called by TTS batch loop between batches to check if another heavy task needs GPU."""
        with self._lock:
            return self._yield_requested and (self._current_holder != "tts" or True)

    def acquire_gpu(self, task_name: str, priority: int = 1, timeout: float = 60.0) -> bool:
        """
        Acquires GPU ownership for a task.
        If TTS is holding GPU and a higher priority/different task requests GPU,
        TTS is prompted to yield and unload resident weights.
        """
        t0 = time.perf_counter()
        deadline = t0 + timeout

        with self._condition:
            # If current holder is already this task, return True (re-entrant within same task)
            if self._current_holder == task_name:
                return True

            # If TTS currently holds GPU and another task needs it, request TTS to yield
            if self._current_holder == "tts" and task_name != "tts":
                self._yield_requested = True
                logger.info(f"[GPU Coordinator] Task '{task_name}' requesting GPU. Signaling TTS to yield/unload...")
                if "tts" in self._unload_callbacks:
                    try:
                        self._unload_callbacks["tts"]()
                    except Exception as e:
                        logger.warning(f"[GPU Coordinator] Unload callback error: {e}")
                if self._tts_worker_client and hasattr(self._tts_worker_client, "request_yield"):
                    try:
                        self._tts_worker_client.request_yield()
                    except Exception as e:
                        logger.warning(f"[GPU Coordinator] Could not trigger TTS yield: {e}")

            # Wait for GPU to become free
            while self._current_holder is not None:
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    wait_time = time.perf_counter() - t0
                    logger.error(f"[GPU Coordinator] Timeout waiting for GPU by '{task_name}' after {wait_time:.2f}s (held by '{self._current_holder}')")
                    return False
                self._condition.wait(timeout=min(0.5, remaining))

            # Acquire
            wait_time = time.perf_counter() - t0
            self._current_holder = task_name
            self._yield_requested = False
            self._total_acquisitions += 1
            self._acquire_start_times[task_name] = time.perf_counter()

            if task_name in self._stats:
                self._stats[task_name]["acquire_count"] += 1
                self._stats[task_name]["total_wait_sec"] += wait_time

            logger.info(f"[GPU Coordinator] GPU granted to '{task_name}' (waited {wait_time:.3f}s)")
            return True

    def release_gpu(self, task_name: str):
        """Releases GPU ownership and notifies any waiting tasks."""
        with self._condition:
            if self._current_holder == task_name:
                held_time = time.perf_counter() - self._acquire_start_times.get(task_name, time.perf_counter())
                if task_name in self._stats:
                    self._stats[task_name]["total_held_sec"] += held_time
                self._current_holder = None
                self._yield_requested = False
                logger.info(f"[GPU Coordinator] GPU released by '{task_name}' (held for {held_time:.3f}s)")
                self._condition.notify_all()
            else:
                logger.warning(f"[GPU Coordinator] Task '{task_name}' attempted to release GPU, but holder was '{self._current_holder}'")

    def record_tts_reload(self, reload_sec: float):
        """Records model reload duration for reporting."""
        with self._lock:
            if "tts" in self._stats:
                self._stats["tts"]["last_reload_sec"] = reload_sec

    def get_status(self) -> Dict[str, Any]:
        """Returns current coordinator diagnostics."""
        with self._lock:
            return {
                "current_holder": self._current_holder,
                "yield_requested": self._yield_requested,
                "total_acquisitions": self._total_acquisitions,
                "stats": {k: dict(v) for k, v in self._stats.items()}
            }


_COORDINATOR_INSTANCE = None
_COORDINATOR_LOCK = threading.Lock()

def get_gpu_coordinator() -> GPUResourceCoordinator:
    """Singleton getter for GPU coordinator."""
    global _COORDINATOR_INSTANCE
    if _COORDINATOR_INSTANCE is None:
        with _COORDINATOR_LOCK:
            if _COORDINATOR_INSTANCE is None:
                _COORDINATOR_INSTANCE = GPUResourceCoordinator()
    return _COORDINATOR_INSTANCE
