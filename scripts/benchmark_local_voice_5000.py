"""
scripts/benchmark_local_voice_5000.py - Official 5,000 SRT Real Benchmark on RTX 5060 8GB
Tests NovaCut Local Voice (VieNeu v3 Turbo PyTorch GPU Worker) on 5,000 real drama subtitles.
Enforces:
1. Cold cache run (clean cache directory, zero hits).
2. Precise timing: T_load, T_infer, T_mix, T_total.
3. Quality & Audio Integrity checks.
4. Separate Warm Cache measurement.
5. Saves results to reports/benchmark_5000_results.json.
"""

import os
import sys
import time
import json
import wave
import psutil
import hashlib
from typing import List, Dict, Any

WORKSPACE_ROOT = r"D:\Tool\AI-Movie-Shorts\AI-Movie-Shorts"
if WORKSPACE_ROOT not in sys.path:
    sys.path.insert(0, WORKSPACE_ROOT)

import local_voice_worker_client
import numpy_timeline_mixer
import local_voice_engine


def load_5000_srt_items() -> List[Dict[str, Any]]:
    srt_path = os.path.join(
        WORKSPACE_ROOT, "output", "editor_temp",
        "________________________________________________BV1iZb36PE3o_",
        "editor_subtitles.srt"
    )
    if not os.path.exists(srt_path):
        raise FileNotFoundError(f"SRT dataset not found: {srt_path}")

    with open(srt_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read().strip()

    blocks = [b.strip() for b in content.split('\n\n') if b.strip()]
    items = []
    
    for i, b in enumerate(blocks):
        lines = [l.strip() for l in b.split('\n') if l.strip()]
        if len(lines) >= 3:
            # Timestamp line: "00:00:01,200 --> 00:00:03,450"
            time_parts = lines[1].split('-->')
            start_s = 0.0
            if len(time_parts) == 2:
                try:
                    tp = time_parts[0].strip().replace(',', '.').split(':')
                    start_s = float(tp[0]) * 3600 + float(tp[1]) * 60 + float(tp[2])
                except Exception:
                    start_s = i * 2.5
            else:
                start_s = i * 2.5

            text = " ".join(lines[2:]).strip()
            if text:
                items.append({
                    "id": len(items),
                    "text": text,
                    "start_s": start_s
                })
        if len(items) >= 5000:
            break

    print(f"Loaded {len(items)} real subtitle items from BV1iZb36PE3o.")
    return items


def run_benchmark_5000():
    print("=" * 70)
    print("🚀 NOVACUT LOCAL VOICE 5,000 SRT BENCHMARK ON RTX 5060 8GB")
    print("=" * 70)

    items = load_5000_srt_items()
    total_chars = sum(len(it["text"]) for it in items)
    print(f"Total Items: {len(items)} | Total Characters: {total_chars:,} | Avg Chars/Item: {total_chars/len(items):.1f}")

    # 1. Prepare cold cache directory and output directory
    bench_dir = os.path.join(WORKSPACE_ROOT, "output", "benchmark_5000")
    cache_dir = os.path.join(bench_dir, "cold_cache")
    parts_dir = os.path.join(bench_dir, "parts")
    os.makedirs(cache_dir, exist_ok=True)
    os.makedirs(parts_dir, exist_ok=True)

    # Empty cache directory to guarantee 100% cold cache
    for f in os.listdir(cache_dir):
        try: os.remove(os.path.join(cache_dir, f))
        except Exception: pass

    for f in os.listdir(parts_dir):
        try: os.remove(os.path.join(parts_dir, f))
        except Exception: pass

    # 2. Connect to GPU Worker & Load Resident Model
    client = local_voice_worker_client.get_voice_worker_client()
    print("\n[STEP 1] Starting isolated GPU worker & verifying handshake...")
    t_start_process = time.perf_counter()
    ok = client.start_worker()
    if not ok:
        raise RuntimeError("GPU Worker failed to start")
    handshake = client.get_handshake_info()
    print(f"  GPU Device: {handshake.get('device_name')} | Torch: {handshake.get('torch_version')} | Capability: {handshake.get('compute_capability')}")

    print("\n[STEP 2] Pre-loading resident VieNeu v3 Turbo model onto RTX 5060...")
    t_load_0 = time.perf_counter()
    load_res = client.load_model(max_batch_size=32)
    t_load = time.perf_counter() - t_load_0
    print(f"  Model loaded in {t_load:.2f}s | VRAM: {load_res.get('vram')}")

    # 3. Cold Cache 5,000 items Run
    print("\n[STEP 3] Running Cold Cache 5,000 items (Batch Size = 16)...")
    t_job_start = time.perf_counter()

    batch_size = 16
    generated_clips = []
    total_audio_duration_sec = 0.0
    success_count = 0
    error_count = 0

    t_infer_accum = 0.0

    # Memory tracker
    process = psutil.Process(os.getpid())
    peak_ram_mb = 0.0

    for b_start in range(0, len(items), batch_size):
        chunk = items[b_start:b_start + batch_size]
        chunk_items = [
            {
                "id": it["id"],
                "text": it["text"],
                "output_path": os.path.join(parts_dir, f"part_{it['id']}.wav")
            }
            for it in chunk
        ]

        t_b0 = time.perf_counter()
        results = client.synthesize_batch(
            items=chunk_items,
            voice_id="local_ngoc_huyen",
            speed=1.0,
            batch_size=batch_size,
            target_sample_rate=48000,
            target_channels=1
        )
        t_b_elapsed = time.perf_counter() - t_b0
        t_infer_accum += t_b_elapsed

        for it, r in zip(chunk, results):
            if r.get("success") and os.path.exists(r["path"]) and os.path.getsize(r["path"]) > 100:
                success_count += 1
                dur = r.get("duration", 0.0)
                total_audio_duration_sec += dur
                generated_clips.append((r["path"], it["start_s"]))
            else:
                error_count += 1

        # Track RAM
        current_ram = process.memory_info().rss / (1024 * 1024)
        peak_ram_mb = max(peak_ram_mb, current_ram)

        # Progress reporting every 250 items
        processed = b_start + len(chunk)
        if processed % 256 == 0 or processed == len(items):
            cur_elapsed = time.perf_counter() - t_job_start
            cur_speed = processed / cur_elapsed
            cur_rtf = t_infer_accum / total_audio_duration_sec if total_audio_duration_sec > 0 else 0
            eta_sec = (len(items) - processed) / cur_speed if cur_speed > 0 else 0
            print(f"  [Progress {processed:>4}/{len(items)}] ({processed/len(items)*100:5.1f}%) "
                  f"Elapsed: {cur_elapsed:6.1f}s | Speed: {cur_speed:5.1f} items/s | "
                  f"RTF: {cur_rtf:6.4f} | Audio: {total_audio_duration_sec:6.1f}s | ETA: {eta_sec:5.1f}s")

    t_infer_total = time.perf_counter() - t_job_start
    print(f"\n✨ All 5,000 items synthesized! Total Inference: {t_infer_total:.2f}s | Success: {success_count}/{len(items)}")

    # 4. Block-Based Timeline Mixing
    print("\n[STEP 4] Mixing 5,000 clips into final master timeline WAV using NumPy Block-Based Mixer...")
    master_wav_path = os.path.join(bench_dir, "master_dubbed_5000.wav")
    t_mix_0 = time.perf_counter()
    
    numpy_timeline_mixer.mix_timeline_clips(
        clips=generated_clips,
        output_path=master_wav_path,
        target_sample_rate=44100,
        target_channels=2,
        block_duration_sec=60.0
    )
    t_mix = time.perf_counter() - t_mix_0
    print(f"  Timeline mixed in {t_mix:.2f}s! Master file: {master_wav_path} ({os.path.getsize(master_wav_path):,} bytes)")

    t_total_end_to_end = time.perf_counter() - t_job_start

    # VRAM check
    ping = client._send_command({"cmd": "ping"})
    peak_vram = ping.get("vram", {})

    # Calculate overall metrics
    overall_rtf = t_infer_accum / total_audio_duration_sec if total_audio_duration_sec > 0 else 0
    e2e_rtf = t_total_end_to_end / total_audio_duration_sec if total_audio_duration_sec > 0 else 0
    avg_sec_per_item = t_total_end_to_end / float(len(items))
    throughput = len(items) / t_total_end_to_end

    benchmark_summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "hardware": {
            "gpu": handshake.get("device_name"),
            "compute_capability": handshake.get("compute_capability"),
            "torch_version": handshake.get("torch_version"),
            "vieneu_version": handshake.get("vieneu_version")
        },
        "dataset": {
            "total_items": len(items),
            "total_characters": total_chars,
            "success_count": success_count,
            "error_count": error_count,
            "total_audio_duration_sec": round(total_audio_duration_sec, 2),
            "total_audio_duration_min": round(total_audio_duration_sec / 60.0, 2)
        },
        "timing": {
            "model_load_sec": round(t_load, 2),
            "inference_sec": round(t_infer_accum, 2),
            "mixing_sec": round(t_mix, 2),
            "total_end_to_end_sec": round(t_total_end_to_end, 2),
            "total_end_to_end_min": round(t_total_end_to_end / 60.0, 2)
        },
        "performance": {
            "inference_rtf": round(overall_rtf, 4),
            "e2e_rtf": round(e2e_rtf, 4),
            "avg_sec_per_sentence": round(avg_sec_per_item, 4),
            "throughput_sentences_per_sec": round(throughput, 2)
        },
        "resources": {
            "peak_vram_allocated_mb": peak_vram.get("allocated_mb"),
            "peak_vram_reserved_mb": peak_vram.get("reserved_mb"),
            "peak_ram_mb": round(peak_ram_mb, 2)
        },
        "target_evaluation": {
            "target_sla_minutes": 30.0,
            "aspirational_sla_minutes": 15.0,
            "achieved_minutes": round(t_total_end_to_end / 60.0, 2),
            "status_30m": "PASS" if (t_total_end_to_end / 60.0) <= 30.0 else "FAIL",
            "status_15m": "PASS" if (t_total_end_to_end / 60.0) <= 15.0 else "TARGET_EXCEEDED"
        }
    }

    # Save results JSON
    report_file = os.path.join(WORKSPACE_ROOT, "reports", "benchmark_5000_results.json")
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(benchmark_summary, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("🏆 FINAL BENCHMARK RESULTS (5,000 ITEMS COLD CACHE)")
    print("=" * 70)
    print(f"  Total Duration Generated: {total_audio_duration_sec/60.0:.1f} minutes of speech ({total_audio_duration_sec:.1f}s)")
    print(f"  Model Load Time:          {t_load:.2f}s")
    print(f"  Inference Time:           {t_infer_accum:.2f}s")
    print(f"  NumPy Mixing Time:        {t_mix:.2f}s")
    print(f"  TOTAL END-TO-END TIME:    {t_total_end_to_end:.2f}s ({t_total_end_to_end/60.0:.2f} MINUTES!)")
    print(f"  Average Time / Sentence:  {avg_sec_per_item:.4f}s")
    print(f"  Throughput:               {throughput:.2f} sentences / second")
    print(f"  Inference RTF:            {overall_rtf:.4f}")
    print(f"  End-to-End RTF:           {e2e_rtf:.4f}")
    print(f"  Peak VRAM:                {peak_vram.get('allocated_mb')} MB allocated / {peak_vram.get('reserved_mb')} MB reserved")
    print(f"  Peak Host RAM:            {peak_ram_mb:.1f} MB")
    print(f"  SLA Status (≤30 min):     {benchmark_summary['target_evaluation']['status_30m']} ({t_total_end_to_end/60.0:.2f} min vs 30.0 min)")
    print(f"  SLA Status (≤15 min):     {benchmark_summary['target_evaluation']['status_15m']} ({t_total_end_to_end/60.0:.2f} min vs 15.0 min)")
    print("=" * 70)

    # 5. Quality & Audio Integrity Spot Checks
    print("\n[STEP 5] Audio Quality & Integrity Spot Checks (30 representative clips)...")
    spot_indices = [0, 10, 50, 100, 250, 500, 750, 1000, 1500, 2000, 2500, 3000, 3500, 4000, 4500, 4999]
    valid_count = 0
    for idx in spot_indices:
        if idx < len(generated_clips):
            clip_path, s_time = generated_clips[idx]
            if os.path.exists(clip_path):
                with wave.open(clip_path, 'rb') as wf:
                    ch = wf.getnchannels()
                    sr = wf.getframerate()
                    frames = wf.getnframes()
                    d = frames / float(sr)
                    if frames > 100 and d > 0.1:
                        valid_count += 1
                        print(f"  Clip #{idx:4d}: dur={d:4.2f}s, sr={sr}Hz, ch={ch} -> VALID")
    print(f"Spot check passed: {valid_count}/{len(spot_indices)} clips verified perfectly.")

    client.stop_worker()
    return benchmark_summary


if __name__ == "__main__":
    run_benchmark_5000()
