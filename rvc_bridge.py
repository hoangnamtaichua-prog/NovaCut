import os
import sys
import subprocess
import json
import tempfile
import time

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_RVC_DIR = r"D:\Tool\RVC\RVC20260718Nvidia50x0"
DEFAULT_PYTHON = os.path.join(DEFAULT_RVC_DIR, "runtime", "python.exe")

def get_rvc_python():
    if os.path.exists(DEFAULT_PYTHON):
        return DEFAULT_PYTHON
    return sys.executable

def get_rvc_dir():
    return DEFAULT_RVC_DIR if os.path.exists(DEFAULT_RVC_DIR) else ROOT_DIR

def convert_voice(input_audio, output_audio, model_path, index_path=None, pitch=0, f0_method="rmvpe", index_rate=0.45, rms_mix_rate=0.25, protect=0.50):
    """
    Converts input_audio using the specified RVC model and index via the RTX 5060 RVC runtime.
    """
    rvc_dir = get_rvc_dir()
    rvc_python = get_rvc_python()

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Không tìm thấy model RVC: {model_path}")
        
    if not os.path.exists(input_audio):
        raise FileNotFoundError(f"Không tìm thấy file âm thanh đầu vào: {input_audio}")

    # Standardize paths
    input_audio = os.path.abspath(input_audio)
    output_audio = os.path.abspath(output_audio)
    model_path = os.path.abspath(model_path)
    if index_path and os.path.exists(index_path):
        index_path = os.path.abspath(index_path)
    else:
        index_path = ""

    os.makedirs(os.path.dirname(output_audio), exist_ok=True)
    is_mp3 = output_audio.lower().endswith('.mp3')
    intermediate_wav = output_audio if not is_mp3 else output_audio + ".temp_rvc.wav"

    # Prepare an inline script for isolated fast inference
    py_script = f"""
import os
import sys
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import soundfile as sf

sys.stdout.reconfigure(encoding='utf-8')
rvc_dir = r"{rvc_dir}"
os.chdir(rvc_dir)
sys.path.append(rvc_dir)

os.environ.setdefault("weight_root", r"assets/weights")
os.environ.setdefault("weight_pymss_root", r"assets/pymss_weights")
os.environ.setdefault("index_root", r"logs")
os.environ.setdefault("outside_index_root", r"assets/indices")
os.environ.setdefault("rmvpe_root", r"assets/rmvpe")

from configs.config import Config
from infer.vc.modules import VC

config = Config()
vc = VC(config)

model_path = r"{model_path}"
index_path = r"{index_path}"
input_audio = r"{input_audio}"
output_audio = r"{intermediate_wav}"
pitch = int({pitch})
f0_method = "{f0_method}"
index_rate = float({index_rate})
rms_mix_rate = float({rms_mix_rate})
protect = float({protect})

# Load Model
model_name = os.path.basename(model_path)
if not os.path.exists(os.path.join(rvc_dir, "assets", "weights", model_name)):
    os.environ["weight_root"] = os.path.dirname(model_path)

vc.get_vc(model_name)

info, (tgt_sr, audio_opt) = vc.vc_single(
    sid=0,
    input_audio_path=input_audio,
    f0_up_key=pitch,
    f0_method=f0_method,
    file_index=index_path,
    index_rate=index_rate,
    resample_sr=0,
    rms_mix_rate=rms_mix_rate,
    protect=protect
)

if audio_opt is None:
    raise Exception(f"RVC Inference Failed: {{info}}")

# Anti-clipping peak normalization to eliminate crackling/rasping
peak = np.max(np.abs(audio_opt))
if peak > 0.90:
    audio_opt = audio_opt / (peak + 1e-6) * 0.90

sf.write(output_audio, audio_opt, tgt_sr)
print("SUCCESS")
"""

    temp_script = os.path.join(tempfile.gettempdir(), f"rvc_run_{int(time.time()*1000)}.py")
    try:
        with open(temp_script, "w", encoding="utf-8") as f:
            f.write(py_script)

        cmd = [rvc_python, temp_script]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", creationflags=0x08000000 if os.name == 'nt' else 0)

        if proc.returncode != 0 or not os.path.exists(intermediate_wav):
            err_msg = proc.stderr.strip() or proc.stdout.strip()
            raise RuntimeError(f"Lỗi khi chạy RVC inference: {err_msg}")

        # Convert to MP3 if needed
        if is_mp3:
            import ffmpeg_installer
            ff = ffmpeg_installer.ensure_ffmpeg()
            conv_cmd = [ff, '-y', '-i', intermediate_wav, '-ar', '44100', '-b:a', '192k', output_audio]
            subprocess.run(conv_cmd, capture_output=True, check=True, creationflags=0x08000000 if os.name == 'nt' else 0)
            if os.path.exists(intermediate_wav):
                try:
                    os.remove(intermediate_wav)
                except:
                    pass

        return output_audio
    finally:
        if os.path.exists(temp_script):
            try:
                os.remove(temp_script)
            except:
                pass
        if is_mp3 and os.path.exists(intermediate_wav):
            try:
                os.remove(intermediate_wav)
            except:
                pass

if __name__ == "__main__":
    test_in = os.path.join(ROOT_DIR, "sample_hoatngon_diem_trinh.wav")
    test_out = os.path.join(ROOT_DIR, "output", "test_bridge_out.wav")
    m_path = r"D:\Tool\RVC\RVC20260718Nvidia50x0\assets\weights\ngochuyen_reviewphim.pth"
    i_path = r"D:\Tool\RVC\RVC20260718Nvidia50x0\logs\ngochuyen_reviewphim\added_IVF525_Flat_nprobe_1_ngochuyen_reviewphim_v2.index"
    
    print("Testing convert_voice via rvc_bridge...")
    res = convert_voice(test_in, test_out, m_path, i_path, pitch=0)
    print(f"Done! Output: {res}")
