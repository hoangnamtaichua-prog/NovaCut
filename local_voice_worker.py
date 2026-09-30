"""
local_voice_worker.py - Isolated High-Speed VieNeu v3 Turbo GPU Worker
Executes inside the isolated runtimes/vieneu_gpu environment on PyTorch 2.8.0+cu128.
Communicates strictly via JSON Lines protocol on stdin/stdout, logging on stderr.
Maintains a resident PyTorch model in VRAM, supports dynamic batching, clone enroll caching,
graceful unload/reload for multi-task GPU coordination, and auto-fallback batch resizing on OOM.
"""

import os
import sys
import json
import time
import traceback
import gc
from typing import Dict, Any, List, Optional
import numpy as np

# Protocol version
PROTOCOL_VERSION = 1

# Global model state
_TTS_MODEL = None
_TTS_CONFIG = {}
_ENROLLED_VOICES: Dict[str, Dict[str, Any]] = {}


def log_debug(msg: str):
    sys.stderr.write(f"[VieNeu GPU Worker] {msg}\n")
    sys.stderr.flush()


def get_vram_info() -> Dict[str, float]:
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / (1024 * 1024)
            reserved = torch.cuda.memory_reserved() / (1024 * 1024)
            return {"allocated_mb": round(allocated, 2), "reserved_mb": round(reserved, 2)}
    except Exception:
        pass
    return {"allocated_mb": 0.0, "reserved_mb": 0.0}


def handle_handshake(req: Dict[str, Any]) -> Dict[str, Any]:
    import torch
    import vieneu
    import transformers

    cuda_available = torch.cuda.is_available()
    device_name = torch.cuda.get_device_name(0) if cuda_available else "CPU"
    capability = list(torch.cuda.get_device_capability(0)) if cuda_available else [0, 0]

    # Smoke CUDA execution to verify sm_120 kernel execution
    smoke_cuda_ok = False
    if cuda_available:
        try:
            a = torch.randn(64, 64, device="cuda", dtype=torch.float32)
            b = torch.randn(64, 64, device="cuda", dtype=torch.float32)
            c = a @ b
            torch.cuda.synchronize()
            smoke_cuda_ok = bool(c.sum().item() is not None)
        except Exception as e:
            log_debug(f"CUDA Smoke Test failed: {e}")
            smoke_cuda_ok = False

    return {
        "status": "ok",
        "protocol_version": PROTOCOL_VERSION,
        "python": sys.executable,
        "torch_version": torch.__version__,
        "torchaudio_version": getattr(torch, '__torchaudio_version__', 'available'),
        "vieneu_version": getattr(vieneu, '__version__', '3.8.1'),
        "transformers_version": transformers.__version__,
        "cuda_available": cuda_available,
        "smoke_cuda_ok": smoke_cuda_ok,
        "device_name": device_name,
        "compute_capability": capability,
        "backend": "pytorch",
        "default_sample_rate": 48000,
        "vram": get_vram_info()
    }


def handle_load_model(req: Dict[str, Any]) -> Dict[str, Any]:
    global _TTS_MODEL, _TTS_CONFIG
    t0 = time.perf_counter()

    if _TTS_MODEL is not None:
        return {"status": "ok", "message": "Model already loaded", "load_time_sec": 0.0, "vram": get_vram_info()}

    import torch
    from vieneu import Vieneu

    max_batch_size = int(req.get("max_batch_size", 32))
    dtype = req.get("dtype", "bfloat16" if torch.cuda.is_available() else "float32")
    device = "cuda" if torch.cuda.is_available() else "cpu"

    log_debug(f"Loading VieNeu v3 Turbo PyTorch model on {device} ({dtype}, max_batch_size={max_batch_size})...")

    # If local offline models exist, use them; otherwise Hugging Face hub
    backbone_repo = req.get("backbone_repo", "pnnbao-ump/VieNeu-TTS-v3-Turbo")
    moss_tokenizer = req.get("moss_tokenizer", "OpenMOSS-Team/MOSS-Audio-Tokenizer-Nano")

    _TTS_MODEL = Vieneu(
        backbone_repo=backbone_repo,
        model_subfolder="update",
        moss_tokenizer=moss_tokenizer,
        device=device,
        dtype=dtype,
        backend="pytorch",
        max_batch_size=max_batch_size
    )
    _TTS_CONFIG = {
        "max_batch_size": max_batch_size,
        "device": device,
        "dtype": dtype
    }

    t_load = time.perf_counter() - t0
    log_debug(f"VieNeu model loaded successfully in {t_load:.2f}s!")
    return {
        "status": "ok",
        "load_time_sec": round(t_load, 3),
        "vram": get_vram_info()
    }


def handle_unload_model(req: Dict[str, Any]) -> Dict[str, Any]:
    global _TTS_MODEL, _TTS_CONFIG
    t0 = time.perf_counter()

    if _TTS_MODEL is not None:
        try:
            del _TTS_MODEL
        except Exception:
            pass
        _TTS_MODEL = None
        _TTS_CONFIG = {}

    gc.collect()
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            torch.cuda.ipc_collect()
    except Exception:
        pass

    t_unload = time.perf_counter() - t0
    log_debug(f"VieNeu model unloaded from VRAM in {t_unload:.2f}s.")
    return {
        "status": "ok",
        "unload_time_sec": round(t_unload, 3),
        "vram": get_vram_info()
    }


def handle_enroll_voice(req: Dict[str, Any]) -> Dict[str, Any]:
    """Pre-calculates speaker embedding and ref codes once for a cloned voice."""
    global _TTS_MODEL, _ENROLLED_VOICES
    if _TTS_MODEL is None:
        handle_load_model({})

    voice_key = req.get("voice_key")
    ref_audio = req.get("ref_audio")
    denoise = req.get("denoise", True)
    use_ref_codes = req.get("use_ref_codes", True)

    if not voice_key or not ref_audio or not os.path.exists(ref_audio):
        return {"status": "error", "error": f"Invalid voice enrollment parameters or file not found: {ref_audio}"}

    if voice_key in _ENROLLED_VOICES:
        return {"status": "ok", "voice_key": voice_key, "cached": True}

    t0 = time.perf_counter()
    clean_ref = _TTS_MODEL._preclean_reference_audio(ref_audio)
    try:
        speaker_emb, ref_codes = _TTS_MODEL.engine.prepare_reference(
            str(clean_ref), denoise=denoise, use_ref_codes=use_ref_codes
        )
        _ENROLLED_VOICES[voice_key] = {
            "speaker_emb": speaker_emb,
            "codes": ref_codes,
            "enrolled_at": time.time()
        }
        t_enroll = time.perf_counter() - t0
        log_debug(f"Enrolled voice '{voice_key}' in {t_enroll:.3f}s")
        return {"status": "ok", "voice_key": voice_key, "enroll_time_sec": round(t_enroll, 3), "cached": False}
    finally:
        if clean_ref and os.path.abspath(clean_ref) != os.path.abspath(ref_audio):
            try:
                os.remove(clean_ref)
            except Exception:
                pass


def handle_synthesize_batch(req: Dict[str, Any]) -> Dict[str, Any]:
    global _TTS_MODEL, _ENROLLED_VOICES
    if _TTS_MODEL is None:
        handle_load_model({})

    items = req.get("items", [])
    if not items:
        return {"status": "ok", "results": []}

    voice_id = req.get("voice_id", "local_ngoc_huyen")
    target_voice = None
    target_ref_audio = None

    # Resolve ref_audio first (for cloned voices or custom audio reference)
    if req.get("ref_audio") and os.path.exists(req.get("ref_audio")):
        target_ref_audio = req.get("ref_audio")
    elif voice_id in _ENROLLED_VOICES:
        target_voice = _ENROLLED_VOICES[voice_id]
    else:
        # Check preset name mapping
        preset_map = {
            "local_ngoc_huyen": "Ngọc Huyền",
            "ngoc_huyen": "Ngọc Huyền",
            "local_minh_duc": "Minh Đức",
            "minh_duc": "Minh Đức",
            "local_truc_ly": "Trúc Ly",
            "truc_ly": "Trúc Ly",
            "local_thai_son": "Thái Sơn",
            "thai_son": "Thái Sơn",
            "local_thuc_doan": "Thục Đoan",
            "thuc_doan": "Thục Đoan",
            "local_quang_son": "Quang Sơn",
            "quang_son": "Quang Sơn",
            "local_ngoc_tran": "Ngọc Trân",
            "ngoc_tran": "Ngọc Trân",
            "local_adam": "Adam",
            "kokoro_am_adam": "Adam",
            "local_kokoro_am_adam": "Adam",
            "en_adam": "Adam",
            "adam": "Adam",
        }
        if voice_id in preset_map:
            target_voice = preset_map[voice_id]
        else:
            # Dynamic fallback preserving gender & language
            try:
                import custom_voices
                profile = custom_voices.resolve_voice_profile(voice_id)
                is_male = profile.get("gender") == "male"
                is_en = "en" in (profile.get("lang") or "").lower()
                if is_en and is_male:
                    target_voice = "Adam"
                elif is_male:
                    target_voice = "Minh Đức"
                else:
                    target_voice = "Ngọc Huyền"
            except Exception:
                target_voice = "Minh Đức" if any(w in str(voice_id).lower() for w in ['nam', 'duc', 'dung', 'dat', 'adam', 'guy', 'male']) else "Ngọc Huyền"

    batch_size = int(req.get("batch_size", 8))
    speed = float(req.get("speed", 1.0))
    target_sr = int(req.get("target_sample_rate", 48000))
    target_ch = int(req.get("target_channels", 1))

    texts = [it["text"] for it in items]
    results = []

    # Run infer_batch with automatic batch size degradation on OOM
    t0 = time.perf_counter()
    waveforms = None
    current_bs = batch_size

    while current_bs >= 1:
        try:
            if target_ref_audio:
                waveforms = _TTS_MODEL.infer_batch(
                    texts=texts,
                    ref_audio=target_ref_audio,
                    batch_size=current_bs,
                    apply_watermark=False
                )
            else:
                waveforms = _TTS_MODEL.infer_batch(
                    texts=texts,
                    voice=target_voice,
                    batch_size=current_bs,
                    apply_watermark=False
                )
            break
        except Exception as e:
            err_str = str(e).lower()
            if "out of memory" in err_str or "oom" in err_str:
                log_debug(f"CUDA OOM with batch_size={current_bs}! Reducing to {current_bs // 2}...")
                try:
                    import torch
                    torch.cuda.empty_cache()
                except Exception:
                    pass
                current_bs = current_bs // 2
                if current_bs < 1:
                    raise RuntimeError(f"CUDA Out-Of-Memory even at batch_size=1: {e}")
            else:
                raise e

    t_infer = time.perf_counter() - t0

    # Write each audio to output file
    import soundfile as sf
    import scipy.signal

    for i, it in enumerate(items):
        item_id = it.get("id", i)
        out_path = it.get("output_path")
        if not out_path:
            results.append({"id": item_id, "error": "Missing output_path", "success": False})
            continue

        raw_wav = waveforms[i] if (waveforms is not None and i < len(waveforms)) else np.array([], dtype=np.float32)
        if len(raw_wav) == 0:
            results.append({"id": item_id, "error": "Empty synthesized waveform", "success": False})
            continue

        audio_arr = raw_wav
        orig_sr = 48000

        # Adjust speed if requested (resample)
        if abs(speed - 1.0) > 0.03:
            s_val = max(0.5, min(2.5, speed))
            target_len = int(round(len(audio_arr) / s_val))
            audio_arr = scipy.signal.resample(audio_arr, target_len)

        # Resample sample rate if requested
        if target_sr != orig_sr:
            new_num_samples = int(round(len(audio_arr) * target_sr / float(orig_sr)))
            audio_arr = scipy.signal.resample(audio_arr, new_num_samples)

        # Convert channels
        if target_ch == 2 and len(audio_arr.shape) == 1:
            final_pcm = np.column_stack((audio_arr, audio_arr))
        else:
            final_pcm = audio_arr

        # Clip to int16
        pcm_int16 = np.clip(final_pcm * 32767.0, -32768, 32767).astype(np.int16)

        # Atomic write
        temp_out = out_path + f".tmp_{int(time.time()*1000)}.wav"
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        sf.write(temp_out, pcm_int16, target_sr, subtype='PCM_16')
        if os.path.exists(out_path):
            try:
                os.remove(out_path)
            except Exception:
                pass
        os.replace(temp_out, out_path)

        dur = len(final_pcm) / float(target_sr)
        results.append({
            "id": item_id,
            "path": out_path,
            "duration": round(dur, 3),
            "sample_rate": target_sr,
            "channels": target_ch,
            "success": True,
            "error": None
        })

    return {
        "status": "ok",
        "infer_time_sec": round(t_infer, 3),
        "total_items": len(items),
        "results": results,
        "vram": get_vram_info()
    }


def main():
    log_debug("Worker process started. Entering event loop...")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            cmd = req.get("cmd")
            req_id = req.get("req_id")

            if cmd == "handshake":
                resp = handle_handshake(req)
            elif cmd == "load_model":
                resp = handle_load_model(req)
            elif cmd == "unload_model":
                resp = handle_unload_model(req)
            elif cmd == "enroll_voice":
                resp = handle_enroll_voice(req)
            elif cmd == "synthesize_batch":
                resp = handle_synthesize_batch(req)
            elif cmd == "ping":
                resp = {"status": "ok", "vram": get_vram_info()}
            elif cmd == "shutdown":
                handle_unload_model({})
                resp = {"status": "ok", "message": "shutting down"}
                if req_id: resp["req_id"] = req_id
                sys.stdout.write(json.dumps(resp) + "\n")
                sys.stdout.flush()
                break
            else:
                resp = {"status": "error", "error": f"Unknown command: {cmd}"}

            if req_id is not None:
                resp["req_id"] = req_id

            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()

        except Exception as e:
            err_msg = traceback.format_exc()
            log_debug(f"Error handling request: {err_msg}")
            err_resp = {"status": "error", "error": str(e), "traceback": err_msg}
            if 'req' in locals() and req.get("req_id"):
                err_resp["req_id"] = req.get("req_id")
            sys.stdout.write(json.dumps(err_resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
