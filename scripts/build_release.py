# -*- coding: utf-8 -*-
"""
NovaCut - Automated Release & Anti-Crack Build Pipeline
Đóng gói bản phát hành tự động, mã hóa Prompt, biên dịch mã nguồn C-binary (.pyd) và tạo file NovaCut.exe
"""

import os
import sys
import shutil
import zipfile
import subprocess
import compileall

import json

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RELEASE_BASE = os.path.join(ROOT_DIR, "release")
RELEASE_DIR = os.path.join(RELEASE_BASE, "NovaCut")

def get_app_version():
    vfile = os.path.join(ROOT_DIR, "version.json")
    if os.path.exists(vfile):
        try:
            with open(vfile, "r", encoding="utf-8") as f:
                return str(json.load(f).get("version", "1.0.7")).strip()
        except Exception:
            pass
    return "1.0.7"

APP_VERSION = get_app_version()

# Danh sách các file / thư mục cần đóng gói vào bản phát hành
INCLUDE_DIRS = [
    "web",
    "resources",
    "routes",
    "bin",
    "models",
    "voices",
    "backgroundmusic"
]

INCLUDE_FILES = [
    "web_app.py",
    "auto_edit_pipeline.py",
    "ai_dubbing.py",
    "license_manager.py",
    "updater.py",
    "prompt_vault.py",
    "asr_manager.py",
    "asr_inference.py",
    "capcut_sync.py",
    "downloader.py",
    "ffmpeg_installer.py",
    "ocr_module.py",
    "custom_voices.py",
    "custom_voices.json",
    "review_phim.py",
    "review_styles.py",
    "batch_queue_manager.py",
    "timeline_sanitizer.py",
    "vietnamese_text_normalizer.py",
    "local_voice_engine.py",
    "rvc_bridge.py",
    "audio_separator.py",
    "mdx_separator.py",
    "custom_pronunciations.json",
    "douyin_browser_downloader.py",
    "tts_cli.py",
    "requirements.txt",
    "version.json",
    "LICENSE_DISCLAIMER.txt",
    "google_apps_script_template.js",
    "google_apps_script_loader.js"
]

# Các file / thư mục tuyệt đối KHÔNG đưa vào bản phát hành (Bảo mật thông tin)
EXCLUDE_PATTERNS = [
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
    ".license.dat",
    ".processed_txs.dat",
    ".token_quota.dat",
    "api_keys.txt",
    "license_config.json",
    "prompt_script.txt",
    "prompt_json.txt",
    "prompt_narration.txt",
    "prompt_dich_phu_de.txt",
    "prompt_clean_srt.txt",
    "prompts",
    "projects",
    "movies",
    "downloads",
    "outputs",
    "output",
    "build",
    "dist",
    "release",
    "patches",
    ".system_generated",
    "*.log"
]


def log(msg):
    print(f"[BUILD] {msg}")


def clean_release_dir():
    """Dọn dẹp thư mục release cũ."""
    log(f"Dang don dep thu muc release: {RELEASE_DIR}...")
    if os.path.exists(RELEASE_DIR):
        shutil.rmtree(RELEASE_DIR, ignore_errors=True)
    os.makedirs(RELEASE_DIR, exist_ok=True)


def copy_project_assets():
    """Sao chép các file và thư mục cần thiết sang thư mục release."""
    log("Dang sao chep tai nguyen va ma nguon...")
    
    # 1. Sao chép thư mục
    for d in INCLUDE_DIRS:
        src = os.path.join(ROOT_DIR, d)
        dst = os.path.join(RELEASE_DIR, d)
        if os.path.exists(src):
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                "__pycache__", "*.pyc", "*.log", ".git", "outputs", "tts_cache", "samples/*"
            ))
            log(f" -> Thu muc: {d}")

    # 2. Sao chép file đơn lẻ
    for f in INCLUDE_FILES:
        src = os.path.join(ROOT_DIR, f)
        dst = os.path.join(RELEASE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, dst)
            log(f" -> File: {f}")


def compile_encrypted_prompts():
    """Mã hóa toàn bộ Prompt AI vào .prompt_vault.dat và xóa sạch file .txt thô trong release."""
    log("Dang ma hoa toan bo AI Prompt vao .prompt_vault.dat...")
    sys.path.insert(0, ROOT_DIR)
    import prompt_vault
    vault_dest = os.path.join(RELEASE_DIR, ".prompt_vault.dat")
    prompt_vault.compile_prompt_vault(output_path=vault_dest)
    log(f" -> Da tao .prompt_vault.dat thanh cong ({os.path.getsize(vault_dest)} bytes)!")


def try_cython_compilation():
    """
    Biên dịch các module Python nhạy cảm thành file nhị phân C (.pyd trên Windows).
    Nếu máy có C compiler (MSVC), các file .py sẽ được thay thế hoàn toàn bằng .pyd!
    """
    log("Kiem tra kha nang bien dich C-binary (Cython / MSVC)...")
    try:
        import Cython
        from setuptools import setup, Extension
        from Cython.Build import cythonize

        sensitive_modules = [
            "license_manager.py",
            "updater.py",
            "prompt_vault.py",
            "auto_edit_pipeline.py",
            "ai_dubbing.py"
        ]

        for mod in sensitive_modules:
            src = os.path.join(RELEASE_DIR, mod)
            if not os.path.exists(src):
                continue
            
            log(f" -> Dang bien dich {mod} sang C-binary (.pyd)...")
            mod_name = os.path.splitext(mod)[0]
            setup_script = f"""
from setuptools import setup
from Cython.Build import cythonize
import sys

setup(
    ext_modules=cythonize("{src.replace(chr(92), '/')}", compiler_directives={{'language_level': "3"}}),
    script_args=["build_ext", "--inplace"]
)
"""
            temp_setup = os.path.join(RELEASE_DIR, "_temp_setup.py")
            with open(temp_setup, "w", encoding="utf-8") as f:
                f.write(setup_script)

            res = subprocess.run([sys.executable, temp_setup], cwd=RELEASE_DIR, capture_output=True, text=True)
            if os.path.exists(temp_setup):
                os.remove(temp_setup)

            # Kiểm tra xem file .pyd đã được tạo chưa
            pyd_files = [f for f in os.listdir(RELEASE_DIR) if f.startswith(mod_name) and f.endswith(".pyd")]
            if pyd_files:
                if os.path.exists(src):
                    os.remove(src)
                c_file = os.path.join(RELEASE_DIR, f"{mod_name}.c")
                if os.path.exists(c_file):
                    os.remove(c_file)
                log(f" [SUCCESS] Da bien dich thanh cong {mod} -> {pyd_files[0]}!")
            else:
                log(f" [INFO] Bo qua Cython C-binary cho {mod} (se su dung toi uu bytecode .pyc)")

        # Dọn dẹp thư mục build tạm
        build_tmp = os.path.join(RELEASE_DIR, "build")
        if os.path.exists(build_tmp):
            shutil.rmtree(build_tmp, ignore_errors=True)
    except Exception as e:
        log(f" [INFO] Cython build info: {e}")


def create_license_bootstrap_config():
    """Tạo resource tối thiểu để EXE mới cài vẫn kết nối được License Server."""
    source_path = os.path.join(ROOT_DIR, 'license_config.json')
    if not os.path.exists(source_path):
        raise RuntimeError('Thiếu license_config.json: không thể tạo bản phát hành có đồng bộ bản quyền.')

    try:
        with open(source_path, 'r', encoding='utf-8') as handle:
            source_config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f'Không đọc được license_config.json: {exc}') from exc

    bootstrap = {
        key: str(source_config.get(key, '')).strip()
        for key in ('google_apps_script_url', 'client_license_token')
    }
    if not all(bootstrap.values()):
        raise RuntimeError('license_config.json thiếu google_apps_script_url hoặc client_license_token.')

    # PyInstaller giữ nguyên tên tệp nguồn khi ``--add-data`` trỏ tới một
    # thư mục đích. Dùng đúng tên mà license_manager.py sẽ đọc trong
    # ``sys._MEIPASS`` thay vì tạo một thư mục tên ``license_bootstrap.json``.
    bootstrap_path = os.path.join(RELEASE_DIR, 'license_bootstrap.json')
    with open(bootstrap_path, 'w', encoding='utf-8') as handle:
        json.dump(bootstrap, handle, ensure_ascii=False)
    return bootstrap_path


def build_pyinstaller_exe():
    """Tạo file chạy NovaCut.exe bằng PyInstaller với Icon thương hiệu và ẩn console."""
    log("Dang tao file thuc thi NovaCut.exe qua PyInstaller...")
    launcher_src = os.path.join(ROOT_DIR, "scripts", "launcher.py")
    ico_path = os.path.join(ROOT_DIR, "resources", "icon.ico")
    
    sea_g2p_bin = os.path.join(ROOT_DIR, "models", "vieneu", "sea_g2p.bin")
    add_data_args = []
    if os.path.exists(sea_g2p_bin):
        add_data_args.append(f"--add-data={sea_g2p_bin}{os.pathsep}sea_g2p")
    bootstrap_path = create_license_bootstrap_config()
    add_data_args.append(f"--add-data={bootstrap_path}{os.pathsep}.")

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--icon={ico_path}",
    ] + add_data_args + [
        "--collect-all=rapidocr_onnxruntime",
        "--collect-all=onnxruntime",
        "--collect-all=vieneu",
        "--collect-all=vieneu_utils",
        "--collect-all=sea_g2p",
        "--collect-all=soxr",
        "--collect-all=kaldi_native_fbank",
        "--collect-all=soundfile",
        "--collect-all=tiktoken",
        "--collect-all=tiktoken_ext",
        "--hidden-import=review_styles",
        "--hidden-import=batch_queue_manager",
        "--hidden-import=routes.batch_queue",
        "--hidden-import=local_voice_engine",
        "--hidden-import=mdx_separator",
        "--hidden-import=audio_separator",
        "--hidden-import=routes.audio",
        "--hidden-import=routes.tts",
        "--hidden-import=routes.video_edit",
        "--hidden-import=routes.updater",
        "--hidden-import=routes.douyin",
        "--hidden-import=routes.projects",
        "--hidden-import=routes.license",
        "--hidden-import=routes.ocr",
        "--hidden-import=routes.asr",
        "--hidden-import=routes.downloader",
        "--hidden-import=routes.auto_edit",
        "--exclude-module=torch",
        "--exclude-module=torchaudio",
        "--exclude-module=torchvision",
        "--exclude-module=transformers",
        "--exclude-module=scipy",
        "--exclude-module=matplotlib",
        "--name=NovaCut",
        launcher_src
    ]
    
    try:
        res = subprocess.run(cmd, cwd=ROOT_DIR, capture_output=True, text=True)
    finally:
        if os.path.exists(bootstrap_path):
            os.remove(bootstrap_path)
    dist_novacut = os.path.join(ROOT_DIR, "dist", "NovaCut")
    
    if os.path.exists(dist_novacut):
        bootstrap_dest = os.path.join(dist_novacut, "_internal", "license_bootstrap.json")
        if not os.path.exists(bootstrap_dest):
            raise RuntimeError("PyInstaller không đóng gói license_bootstrap.json vào bản phát hành.")
        try:
            with open(bootstrap_dest, 'r', encoding='utf-8') as handle:
                bootstrap_data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"license_bootstrap.json trong bản phát hành không hợp lệ: {exc}") from exc
        expected_bootstrap_keys = {"google_apps_script_url", "client_license_token"}
        if set(bootstrap_data) != expected_bootstrap_keys or not all(str(bootstrap_data[key]).strip() for key in expected_bootstrap_keys):
            raise RuntimeError("license_bootstrap.json phải chỉ chứa URL và client_license_token hợp lệ.")
        log(" [ASSERTION PASS] license_bootstrap.json contains only required client configuration.")

        # Post-Build Assertion: Đảm bảo sea_g2p.bin đã được đóng gói chính xác
        sea_dest = os.path.join(dist_novacut, "_internal", "sea_g2p", "sea_g2p.bin")
        if not os.path.exists(sea_dest) or os.path.getsize(sea_dest) < 10 * 1024 * 1024:
            if os.path.exists(sea_g2p_bin):
                os.makedirs(os.path.dirname(sea_dest), exist_ok=True)
                shutil.copy2(sea_g2p_bin, sea_dest)
                log(f" [ASSERTION] Da sao chep sea_g2p.bin ({os.path.getsize(sea_dest):,} bytes) vao _internal/sea_g2p/")
        else:
            log(f" [ASSERTION PASS] sea_g2p.bin ton tai dung chuan ({os.path.getsize(sea_dest):,} bytes) trong bundle.")

        log(" -> Dang tich hop runtime PyInstaller vao thu muc release...")
        for item in os.listdir(dist_novacut):
            s = os.path.join(dist_novacut, item)
            d = os.path.join(RELEASE_DIR, item)
            if os.path.isdir(s):
                shutil.copytree(s, d, dirs_exist_ok=True)
            else:
                shutil.copy2(s, d)
        
        # Dọn dẹp thư mục tạm của PyInstaller ở root
        for tmp in ["build", "dist", "NovaCut.spec"]:
            p = os.path.join(ROOT_DIR, tmp)
            if os.path.exists(p):
                if os.path.isdir(p):
                    shutil.rmtree(p, ignore_errors=True)
                else:
                    os.remove(p)
                    
        exe_path = os.path.join(RELEASE_DIR, "NovaCut.exe")
        if os.path.exists(exe_path):
            log(f" [SUCCESS] Da tao thanh cong file thuc thi: {exe_path}!")
    else:
        log(" [INFO] PyInstaller skipped or failed, fallback to direct python execution.")


def optimize_bytecode():
    """Biên dịch tối ưu toàn bộ Python bytecode (.pyc) và loại bỏ file thừa."""
    log("Dang toi uu hoa bytecode (.pyc)...")
    compileall.compile_dir(RELEASE_DIR, force=True, quiet=1)


def build_inno_setup_installer():
    """Tạo bộ cài đặt chuyên nghiệp NovaCut_Setup_v1.0.0.exe qua Inno Setup."""
    log("Dang bien dich bo cai dat 1-Click: NovaCut_Setup_v1.0.0.exe qua Inno Setup...")
    iss_file = os.path.join(ROOT_DIR, "scripts", "installer.iss")
    
    iscc_candidates = [
        r"C:\Users\hoang\AppData\Local\Programs\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        shutil.which("ISCC"),
        shutil.which("iscc")
    ]
    iscc_bin = None
    for p in iscc_candidates:
        if p and os.path.exists(p):
            iscc_bin = p
            break
            
    if iscc_bin and os.path.exists(iss_file):
        cmd = [iscc_bin, f"/DMyAppVersion={APP_VERSION}", iss_file]
        res = subprocess.run(cmd, cwd=os.path.dirname(iss_file), capture_output=True, text=True)
        setup_exe = os.path.join(RELEASE_BASE, f"NovaCut_Setup_v{APP_VERSION}.exe")
        if os.path.exists(setup_exe):
            log(f" [SUCCESS] Da tao thanh cong bo cai dat 1-Click: {setup_exe} ({os.path.getsize(setup_exe):,} bytes)!")
            return setup_exe
        else:
            log(f" [ERROR] Inno Setup compiler output:\n{res.stderr or res.stdout}")
    else:
        log(" [WARNING] Khong tim thay ISCC.exe hoac scripts/installer.iss.")
    return None


def create_portable_zip():
    """Nén toàn bộ thư mục release/NovaCut thành NovaCut_v1.0.0_Portable.zip"""
    zip_path = os.path.join(RELEASE_BASE, f"NovaCut_v{APP_VERSION}_Portable.zip")
    log(f"Dang nen ban Portable: {zip_path}...")
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(RELEASE_DIR):
            for file in files:
                abs_p = os.path.join(root, file)
                rel_p = os.path.relpath(abs_p, RELEASE_BASE)
                zf.write(abs_p, rel_p)
    if os.path.exists(zip_path):
        log(f" [SUCCESS] Da tao thanh cong goi Portable: {zip_path} ({os.path.getsize(zip_path):,} bytes)!")
    return zip_path


def main():
    log("=" * 60)
    log(f"BAT DAU QUY TRINH DONG GOI RELEASE CHO NOVACUT (v{APP_VERSION})")
    log("=" * 60)
    
    clean_release_dir()
    copy_project_assets()
    compile_encrypted_prompts()
    try_cython_compilation()
    build_pyinstaller_exe()
    optimize_bytecode()
    build_inno_setup_installer()
    create_portable_zip()
    
    log("=" * 60)
    log("HOAN TAT QUY TRINH DONG GOI RELEASE THANH CONG 100%!")
    log(f" - Thu muc Ung dung       : {RELEASE_DIR}")
    log(f" - File chay chinh         : {os.path.join(RELEASE_DIR, 'NovaCut.exe')}")
    log(f" - Bo Cai Dat 1-Click EXE  : {os.path.join(RELEASE_BASE, f'NovaCut_Setup_v{APP_VERSION}.exe')}")
    log("=" * 60)

if __name__ == "__main__":
    main()
