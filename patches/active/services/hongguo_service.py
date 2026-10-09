# -*- coding: utf-8 -*-
"""
services/hongguo_service.py
Quản lý vòng đời tiến trình dịch vụ nền Hongguo Downloader (Unidbg Signer & FastAPI Server).
Tích hợp Win32 Job Object, CREATE_NO_WINDOW, kiểm tra cổng động và dọn dẹp an toàn khi thoát.
"""

import os
import sys
import time
import socket
import logging
import ctypes
import atexit
import threading
import subprocess
import json
from typing import Optional, Tuple, Dict, Any, List
import requests

logger = logging.getLogger("HongguoService")
logger.setLevel(logging.INFO)

# Win32 Constants
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JobObjectExtendedLimitInformation = 9
PROCESS_ALL_ACCESS = 0x1F0FFF
CREATE_NO_WINDOW = 0x08000000
CREATE_NEW_PROCESS_GROUP = 0x00000200

if os.name == "nt":
    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryLimit", ctypes.c_size_t),
            ("PeakJobMemoryLimit", ctypes.c_size_t),
        ]


def port_is_open(port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
    """Kiểm tra xem cổng TCP có đang mở (đang lắng nghe) hay không."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def port_is_bindable(port: int, host: str = "127.0.0.1") -> bool:
    """Kiểm tra xem cổng TCP có thể bind được (cổng rỗng chưa ai chiếm) hay không."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind((host, port))
        s.close()
        return True
    except Exception:
        return False


def select_available_port(default_port: int, candidate_ports: List[int], host: str = "127.0.0.1") -> int:
    """Chọn cổng mặc định nếu bindable, hoặc quét danh sách dự phòng, hoặc gán cổng ngẫu nhiên của OS."""
    if port_is_bindable(default_port, host):
        return default_port
    for p in candidate_ports:
        if port_is_bindable(p, host):
            return p
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    free_port = s.getsockname()[1]
    s.close()
    return free_port


class HongguoServiceManager:
    """
    Quản lý tập trung tiến trình Hongguo Downloader nền.
    Singleton giám sát Unidbg Signer (:9099) và FastAPI Server (:8000).
    """

    DEFAULT_SIGN_CANDIDATES = [9099, 8766, 8765, 9599, 9088, 9090, 19099]
    DEFAULT_SERVER_CANDIDATES = [8000, 8088, 8090, 8888, 8008, 8080, 18000]

    @classmethod
    def resolve_output_dir(cls, tool_dir: Optional[str] = None) -> str:
        """
        Xác định thư mục lưu trữ video Hồng Quả theo thứ tự ưu tiên:
        1. Biến môi trường HG_OUT (nếu có, không rỗng và tồn tại)
        2. Cấu hình người dùng trong dlconfig.json (%LOCALAPPDATA%\\HongguoDownloader\\dlconfig.json)
        3. Cấu hình dlconfig.json trong thư mục công cụ tool_dir nếu có
        4. Thư mục ~/Videos/Hongguo
        5. Thư mục downloads trong tool_dir
        """
        # 1. HG_OUT
        env_out = os.environ.get("HG_OUT")
        if env_out and str(env_out).strip():
            env_path = os.path.abspath(str(env_out).strip())
            if os.path.isdir(env_path):
                return env_path

        # 2. dlconfig.json trong AppData
        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        dlcfg_path = os.path.join(local_appdata, "HongguoDownloader", "dlconfig.json")
        if os.path.isfile(dlcfg_path):
            try:
                with open(dlcfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    cfg_out = cfg_data.get("output_dir")
                    if cfg_out and str(cfg_out).strip():
                        cfg_abs = os.path.abspath(str(cfg_out).strip())
                        if os.path.isdir(cfg_abs):
                            return cfg_abs
            except Exception as e:
                logger.warning(f"[HongguoService] Could not read {dlcfg_path}: {e}")

        # 3. dlconfig.json trong tool_dir
        if tool_dir and os.path.isdir(tool_dir):
            for candidate_cfg in (
                os.path.join(tool_dir, "dlconfig.json"),
                os.path.join(tool_dir, "app", "dlconfig.json")
            ):
                if os.path.isfile(candidate_cfg):
                    try:
                        with open(candidate_cfg, "r", encoding="utf-8") as f:
                            cfg_data = json.load(f)
                            cfg_out = cfg_data.get("output_dir")
                            if cfg_out and str(cfg_out).strip():
                                cfg_abs = os.path.abspath(str(cfg_out).strip())
                                if os.path.isdir(cfg_abs):
                                    return cfg_abs
                    except Exception:
                        pass

        # 4. Videos/Hongguo
        vids_hongguo = os.path.abspath(os.path.expanduser(r"~\Videos\Hongguo"))
        if os.path.isdir(vids_hongguo):
            return vids_hongguo

        # 5. tool_dir/downloads
        if tool_dir and os.path.isdir(tool_dir):
            downloads_dir = os.path.abspath(os.path.join(tool_dir, "downloads"))
            if os.path.isdir(downloads_dir):
                return downloads_dir

        return vids_hongguo

    def get_candidate_output_roots(self) -> List[str]:
        """
        Lấy danh sách tất cả các thư mục gốc lưu trữ phim hợp lệ để quét thư viện và kiểm tra bảo mật.
        """
        candidates: List[str] = []
        cur_out = self.resolve_output_dir(self._tool_dir)
        if cur_out:
            candidates.append(cur_out)

        local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser(r"~\AppData\Local")
        dlcfg_path = os.path.join(local_appdata, "HongguoDownloader", "dlconfig.json")
        if os.path.isfile(dlcfg_path):
            try:
                with open(dlcfg_path, "r", encoding="utf-8") as f:
                    cfg_data = json.load(f)
                    cfg_out = cfg_data.get("output_dir")
                    if cfg_out and str(cfg_out).strip():
                        candidates.append(str(cfg_out).strip())
            except Exception:
                pass

        env_out = os.environ.get("HG_OUT")
        if env_out and str(env_out).strip():
            candidates.append(str(env_out).strip())

        candidates.append(os.path.expanduser(r"~\Videos\Hongguo"))
        if self._tool_dir:
            candidates.append(os.path.join(self._tool_dir, "downloads"))

        seen = set()
        unique: List[str] = []
        for c in candidates:
            if not c:
                continue
            norm = os.path.normpath(os.path.abspath(c))
            norm_key = os.path.normcase(norm)
            if norm_key not in seen:
                seen.add(norm_key)
                unique.append(norm)
        return unique

    def __init__(self, tool_dir: Optional[str] = None, override_tool_dir: Optional[str] = None):
        self._lock = threading.RLock()
        self._override_tool_dir = override_tool_dir or tool_dir
        self._job_handle = None
        self._procs: List[subprocess.Popen] = []

        self.signer_port: int = int(os.environ.get("HG_SIGN_PORT", 9099))
        self.server_port: int = int(os.environ.get("HG_PORT", 8000))
        self.output_dir: str = self.resolve_output_dir(self._override_tool_dir or tool_dir)
        self._output_dir_cached = self.output_dir

        # Phát hiện và xác thực môi trường tool
        self._installed = False
        self._tool_dir = ""
        self._java_path = ""
        self._python_path = ""
        self._signer_jar = ""
        self._server_script = ""
        self._validation_details: Dict[str, Any] = {}

        self.refresh_installation()

    def is_installed(self) -> bool:
        """Kiểm tra xem thư mục Hongguo Downloader có tồn tại và hợp lệ hay không."""
        with self._lock:
            target_dir = self._override_tool_dir if self._override_tool_dir else (self._tool_dir or r"D:\Tool\Hongguo Downloader")
            if not os.path.isdir(target_dir):
                self._installed = False
                return False
            self.refresh_installation()
            return self._installed

    def refresh_installation(self) -> bool:
        """Quét và xác nhận sự tồn tại của thư mục công cụ Hongguo."""
        with self._lock:
            ok, tool_dir, details = self.detect_installation(self._override_tool_dir)
            self._installed = ok
            self._tool_dir = tool_dir
            self._java_path = details.get("java_path") or ""
            self._python_path = details.get("python_path") or ""
            self._signer_jar = details.get("signer_jar") or ""
            self._server_script = details.get("server_script") or ""
            self._validation_details = details
            return ok

    @classmethod
    def _validate_tool_dir(cls, c_dir: str) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Kiểm tra tính toàn vẹn của các tệp thực thi cốt lõi trong một thư mục chỉ định.
        Trả về (ok, c_dir_abs, details).
        """
        c_dir_abs = os.path.abspath(c_dir)
        # 1. Kiểm tra JRE
        java_path = os.path.join(c_dir_abs, "jre", "bin", "java.exe")
        if not os.path.isfile(java_path):
            java_path = os.path.join(c_dir_abs, "bin", "java.exe")

        # 2. Kiểm tra Python nội bộ
        python_path = os.path.join(c_dir_abs, "python", "python.exe")

        # 3. Kiểm tra Unidbg Signer JAR
        signer_jar = os.path.join(c_dir_abs, "app", "sign", "unidbg-sign.jar")

        # 4. Kiểm tra Server script (server_ext.py hoặc bytecode server.pyc)
        app_dir = os.path.join(c_dir_abs, "app")
        server_script = ""
        for s_name in ("server_ext.py", "server_ext.pyc", "server.pyc", "server.py"):
            candidate_script = os.path.join(app_dir, s_name)
            if os.path.isfile(candidate_script):
                server_script = candidate_script
                break

        missing = []
        if not os.path.isfile(java_path):
            missing.append("jre/bin/java.exe")
        if not os.path.isfile(python_path):
            missing.append("python/python.exe")
        if not os.path.isfile(signer_jar):
            missing.append("app/sign/unidbg-sign.jar")
        if not server_script:
            missing.append("app/server_ext.py (or server.pyc)")

        details = {
            "tool_dir": c_dir_abs,
            "java_path": java_path if os.path.isfile(java_path) else None,
            "python_path": python_path if os.path.isfile(python_path) else None,
            "signer_jar": signer_jar if os.path.isfile(signer_jar) else None,
            "server_script": server_script if server_script else None,
            "missing": missing
        }

        return (len(missing) == 0), c_dir_abs, details

    @classmethod
    def detect_installation(cls, override_path: Optional[str] = None) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Tìm và kiểm tra tính toàn vẹn của thư mục Hongguo Downloader:
        - Nếu override_path được cung cấp rõ ràng: CHỈ kiểm tra duy nhất đường dẫn này.
          Tuyệt đối KHÔNG tự ý fallback sang các ứng viên mặc định khác.
          Nếu thư mục không tồn tại hoặc thiếu tệp, trả về (False, target, details) kèm lỗi.
        - Nếu override_path là None hoặc rỗng: Quét danh sách ứng viên mặc định theo thứ tự:
          1. HONGGUO_DIR environment variable
          2. D:\\Tool\\Hongguo Downloader
          3. ../Hongguo Downloader (thư mục ngang cấp với NovaCut)
          4. C:\\Tool\\Hongguo Downloader
        """
        if override_path and str(override_path).strip():
            target_path = os.path.abspath(str(override_path).strip())
            if not os.path.isdir(target_path):
                return False, target_path, {
                    "tool_dir": target_path,
                    "java_path": None,
                    "python_path": None,
                    "signer_jar": None,
                    "server_script": None,
                    "missing": ["tool_dir_not_found"],
                    "error": f"Thư mục công cụ chỉ định không tồn tại: {target_path}"
                }
            return cls._validate_tool_dir(target_path)

        # Chế độ Auto-Discovery khi không có override_path
        candidates = []
        env_dir = os.environ.get("HONGGUO_DIR")
        if env_dir and env_dir.strip():
            candidates.append(os.path.abspath(env_dir.strip()))
        candidates.append(r"D:\Tool\Hongguo Downloader")

        try:
            from web_app import ROOT_DIR
            candidates.append(os.path.abspath(os.path.join(ROOT_DIR, "..", "Hongguo Downloader")))
        except Exception:
            candidates.append(os.path.abspath(os.path.join(os.getcwd(), "..", "Hongguo Downloader")))

        candidates.append(r"C:\Tool\Hongguo Downloader")

        first_failed_details = None
        first_failed_dir = ""

        for c_dir in candidates:
            if not os.path.isdir(c_dir):
                continue

            ok, validated_dir, details = cls._validate_tool_dir(c_dir)
            if ok:
                return True, validated_dir, details
            elif first_failed_details is None:
                first_failed_details = details
                first_failed_dir = validated_dir

        if first_failed_details is not None:
            return False, first_failed_dir, first_failed_details

        return False, "", {"tool_dir": None, "missing": ["tool_dir_not_found"]}

    def verify_runtime(self) -> Tuple[bool, str]:
        """
        Xác thực sự hiện diện của các tệp thực thi cốt lõi (JRE, Python, Signer JAR, Server script).
        Trả về (True, "") nếu đầy đủ, hoặc (False, error_msg) nếu thiếu.
        """
        tool_dir = self._override_tool_dir if self._override_tool_dir else (self._tool_dir or r"D:\Tool\Hongguo Downloader")
        if not os.path.exists(tool_dir):
            return False, f"Thư mục công cụ không tồn tại: {tool_dir} (tool directory not found)"

        # 1. Java executable
        java_path = os.path.join(tool_dir, "jre", "bin", "java.exe")
        if not os.path.exists(java_path):
            java_path = os.path.join(tool_dir, "bin", "java.exe")
        if not os.path.exists(java_path):
            return False, f"Không tìm thấy máy ảo Java (java.exe missing) tại {tool_dir}"

        # 2. Python executable
        python_path = os.path.join(tool_dir, "python", "python.exe")
        if not os.path.exists(python_path):
            return False, f"Không tìm thấy Python nội bộ (python.exe missing) tại {tool_dir}"

        # 3. Unidbg Signer JAR
        signer_jar = os.path.join(tool_dir, "app", "sign", "unidbg-sign.jar")
        if not os.path.exists(signer_jar):
            return False, f"Không tìm thấy Unidbg Signer JAR (unidbg-sign.jar missing) tại {tool_dir}"

        # 4. Server script
        server_found = False
        app_dir = os.path.join(tool_dir, "app")
        for s_name in ("server_ext.py", "server_ext.pyc", "server.pyc", "server.py"):
            candidate = os.path.join(app_dir, s_name)
            if os.path.exists(candidate):
                server_found = True
                break
        if not server_found:
            return False, f"Không tìm thấy mã nguồn máy chủ (server_ext.py missing) tại {app_dir}"

        return True, ""

    def port_open(self, port: int, host: str = "127.0.0.1", timeout: float = 0.3) -> bool:
        """Kiểm tra cổng TCP có đang phản hồi hay không."""
        return port_is_open(port, host=host, timeout=timeout)

    def is_port_bindable(self, port: int, host: str = "127.0.0.1") -> bool:
        """Kiểm tra cổng TCP có bind được hay không."""
        return port_is_bindable(port, host=host)

    def select_port(self, env_var: str, default_port: int, candidate_ports: List[int], host: str = "127.0.0.1") -> int:
        """Chọn cổng từ biến môi trường, mặc định, hoặc danh sách dự phòng."""
        env_val = os.environ.get(env_var)
        if env_val:
            try:
                p_env = int(env_val)
                if self.is_port_bindable(p_env, host):
                    return p_env
            except (ValueError, TypeError):
                pass
        if self.is_port_bindable(default_port, host):
            return default_port
        for p in candidate_ports:
            if self.is_port_bindable(p, host):
                return p
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, 0))
        free_port = s.getsockname()[1]
        s.close()
        return free_port

    def wait_port(self, port: int, timeout: float = 45.0, host: str = "127.0.0.1") -> bool:
        """Chờ cho đến khi cổng TCP mở hoặc hết thời gian timeout."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.port_open(port, host=host):
                return True
            time.sleep(0.3)
        return False

    def _init_job_object(self):
        """Khởi tạo Windows Job Object với cờ tự động kết liễu toàn bộ tiến trình con khi cha đóng."""
        if os.name != "nt":
            return None
        if self._job_handle:
            return self._job_handle

        try:
            k32 = ctypes.windll.kernel32
            h_job = k32.CreateJobObjectW(None, None)
            if not h_job:
                return None

            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

            success = k32.SetInformationJobObject(
                h_job,
                JobObjectExtendedLimitInformation,
                ctypes.byref(info),
                ctypes.sizeof(info)
            )
            if not success:
                k32.CloseHandle(h_job)
                return None

            self._job_handle = h_job
            logger.info("[HongguoService] Initialized Win32 Job Object with KILL_ON_JOB_CLOSE.")
            return self._job_handle
        except Exception as e:
            logger.warning(f"[HongguoService] Could not init Job Object: {e}")
            return None

    def _assign_to_job(self, proc: subprocess.Popen):
        """Gán tiến trình subprocess vừa spawn vào Win32 Job Object."""
        if not self._job_handle or os.name != "nt" or not proc:
            return
        try:
            k32 = ctypes.windll.kernel32
            proc_h = getattr(proc, '_handle', None)
            need_close = False
            if proc_h is None:
                proc_h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
                need_close = True
            else:
                proc_h = int(proc_h)

            if proc_h:
                k32.AssignProcessToJobObject(self._job_handle, proc_h)
                if need_close:
                    k32.CloseHandle(proc_h)
        except Exception as e:
            logger.warning(f"[HongguoService] Error assigning PID {proc.pid} to Job Object: {e}")

    def _spawn(self, cmd: List[str], cwd: str, env: Optional[Dict[str, str]] = None) -> subprocess.Popen:
        """Spawn tiến trình nền ẩn hoàn toàn cửa sổ (CREATE_NO_WINDOW) và gắn vào Job Object."""
        flags = (CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP) if os.name == 'nt' else 0
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env=env,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self._procs.append(proc)
        self._assign_to_job(proc)
        return proc

    def check_signer_health(self) -> bool:
        """Kiểm tra Signer có đang lắng nghe trên cổng hay không."""
        return self.port_open(self.signer_port)

    def check_server_health(self) -> bool:
        """Kiểm tra Server có đang chạy và phản hồi API /dl/status hay không."""
        if not self.port_open(self.server_port):
            return False
        try:
            resp = requests.get(f"http://127.0.0.1:{self.server_port}/dl/status", timeout=1.5)
            if resp.status_code == 200:
                data = resp.json()
                return "running" in data
        except Exception:
            pass
        return False

    def get_status(self) -> Dict[str, Any]:
        """
        Lấy trạng thái tổng quan của hệ thống dịch vụ Hongguo Downloader.
        Tuân thủ Interface Contract quy định trong PROJECT.md.
        """
        with self._lock:
            target_dir = self._override_tool_dir if self._override_tool_dir else (self._tool_dir or r"D:\Tool\Hongguo Downloader")
            if not os.path.isdir(target_dir):
                self._installed = False

            signer_ok = self.check_signer_health()
            server_ok = self.check_server_health()
            self.output_dir = self.resolve_output_dir(self._override_tool_dir or self._tool_dir)

            error_msg = None
            if not self._installed:
                error_msg = "Thư mục Hongguo Downloader không tồn tại hoặc thiếu thành phần (tool directory not found)"
                missing = self._validation_details.get("missing", [])
                if missing:
                    error_msg += f": {', '.join(missing)}"

            return {
                "installed": self._installed,
                "tool_dir": self._tool_dir or target_dir,
                "signer_running": signer_ok,
                "signer_port": self.signer_port,
                "server_running": server_ok,
                "server_port": self.server_port,
                "output_dir": self.output_dir,
                "error": error_msg
            }

    def start_services(self) -> Tuple[bool, str]:
        """
        Khởi động tuần tự Unidbg Signer và Python FastAPI Server nếu chưa chạy.
        Tự động tái sử dụng instance lành mạnh đã chạy sẵn.
        """
        with self._lock:
            if not self._installed:
                self.refresh_installation()

            ok_rt, msg_rt = self.verify_runtime()
            if not ok_rt:
                return False, f"Lỗi xác thực môi trường Hongguo Downloader: {msg_rt}"

            self.output_dir = self.resolve_output_dir(self._override_tool_dir or self._tool_dir)
            self._init_job_object()
            try:
                os.makedirs(self.output_dir, exist_ok=True)
            except Exception:
                pass

            p_sign = None
            # 1. Quản lý Signer
            if self.check_signer_health():
                logger.info(f"[HongguoService] Signer already healthy on port :{self.signer_port}")
            else:
                if not self.is_port_bindable(self.signer_port):
                    self.signer_port = self.select_port(
                        "HG_SIGN_PORT", 9099, self.DEFAULT_SIGN_CANDIDATES
                    )

                target_tool = self._override_tool_dir if self._override_tool_dir else (self._tool_dir or r"D:\Tool\Hongguo Downloader")
                sign_cwd = os.path.join(target_tool, "app", "sign")
                java_bin = self._java_path or os.path.join(sign_cwd, "..", "..", "jre", "bin", "java.exe")
                cmd_sign = [
                    java_bin,
                    "-Xmx1024m",
                    "-XX:+ExitOnOutOfMemoryError",
                    "--add-opens",
                    "java.base/java.lang=ALL-UNNAMED",
                    "-cp",
                    "unidbg-sign.jar",
                    "com.hongguo.sign.FqTrace",
                    "serve",
                    str(self.signer_port)
                ]

                env = dict(os.environ)
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"

                logger.info(f"[HongguoService] Spawning Unidbg Signer on port :{self.signer_port}...")
                p_sign = self._spawn(cmd_sign, cwd=sign_cwd, env=env)

                # Chờ signer mở cổng
                started = self.wait_port(self.signer_port, timeout=45.0)
                if not started or (p_sign.poll() is not None):
                    try:
                        p_sign.terminate()
                    except Exception:
                        pass
                    if p_sign in self._procs:
                        self._procs.remove(p_sign)
                    return False, f"Tiến trình Signer (Java) không thể khởi động hoặc thoát sớm trên cổng :{self.signer_port}"

            # 2. Quản lý Server
            if self.check_server_health():
                logger.info(f"[HongguoService] Server already healthy on port :{self.server_port}")
            else:
                if not self.is_port_bindable(self.server_port):
                    self.server_port = self.select_port(
                        "HG_PORT", 8000, self.DEFAULT_SERVER_CANDIDATES
                    )

                target_tool = self._override_tool_dir if self._override_tool_dir else (self._tool_dir or r"D:\Tool\Hongguo Downloader")
                app_cwd = os.path.join(target_tool, "app")
                py_bin = self._python_path or os.path.join(app_cwd, "..", "python", "python.exe")
                srv_script_name = os.path.basename(self._server_script) if self._server_script else "server_ext.py"
                cmd_server = [py_bin, srv_script_name]

                env = dict(os.environ)
                env["PYTHONUTF8"] = "1"
                env["PYTHONIOENCODING"] = "utf-8"
                env["SIGN_SERVER"] = f"http://127.0.0.1:{self.signer_port}"
                env["BIND_HOST"] = "127.0.0.1"
                env["PORT"] = str(self.server_port)
                env["HG_OUT"] = self.output_dir
                env["HG_LICENSE_DISABLED"] = "0"

                logger.info(f"[HongguoService] Spawning Hongguo Server on port :{self.server_port}...")
                p_srv = self._spawn(cmd_server, cwd=app_cwd, env=env)

                # Chờ server phản hồi
                started = self.wait_port(self.server_port, timeout=45.0)
                if not started or (p_srv.poll() is not None):
                    try:
                        p_srv.terminate()
                    except Exception:
                        pass
                    if p_srv in self._procs:
                        self._procs.remove(p_srv)

                    # Dọn dẹp cả signer vừa bật nếu có để tránh orphan
                    if p_sign:
                        try:
                            p_sign.terminate()
                        except Exception:
                            pass
                        if p_sign in self._procs:
                            self._procs.remove(p_sign)

                    return False, f"Tiến trình Server (Python) không thể khởi động hoặc thoát sớm trên cổng :{self.server_port}"

            return True, "Dịch vụ Hongguo Downloader đã khởi động và sẵn sàng"

    def stop_services(self) -> Tuple[bool, str]:
        """Dừng sạch sẽ các tiến trình con được quản lý bởi NovaCut."""
        with self._lock:
            stopped_count = 0
            for proc in self._procs:
                if proc and proc.poll() is None:
                    try:
                        proc.terminate()
                        stopped_count += 1
                    except Exception:
                        pass

            t0 = time.time()
            for proc in self._procs:
                if proc and proc.poll() is None:
                    try:
                        remaining = max(0.1, 3.0 - (time.time() - t0))
                        proc.wait(timeout=remaining)
                    except Exception:
                        try:
                            proc.kill()
                        except Exception:
                            pass

            self._procs.clear()

            if self._job_handle and os.name == 'nt':
                try:
                    ctypes.windll.kernel32.CloseHandle(self._job_handle)
                except Exception:
                    pass
                self._job_handle = None

            logger.info(f"[HongguoService] Stopped {stopped_count} child processes cleanly.")
            return True, "Đã dừng các dịch vụ Hongguo Downloader."

    def forward_request(
        self,
        method: str,
        path: str,
        json_data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        timeout: float = 30.0
    ) -> Tuple[int, Any]:
        """
        Proxy request từ NovaCut backend sang Hongguo FastAPI Server.
        Tự động khởi động dịch vụ nếu chưa chạy.
        """
        if not self.check_server_health():
            ok, msg = self.start_services()
            if not ok:
                return 503, {"success": False, "error": f"Không thể kết nối dịch vụ Hongguo: {msg}"}

        url = f"http://127.0.0.1:{self.server_port}{path}"
        try:
            resp = requests.request(
                method=method.upper(),
                url=url,
                json=json_data,
                params=params,
                timeout=timeout
            )
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.status_code, resp.json()
            return resp.status_code, resp.text
        except requests.Timeout:
            return 504, {"success": False, "error": "Hongguo API timeout"}
        except requests.RequestException as e:
            return 502, {"success": False, "error": f"Lỗi kết nối tới Hongguo server: {str(e)}"}

    @classmethod
    def get_instance(cls) -> "HongguoServiceManager":
        """Lấy thể hiện duy nhất (Singleton)."""
        return get_service_manager()


# Global singleton instance
_manager_instance: Optional[HongguoServiceManager] = None
_manager_lock = threading.Lock()


def get_service_manager() -> HongguoServiceManager:
    """Lấy thể hiện duy nhất của HongguoServiceManager (Singleton)."""
    global _manager_instance
    with _manager_lock:
        if _manager_instance is None:
            _manager_instance = HongguoServiceManager()
        return _manager_instance


# Tự động đăng ký dọn dẹp khi Python thoát
atexit.register(lambda: get_service_manager().stop_services())
