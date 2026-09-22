"""
local_voice_worker_client.py - IPC Client for Isolated VieNeu GPU Worker
Runs inside NovaCut's main process. Communicates with local_voice_worker.py via JSON Lines.
Cleans child environment (removes PYTHONHOME/PYTHONPATH), intercepts crashes,
supports graceful unload/reload for GPU coordinator, and handles cancel tokens.
"""

import os
import sys
import json
import time
import subprocess
import threading
import logging
from typing import Dict, Any, List, Optional, Callable

logger = logging.getLogger("local_voice_worker_client")
logger.setLevel(logging.INFO)

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKER_SCRIPT = os.path.join(ROOT_DIR, "local_voice_worker.py")
GPU_RUNTIME_DIR = os.path.join(ROOT_DIR, "runtimes", "vieneu_gpu")
GPU_PYTHON = os.path.join(GPU_RUNTIME_DIR, "Scripts", "python.exe")


class VieNeuWorkerCrashError(RuntimeError):
    pass


class VieNeuWorkerClient:
    def __init__(self, python_path: Optional[str] = None):
        self.python_path = python_path or GPU_PYTHON
        self.proc: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        self._req_counter = 0
        self._is_ready = False
        self._handshake_data: Dict[str, Any] = {}
        self._yield_requested = False
        self._crash_count = 0
        self._max_crashes = 3

    def is_runtime_available(self) -> bool:
        """Checks if the isolated GPU virtual environment python executable exists."""
        return os.path.exists(self.python_path) and os.path.exists(WORKER_SCRIPT)

    def _clean_child_env(self) -> Dict[str, str]:
        """Sanitizes child environment to avoid polluting worker with main app's python/packages/DLLs."""
        env = os.environ.copy()
        # Remove Python environment variables that could cause child to load parent site-packages
        for var in ["PYTHONHOME", "PYTHONPATH", "PYTHONEXECUTABLE"]:
            env.pop(var, None)

        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        return env

    def start_worker(self) -> bool:
        with self._lock:
            if self.proc is not None and self.proc.poll() is None:
                return True

            if not self.is_runtime_available():
                logger.warning(f"[VieNeu Client] GPU runtime python not found at: {self.python_path}")
                return False

            cmd = [self.python_path, "-u", WORKER_SCRIPT]
            env = self._clean_child_env()

            creation_flags = 0x08000000 if os.name == 'nt' else 0  # CREATE_NO_WINDOW
            try:
                self.proc = subprocess.Popen(
                    cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    bufsize=1,
                    env=env,
                    cwd=ROOT_DIR,
                    creationflags=creation_flags
                )

                # Thread to log stderr
                def _log_stderr(proc_pipe):
                    for line in iter(proc_pipe.readline, ''):
                        if line:
                            logger.info(line.strip())

                threading.Thread(target=_log_stderr, args=(self.proc.stderr,), daemon=True).start()

                # Perform handshake
                resp = self._send_command({"cmd": "handshake"}, timeout=30.0)
                if resp.get("status") == "ok":
                    self._is_ready = True
                    self._handshake_data = resp
                    self._crash_count = 0
                    logger.info(f"[VieNeu Client] Worker connected successfully! GPU: {resp.get('device_name')} (Torch {resp.get('torch_version')})")
                    return True
                else:
                    logger.error(f"[VieNeu Client] Handshake failed: {resp}")
                    self.stop_worker()
                    return False
            except Exception as e:
                logger.error(f"[VieNeu Client] Failed to launch worker: {e}")
                self.stop_worker()
                return False

    def stop_worker(self):
        with self._lock:
            if self.proc is not None:
                try:
                    if self.proc.poll() is None:
                        try:
                            self._send_command({"cmd": "shutdown"}, timeout=3.0)
                        except Exception:
                            pass
                        self.proc.terminate()
                        self.proc.wait(timeout=2.0)
                except Exception:
                    try:
                        self.proc.kill()
                    except Exception:
                        pass
                self.proc = None
            self._is_ready = False

    def _send_command(self, req: Dict[str, Any], timeout: float = 120.0) -> Dict[str, Any]:
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                exit_code = self.proc.poll() if self.proc else None
                self.proc = None
                self._is_ready = False
                self._crash_count += 1
                if self._crash_count <= self._max_crashes:
                    logger.warning(f"[VieNeu Client] Worker process was dead (exit code {exit_code}). Attempting restart ({self._crash_count}/{self._max_crashes})...")
                    if not self.start_worker():
                        raise VieNeuWorkerCrashError("Worker crashed and failed to restart")
                else:
                    raise VieNeuWorkerCrashError(f"Worker crashed {self._crash_count} times, exceeding limit")

            self._req_counter += 1
            req_id = self._req_counter
            req["req_id"] = req_id

            msg_str = json.dumps(req, ensure_ascii=False) + "\n"
            try:
                self.proc.stdin.write(msg_str)
                self.proc.stdin.flush()
            except Exception as io_err:
                self.proc = None
                self._is_ready = False
                raise VieNeuWorkerCrashError(f"Broken pipe communicating with worker: {io_err}")

            # Read response
            resp_line = self.proc.stdout.readline()
            if not resp_line:
                exit_code = self.proc.poll()
                self.proc = None
                self._is_ready = False
                raise VieNeuWorkerCrashError(f"Worker exited unexpectedly while awaiting response (exit code {exit_code})")

            return json.loads(resp_line)

    def request_yield(self):
        """Called by GPU coordinator to request that this worker pause and release GPU."""
        self._yield_requested = True

    def reset_yield(self):
        self._yield_requested = False

    def should_yield(self) -> bool:
        return self._yield_requested

    def load_model(self, max_batch_size: int = 32, dtype: str = "bfloat16") -> Dict[str, Any]:
        if not self._is_ready:
            if not self.start_worker():
                raise RuntimeError("Could not start GPU worker")
        return self._send_command({"cmd": "load_model", "max_batch_size": max_batch_size, "dtype": dtype})

    def unload_model(self) -> Dict[str, Any]:
        if self._is_ready and self.proc and self.proc.poll() is None:
            return self._send_command({"cmd": "unload_model"})
        return {"status": "ok", "message": "not running"}

    def enroll_voice(self, voice_key: str, ref_audio: str, denoise: bool = True) -> Dict[str, Any]:
        if not self._is_ready:
            if not self.start_worker():
                raise RuntimeError("Could not start GPU worker")
        return self._send_command({
            "cmd": "enroll_voice",
            "voice_key": voice_key,
            "ref_audio": ref_audio,
            "denoise": denoise
        })

    def synthesize_batch(
        self,
        items: List[Dict[str, Any]],
        voice_id: str = "local_ngoc_huyen",
        speed: float = 1.0,
        batch_size: int = 8,
        target_sample_rate: int = 48000,
        target_channels: int = 1,
        ref_audio: Optional[str] = None,
        cancel_token: Optional[Callable[[], bool]] = None
    ) -> List[Dict[str, Any]]:
        """
        Synthesizes a list of items using infer_batch on the resident GPU model.
        Returns list of result dicts mapped 1:1 with item IDs.
        """
        if not items:
            return []

        if cancel_token and cancel_token():
            return [{"id": it["id"], "error": "Cancelled", "success": False} for it in items]

        if not self._is_ready:
            if not self.start_worker():
                raise RuntimeError("Cannot start VieNeu GPU worker")

        req = {
            "cmd": "synthesize_batch",
            "items": items,
            "voice_id": voice_id,
            "speed": float(speed),
            "batch_size": int(batch_size),
            "target_sample_rate": int(target_sample_rate),
            "target_channels": int(target_channels),
            "ref_audio": ref_audio
        }

        resp = self._send_command(req, timeout=300.0)
        if resp.get("status") == "ok":
            return resp.get("results", [])
        else:
            err = resp.get("error", "Unknown worker error")
            return [{"id": it["id"], "error": err, "success": False} for it in items]

    def get_handshake_info(self) -> Dict[str, Any]:
        return dict(self._handshake_data)


_CLIENT_INSTANCE: Optional[VieNeuWorkerClient] = None
_CLIENT_LOCK = threading.Lock()

def get_voice_worker_client() -> VieNeuWorkerClient:
    global _CLIENT_INSTANCE
    if _CLIENT_INSTANCE is None:
        with _CLIENT_LOCK:
            if _CLIENT_INSTANCE is None:
                _CLIENT_INSTANCE = VieNeuWorkerClient()
    return _CLIENT_INSTANCE
